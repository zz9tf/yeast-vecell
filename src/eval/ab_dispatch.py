#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-GPU dispatcher for the T1/T2A A/B prompt-ablation eval (Qwen2.5-14B only).

Same sharding strategy as dispatch_full.py (contiguous shards per GPU, one
vLLM worker per physical GPU, model loaded once), but scoped to the 8
A/B prompt files (T1a-DE, T1b-DIR, T2A-DE, T2A-DIR x branch A/B) x 3 seeds
produced by support/variants/{A_mechanism,B_calibration}[/task2] templates,
single model Qwen2.5-14B-Instruct (the ablation-suite convention).

Subcommands:
  prep   — probe free GPUs, shard prompts, write manifests + alloc.json + launch.sh
  merge  — concatenate shard outputs back into per-(branch,task,seed) prediction files
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AB = os.path.join(REPO, "data", "ab")
SHARD_DIR = os.path.join(AB, "shards")
ALLOC_JSON = os.path.join(SHARD_DIR, "alloc.json")
HUB = "/home/zhengz2/.cache/huggingface/hub"
VLLM_PY = "/home/zhengz2/miniconda3/envs/vllm/bin/python"
INFER = os.path.join(REPO, "src", "eval", "infer_vllm.py")
SEP = "=" * 80

MODEL_HUB = "models--Qwen--Qwen2.5-14B-Instruct"
NODES = ["h100-8s-06", "h100-8s-01"]
# Avoid h100-8s-01 GPU0 (occupied by an unrelated job as of prep time) — the
# free-slot probe below already filters by mem/util so this is belt-and-braces.
TASKS = {
    "DE-C":    f"{AB}/DE_prompts_C_s{{s}}.txt",
    "DE-D":    f"{AB}/DE_prompts_D_s{{s}}.txt",
    "DIR-C":   f"{AB}/DIR_prompts_C_s{{s}}.txt",
    "DIR-D":   f"{AB}/DIR_prompts_D_s{{s}}.txt",
    "t2de-C":  f"{AB}/t2de_prompts_C_s{{s}}.txt",
    "t2de-D":  f"{AB}/t2de_prompts_D_s{{s}}.txt",
    "t2dir-C": f"{AB}/t2dir_prompts_C_s{{s}}.txt",
    "t2dir-D": f"{AB}/t2dir_prompts_D_s{{s}}.txt",
}
# Previous A/B run's tasks (kept here for reference, not active):
# "DE-A": f"{AB}/DE_prompts_A_s{{s}}.txt", "DE-B": f"{AB}/DE_prompts_B_s{{s}}.txt",
# "DIR-A": f"{AB}/DIR_prompts_A_s{{s}}.txt", "DIR-B": f"{AB}/DIR_prompts_B_s{{s}}.txt",
# "t2de-A": f"{AB}/t2de_prompts_A_s{{s}}.txt", "t2de-B": f"{AB}/t2de_prompts_B_s{{s}}.txt",
# "t2dir-A": f"{AB}/t2dir_prompts_A_s{{s}}.txt", "t2dir-B": f"{AB}/t2dir_prompts_B_s{{s}}.txt",
SEEDS = [0, 1, 2]


def _free_slots():
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


def _read_blocks(path):
    with open(path, "r", encoding="utf-8") as f:
        return [b for b in f.read().split(SEP) if b.strip()]


def _iter_blocks(path):
    """Stream blocks one at a time (O(1) memory) instead of loading the whole
    (multi-GB) prompt file into a string + list simultaneously — the node's
    free RAM is shared with other users' jobs and spiked OOM under the naive
    read-whole-file-then-split approach."""
    buf = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == SEP:
                blk = "".join(buf).strip()
                if blk:
                    yield blk
                buf = []
            else:
                buf.append(line)
    blk = "".join(buf).strip()
    if blk:
        yield blk


def _count_blocks(path):
    return sum(1 for _ in _iter_blocks(path))


def _contig_shards(n_items, k):
    base, rem = divmod(n_items, k); out, s = [], 0
    for j in range(k):
        e = s + base + (1 if j < rem else 0); out.append((s, e)); s = e
    return out


