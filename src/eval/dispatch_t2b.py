#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-GPU dispatcher for the FULL-SCALE Task 2B eval (T2B-DE + T2B-DIR,
4 models x 3 seeds), adapted from src/eval/dispatch_full.py (same contiguous
shard / order-preserving merge strategy, one vLLM worker per physical GPU,
model loaded once, manifest drives all task x seed jobs for that GPU's shard).

Difference from dispatch_full.py: GPUs are a FORCED explicit list (not
auto-probed) because this run must stay confined to a specific pre-approved
set of indices per node, rather than grabbing whatever nvidia-smi reports
free at prep time (that free-probe is still run, but only to WARN if a forced
slot turns out busy -- it does not expand or substitute the slot list).

Subcommands:
  prep   — verify forced GPU slots free, shard prompts, write manifests + alloc.json + launch.sh
  merge  — concatenate shard outputs back into per-(model,task,seed) prediction files
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
T2B = os.path.join(REPO, "data", "task2b")
SHARD_DIR = os.path.join(REPO, "data", "runs", "shards_t2b")
ALLOC_JSON = os.path.join(SHARD_DIR, "alloc.json")
HUB = "/home/zhengz2/.cache/huggingface/hub"
VLLM_PY = "/home/zhengz2/miniconda3/envs/vllm/bin/python"
INFER = os.path.join(REPO, "src", "eval", "infer_vllm.py")
SEP = "=" * 80

MODELS = {
    "qwen14b": ("models--Qwen--Qwen2.5-14B-Instruct", 160),
    "llama8b": ("models--NousResearch--Meta-Llama-3.1-8B-Instruct", 80),
    "qwen7b":  ("models--Qwen--Qwen2.5-7B-Instruct", 77),
    "qwen4b":  ("models--Qwen--Qwen3-4B-Instruct-2507", 53),
}
TASKS = {
    "t2bde":  (f"{T2B}/t2bde_prompts_full_s{{s}}.txt",  f"{T2B}/t2bde_pred_{{m}}_s{{s}}.txt"),
    "t2bdir": (f"{T2B}/t2bdir_prompts_full_s{{s}}.txt", f"{T2B}/t2bdir_pred_{{m}}_s{{s}}.txt"),
}
SEEDS = [0, 1, 2]

# Forced slots, high-index-first within each node (per gpu_dispatch_high_index_first
# convention), 8s-06 listed first as in dispatch_full.py's NODES order.
FORCED_SLOTS = [
    ("h100-8s-06", 5), ("h100-8s-06", 4), ("h100-8s-06", 3),
    ("h100-8s-06", 2), ("h100-8s-06", 1), ("h100-8s-06", 0),
    ("h100-8s-01", 7), ("h100-8s-01", 6), ("h100-8s-01", 5),
    ("h100-8s-01", 4), ("h100-8s-01", 3), ("h100-8s-01", 2),
]


def _check_free(slots):
    """Verify each forced slot is actually free right now; return (free, busy)."""
    by_node = {}
    for node, gpu in slots:
        by_node.setdefault(node, []).append(gpu)
    status = {}
    for node in by_node:
        try:
            out = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", node,
                 "nvidia-smi --query-gpu=index,memory.used,utilization.gpu "
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=25).stdout
        except Exception as e:
            raise RuntimeError(f"cannot reach {node}: {e}")
        for line in out.strip().splitlines():
            idx, mem, util = [x.strip() for x in line.split(",")]
            status[(node, int(idx))] = (int(mem), int(util))
    free, busy = [], []
    for s in slots:
        mem, util = status.get(s, (99999, 99))
        if mem < 2000 and util < 10:
            free.append(s)
        else:
            busy.append((s, mem, util))
    return free, busy


