#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""16-GPU dispatcher for the full-scale vLLM eval (T1 full + T2-A, 4 models, 3 seeds).

Strategy (throughput-oriented, model load once per GPU):
  * Each model is given a slice of the 16 GPUs (∝ its estimated cost).
  * Every prompt file is split into CONTIGUOUS shards (one per the model's GPUs),
    so concatenating shard outputs in gpu order restores the original prompt order
    (score.py joins predictions to retrieval BY ORDER).
  * Each physical GPU runs ONE vLLM worker (infer_vllm.py --manifest) that loads the
    model once and processes its shard of every prompt file.

Subcommands:
  prep   — shard prompts, write per-GPU manifests, emit `launch.sh` (task-run lines)
  merge  — concatenate shard outputs back into per-(model,task,seed) prediction files
"""

from __future__ import annotations

import argparse
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUNS = os.path.join(REPO, "data", "runs")
T2 = os.path.join(REPO, "data", "task2")
SHARD_DIR = os.path.join(RUNS, "shards")
HUB = "/home/zhengz2/.cache/huggingface/hub"
VLLM_PY = "/home/zhengz2/miniconda3/envs/vllm/bin/python"
INFER = os.path.join(REPO, "src", "eval", "infer_vllm.py")
SEP = "=" * 80

# model -> (hub dir name, #GPUs).  7+3+3+3 = 16
MODELS = {
    "qwen14b": ("models--Qwen--Qwen2.5-14B-Instruct", 7),
    "llama8b": ("models--NousResearch--Meta-Llama-3.1-8B-Instruct", 3),
    "qwen7b":  ("models--Qwen--Qwen2.5-7B-Instruct", 3),
    "qwen4b":  ("models--Qwen--Qwen3-4B-Instruct-2507", 3),
}
# 16 physical slots, high-index-first on each node (avoid slurm).
SLOTS = ([("h100-8s-06", g) for g in range(7, -1, -1)] +
         [("h100-8s-01", g) for g in range(7, -1, -1)])

# task key -> (prompts path template, pred path template)   {s}=seed
TASKS = {
    "DE":    (f"{RUNS}/DE_prompts_full_s{{s}}.txt",   f"{RUNS}/DE_pred_{{m}}_s{{s}}.txt"),
    "DIR":   (f"{RUNS}/DIR_prompts_full_s{{s}}.txt",  f"{RUNS}/DIR_pred_{{m}}_s{{s}}.txt"),
    "t2de":  (f"{T2}/t2de_prompts_full_s{{s}}.txt",   f"{T2}/t2de_pred_{{m}}_s{{s}}.txt"),
    "t2dir": (f"{T2}/t2dir_prompts_full_s{{s}}.txt",  f"{T2}/t2dir_pred_{{m}}_s{{s}}.txt"),
}
SEEDS = [0, 1, 2]


def _read_blocks(path):
    with open(path, "r", encoding="utf-8") as f:
        return [b for b in f.read().split(SEP) if b.strip()]


def _contig_shards(n_items, k):
    """k contiguous [start,end) index ranges covering n_items as evenly as possible."""
    base, rem = divmod(n_items, k)
    out, s = [], 0
    for j in range(k):
        e = s + base + (1 if j < rem else 0)
        out.append((s, e)); s = e
    return out


def _shard_path(task, s, m, j):
    return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.prompts.txt")


def _shard_out(task, s, m, j):
    return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.pred.txt")


def prep():
    os.makedirs(SHARD_DIR, exist_ok=True)
    slot_i = 0
    launch = []
    for m, (hub, ngpu) in MODELS.items():
        model_dir = None
        cand = os.path.join(HUB, hub, "snapshots")
        model_dir = os.path.join(cand, sorted(os.listdir(cand))[0]) if os.path.isdir(cand) else hub
        my_slots = SLOTS[slot_i:slot_i + ngpu]; slot_i += ngpu
        # per-GPU manifest lines
        manifests = {j: [] for j in range(ngpu)}
        for task, (ptmpl, _) in TASKS.items():
            for s in SEEDS:
                blocks = _read_blocks(ptmpl.format(s=s))
                for j, (a, b) in enumerate(_contig_shards(len(blocks), ngpu)):
                    sp = _shard_path(task, s, m, j)
                    with open(sp, "w", encoding="utf-8") as f:
                        for blk in blocks[a:b]:
                            f.write(blk.strip() + "\n\n" + SEP + "\n\n")
                    manifests[j].append((sp, _shard_out(task, s, m, j)))
        for j in range(ngpu):
            node, gpu = my_slots[j]
            mf = os.path.join(SHARD_DIR, f"manifest_{m}_g{j}.tsv")
            with open(mf, "w", encoding="utf-8") as f:
                for p, o in manifests[j]:
                    f.write(f"{p}\t{o}\n")
            log = os.path.join(SHARD_DIR, f"worker_{m}_g{j}.log")
            remote = (f"cd {REPO}/src/cli_pipeline && export CUDA_VISIBLE_DEVICES={gpu} "
                      f"HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_LOGGING_LEVEL=WARNING "
                      f"VLLM_USE_V1=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN "
                      f"CUDA_HOME=/home/zhengz2/miniconda3/envs/vllm "
                      f"PATH=/home/zhengz2/miniconda3/envs/vllm/bin:\\$PATH && "
                      f"{VLLM_PY} {INFER} --model {model_dir} --manifest {mf} > {log} 2>&1")
            name = f"yvcf_{m}_g{j}"
            launch.append(f"task run '{name}' 'ssh {node} \"{remote}\"'")
    launch_sh = os.path.join(SHARD_DIR, "launch.sh")
    with open(launch_sh, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\nexport PATH=/home/zhengz2/miniconda3/bin:$PATH\n")
        f.write("\n".join(launch) + "\n")
    print(f"prep done: {slot_i} workers across {len(MODELS)} models. launch: bash {launch_sh}")


def merge():
    for m in MODELS:
        ngpu = MODELS[m][1]
        for task, (_, otmpl) in TASKS.items():
            for s in SEEDS:
                out = otmpl.format(m=m, s=s)
                parts = [_shard_out(task, s, m, j) for j in range(ngpu)]
                if not all(os.path.exists(p) for p in parts):
                    print(f"  SKIP {out}: missing shard(s)"); continue
                with open(out, "w", encoding="utf-8") as fo:
                    for p in parts:
                        with open(p, "r", encoding="utf-8") as fi:
                            fo.write(fi.read())
                n = sum(1 for _ in open(out) if "End of Query" in _)
                print(f"  merged {out}  ({n} blocks)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "merge"])
    a = ap.parse_args()
    prep() if a.cmd == "prep" else merge()