def _sp(task, s, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_g{j}.prompts.txt")
def _so(task, s, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_g{j}.pred.txt")


def _model_dir():
    cand = os.path.join(HUB, MODEL_HUB, "snapshots")
    return os.path.join(cand, sorted(os.listdir(cand))[0])


def _select_slots(cap_per_node=None):
    """Group free slots by node (high-index-first within each node, project
    convention). ``cap_per_node`` = {node: max_gpus} caps how many GPUs to
    take from a given node (used to leave headroom for other concurrent jobs
    on a shared node)."""
    slots = _free_slots()
    by_node = {}
    for node, gpu in slots:
        by_node.setdefault(node, []).append(gpu)
    out = []
    for node in NODES:
        gpus = by_node.get(node, [])
        cap = (cap_per_node or {}).get(node)
        if cap is not None:
            gpus = gpus[:cap]
        out += [(node, g) for g in gpus]
    return out


def prep(max_gpus=None, cap_per_node=None):
    os.makedirs(SHARD_DIR, exist_ok=True)
    slots = _select_slots(cap_per_node)
    if max_gpus:
        slots = slots[:max_gpus]
    ngpu = len(slots)
    json.dump({"qwen14b": ngpu}, open(ALLOC_JSON, "w"))
    print(f"free slots: {ngpu} {slots}")
    model_dir = _model_dir()
    manifests = {j: [] for j in range(ngpu)}
    # Two-pass STREAMING shard per (task, seed) file: count blocks first
    # (O(1) memory), then stream-write into shard files. The full A/B sweep
    # is multi-GB of prompt text and the node's free RAM is shared with other
    # users' jobs — never hold a whole file's blocks in memory at once.
    for task, ptmpl in TASKS.items():
        for s in SEEDS:
            path = ptmpl.format(s=s)
            n = _count_blocks(path)
            bounds = _contig_shards(n, ngpu)
            handles = [open(_sp(task, s, j), "w", encoding="utf-8") for j in range(ngpu)]
            idx, j = 0, 0
            for blk in _iter_blocks(path):
                while idx >= bounds[j][1] and j < ngpu - 1:
                    j += 1
                handles[j].write(blk.strip() + "\n\n" + SEP + "\n\n")
                idx += 1
            for h in handles:
                h.close()
            for j in range(ngpu):
                manifests[j].append((_sp(task, s, j), _so(task, s, j)))
            print(f"  sharded {task} s{s} ({n} cases) -> {ngpu} gpus")
    launch = []
    for j in range(ngpu):
        node, gpu = slots[j]
        mf = os.path.join(SHARD_DIR, f"manifest_g{j}.tsv")
        with open(mf, "w", encoding="utf-8") as f:
            for p, o in manifests[j]:
                f.write(f"{p}\t{o}\n")
        log = os.path.join(SHARD_DIR, f"worker_g{j}.log")
        remote = (f"cd {REPO}/src/cli_pipeline && export CUDA_VISIBLE_DEVICES={gpu} "
                  f"HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_LOGGING_LEVEL=WARNING "
                  f"VLLM_USE_V1=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN "
                  f"CUDA_HOME=/home/zhengz2/miniconda3/envs/vllm "
                  f"PATH=/home/zhengz2/miniconda3/envs/vllm/bin:\\$PATH && "
                  f"{VLLM_PY} {INFER} --model {model_dir} --manifest {mf} > {log} 2>&1")
        launch.append(f"task run 'yvab_g{j}' 'ssh {node} \"{remote}\"'")
    with open(os.path.join(SHARD_DIR, "launch.sh"), "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\nexport PATH=/home/zhengz2/miniconda3/bin:$PATH\n" +
                "\n".join(launch) + "\n")
    print(f"prep done: {ngpu} workers. launch: bash {SHARD_DIR}/launch.sh")


def merge():
    alloc = json.load(open(ALLOC_JSON))
    ngpu = alloc["qwen14b"]
    for task in TASKS:
        for s in SEEDS:
            out = os.path.join(AB, f"{task}_pred_s{s}.txt")
            parts = [_so(task, s, j) for j in range(ngpu)]
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
    ap.add_argument("--max-gpus", type=int, default=None)
    ap.add_argument("--cap-8s06", type=int, default=None)
    ap.add_argument("--cap-8s01", type=int, default=None)
    a = ap.parse_args()
    cap = {}
    if a.cap_8s06 is not None:
        cap["h100-8s-06"] = a.cap_8s06
    if a.cap_8s01 is not None:
        cap["h100-8s-01"] = a.cap_8s01
    prep(a.max_gpus, cap or None) if a.cmd == "prep" else merge()