def _apportion(weights, n):
    keys = list(weights); tot = sum(weights.values())
    raw = {k: weights[k] / tot * n for k in keys}
    alloc = {k: max(1, int(raw[k])) for k in keys}
    while sum(alloc.values()) > n:
        alloc[max(alloc, key=lambda k: alloc[k])] -= 1
    while sum(alloc.values()) < n:
        alloc[max(keys, key=lambda k: raw[k] - alloc[k])] += 1
    return alloc


def _count_blocks(path):
    """Count blocks without materializing them (memory-safe for multi-GB files)."""
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == SEP:
                n += 1
    return n


def _contig_shards(n_items, k):
    base, rem = divmod(n_items, k); out, s = [], 0
    for j in range(k):
        e = s + base + (1 if j < rem else 0); out.append((s, e)); s = e
    return out


def _stream_shard(path, boundaries, out_paths):
    """Single streaming pass: write block i to whichever out file's [a,b) contains i.
    Keeps only the current block's lines in memory at any time."""
    outs = [open(p, "w", encoding="utf-8") for p in out_paths]

    def _shard_of(i):
        for j, (a, b) in enumerate(boundaries):
            if a <= i < b:
                return j
        return len(boundaries) - 1

    block_idx = 0
    buf = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() == SEP:
                    text = "".join(buf).strip()
                    if text:
                        j = _shard_of(block_idx)
                        outs[j].write(text + "\n\n" + SEP + "\n\n")
                        block_idx += 1
                    buf = []
                else:
                    buf.append(line)
            # trailing block with no terminal SEP (shouldn't normally occur)
            text = "".join(buf).strip()
            if text:
                j = _shard_of(block_idx)
                outs[j].write(text + "\n\n" + SEP + "\n\n")
    finally:
        for o in outs:
            o.close()
    return block_idx


def _sp(task, s, m, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.prompts.txt")
def _so(task, s, m, j): return os.path.join(SHARD_DIR, f"{task}_s{s}_{m}_g{j}.pred.txt")


def _model_dir(hub):
    cand = os.path.join(HUB, hub, "snapshots")
    return os.path.join(cand, sorted(os.listdir(cand))[0]) if os.path.isdir(cand) else hub


def prep(exclude=None):
    exclude = set(exclude or [])
    os.makedirs(SHARD_DIR, exist_ok=True)
    slots = [s for s in FORCED_SLOTS if s not in exclude]
    free, busy = _check_free(slots)
    if busy:
        print(f"WARNING: {len(busy)} forced slot(s) NOT free, excluding: {busy}")
    slots = free
    alloc = _apportion({m: w for m, (h, w) in MODELS.items()}, len(slots))
    json.dump(alloc, open(ALLOC_JSON, "w"))
    print(f"usable slots: {len(slots)} {slots}\nalloc: {alloc}")
    slot_i, launch = 0, []
    for m, (hub, _w) in MODELS.items():
        ngpu = alloc[m]; my = slots[slot_i:slot_i + ngpu]; slot_i += ngpu
        model_dir = _model_dir(hub)
        manifests = {j: [] for j in range(ngpu)}
        for task, (ptmpl, _) in TASKS.items():
            for s in SEEDS:
                src = ptmpl.format(s=s)
                n_items = _count_blocks(src)
                boundaries = _contig_shards(n_items, ngpu)
                out_paths = [_sp(task, s, m, j) for j in range(ngpu)]
                written = _stream_shard(src, boundaries, out_paths)
                print(f"  [{m}] {task} s{s}: {n_items} blocks -> {ngpu} shards "
                      f"(wrote {written})")
                for j in range(ngpu):
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
            launch.append(f"task run 'yvcf2b_{m}_g{j}' 'ssh {node} \"{remote}\"'")
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
    if a.cmd == "prep":
        # NOTE: at first safety-check (17:39 CDT) a108983's job (pid 2741642) was live on
        # h100-8s-01 idx4 (15GB used); re-checked free at 17:55 CDT immediately before this
        # run. _check_free() re-verifies all forced slots again right now regardless.
        prep(exclude=[])
    else:
        merge()
