#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-GPU dispatcher for the full-scale vLLM eval (T1 full + T2-A, 4 models, 3 seeds).

Strategy (throughput-oriented, model loaded once per GPU):
  * Probe FREE GPUs across nodes; apportion them to models ∝ estimated cost.
  * Each prompt file is split into CONTIGUOUS shards (one per the model's GPUs),
    so concatenating shard outputs in gpu order restores the original prompt order
    (score.py joins predictions to retrieval BY ORDER).
  * Each physical GPU runs ONE vLLM worker (infer_vllm.py --manifest) that loads the
    model once and processes its shard of every prompt file.

Subcommands:
  prep   — probe free GPUs, shard prompts, write manifests + alloc.json + launch.sh
  merge  — concatenate shard outputs back into per-(model,task,seed) prediction files
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUNS = os.path.join(REPO, "data", "runs")
T2 = os.path.join(REPO, "data", "task2")
SHARD_DIR = os.path.join(RUNS, "shards")
ALLOC_JSON = os.path.join(SHARD_DIR, "alloc.json")
HUB = "/home/zhengz2/.cache/huggingface/hub"
VLLM_PY = "/home/zhengz2/miniconda3/envs/vllm/bin/python"
INFER = os.path.join(REPO, "src", "eval", "infer_vllm.py")
SEP = "=" * 80

# model -> (hub dir name, weight = est GPU-hours for proportional GPU allocation)
MODELS = {
    "qwen14b": ("models--Qwen--Qwen2.5-14B-Instruct", 160),
    "llama8b": ("models--NousResearch--Meta-Llama-3.1-8B-Instruct", 80),
    "qwen7b":  ("models--Qwen--Qwen2.5-7B-Instruct", 77),
    "qwen4b":  ("models--Qwen--Qwen3-4B-Instruct-2507", 53),
}
NODES = ["h100-8s-06", "h100-8s-01"]
TASKS = {
    "DE":    (f"{RUNS}/DE_prompts_full_s{{s}}.txt",   f"{RUNS}/DE_pred_{{m}}_s{{s}}.txt"),
    "DIR":   (f"{RUNS}/DIR_prompts_full_s{{s}}.txt",  f"{RUNS}/DIR_pred_{{m}}_s{{s}}.txt"),
    "t2de":  (f"{T2}/t2de_prompts_full_s{{s}}.txt",   f"{T2}/t2de_pred_{{m}}_s{{s}}.txt"),
    "t2dir": (f"{T2}/t2dir_prompts_full_s{{s}}.txt",  f"{T2}/t2dir_pred_{{m}}_s{{s}}.txt"),
}
SEEDS = [0, 1, 2]


def _free_slots():
    """(node, gpu) for GPUs with <2GB used and <10% util; high-index-first."""
    slots = []
    for node in NODES:
        try:
            out = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", node,
                 "nvidia-smi --query-gpu=index,memory.used,utilization.gpu "
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=25).stdout
        except Exception:
            continue
        free = []
        for line in out.strip().splitlines():
            try:
                idx, mem, util = [x.strip() for x in line.split(",")]
                if int(mem) < 2000 and int(util) < 10:
                    free.append(int(idx))
            except ValueError:
                continue
        slots += [(node, g) for g in sorted(free, reverse=True)]
    return slots


def _apportion(weights, n):
    keys = list(weights); tot = sum(weights.values())
    raw = {k: weights[k] / tot * n for k in keys}
    alloc = {k: max(1, int(raw[k])) for k in keys}
    while sum(alloc.values()) > n:
        alloc[max(alloc, key=lambda k: alloc[k])] -= 1
    while sum(alloc.values()) < n:
        alloc[max(keys, key=lambda k: raw[k] - alloc[k])] += 1
    return alloc


def _read_blocks(path):
    with open(path, "r", encoding="utf-8") as f:
        return [b for b in f.read().split(SEP) if b.strip()]


def _contig_shards(n_items, k):
    base, rem = divmod(n_items, k); out, s = [], 0
    for j in range(k):
        e = s + base + (1 if j < rem else 0); out.append((s, e)); s = e
    return out


def _sp(task, s, m, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.prompts.txt")
def _so(task, s, m, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.pred.txt")


def _model_dir(hub):
    cand = os.path.join(HUB, hub, "snapshots")
    return os.path.join(cand, sorted(os.listdir(cand))[0]) if os.path.isdir(cand) else hub


def prep():
    os.makedirs(SHARD_DIR, exist_ok=True)
    slots = _free_slots()
    alloc = _apportion({m: w for m, (h, w) in MODELS.items()}, len(slots))
    json.dump(alloc, open(ALLOC_JSON, "w"))
    print(f"free slots: {len(slots)} {slots}\nalloc: {alloc}")
    slot_i, launch = 0, []
    for m, (hub, _w) in MODELS.items():
        ngpu = alloc[m]; my = slots[slot_i:slot_i + ngpu]; slot_i += ngpu
        model_dir = _model_dir(hub)
        manifests = {j: [] for j in range(ngpu)}
        for task, (ptmpl, _) in TASKS.items():
            for s in SEEDS:
                blocks = _read_blocks(ptmpl.format(s=s))
                for j, (a, b) in enumerate(_contig_shards(len(blocks), ngpu)):
                    with open(_sp(task, s, m, j), "w", encoding="utf-8") as f:
                        for blk in blocks[a:b]:
                            f.write(blk.strip() + "\n\n" + SEP + "\n\n")
                    manifests[j].append((_sp(task, s, m, j), _so(task, s, m, j)))
        for j in range(ngpu):
            node, gpu = my[j]
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
            launch.append(f"task run 'yvcf_{m}_g{j}' 'ssh {node} \"{remote}\"'")
    with open(os.path.join(SHARD_DIR, "launch.sh"), "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\nexport PATH=/home/zhengz2/miniconda3/bin:$PATH\n" +
                "\n".join(launch) + "\n")
    print(f"prep done: {slot_i} workers. launch: bash {SHARD_DIR}/launch.sh")


def merge():
    alloc = json.load(open(ALLOC_JSON))
    for m in MODELS:
        ngpu = alloc[m]
        for task, (_, otmpl) in TASKS.items():
            for s in SEEDS:
                out = otmpl.format(m=m, s=s)
                parts = [_so(task, s, m, j) for j in range(ngpu)]
                if not all(os.path.exists(p) for p in parts):
                    print(f"  SKIP {os.path.basename(out)}: missing shard(s)"); continue
                with open(out, "w", encoding="utf-8") as fo:
                    for p in parts:
                        fo.write(open(p, "r", encoding="utf-8").read())
                n = sum(1 for line in open(out) if "End of Query" in line)
                print(f"  merged {os.path.basename(out)}  ({n} blocks)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "merge"])
    a = ap.parse_args()
    prep() if a.cmd == "prep" else merge()
