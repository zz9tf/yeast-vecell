#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redistribute Qwen3-4B's PENDING files across all free GPUs (bottleneck rescue).

4B finished DE_s0, DE_s1 (merged by dispatch_full). Its remaining 10 files
(DE_s2 + DIR/t2de/t2dir x 3 seeds) get re-sharded across every free GPU here.
  prep  — shard pending files, write manifests + launch.sh (shards_4b/)
  merge — concat the new shards into the final 4B pred files (DE_pred_qwen4b_s2.txt, …)
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import dispatch_full as D

MODEL = "qwen4b"; HUB_DIR = "models--Qwen--Qwen3-4B-Instruct-2507"
SD2 = os.path.join(D.RUNS, "shards_4b")
# pending (task, seed): DE only seed2 (s0,s1 done); DIR/t2de/t2dir all seeds
PENDING = [("DE", 2)] + [(t, s) for t in ("DIR", "t2de", "t2dir") for s in (0, 1, 2)]


def _sp(task, s, j): return os.path.join(SD2, f"{task}_s{s}_g{j}.prompts.txt")
def _so(task, s, j): return os.path.join(SD2, f"{task}_s{s}_g{j}.pred.txt")


def prep():
    os.makedirs(SD2, exist_ok=True)
    slots = D._free_slots(); n = len(slots)
    model_dir = D._model_dir(HUB_DIR)
    print(f"free slots: {n} {slots}")
    manifests = {j: [] for j in range(n)}
    for task, s in PENDING:
        ptmpl = D.TASKS[task][0]
        blocks = D._read_blocks(ptmpl.format(s=s))
        for j, (a, b) in enumerate(D._contig_shards(len(blocks), n)):
            with open(_sp(task, s, j), "w", encoding="utf-8") as f:
                for blk in blocks[a:b]:
                    f.write(blk.strip() + "\n\n" + D.SEP + "\n\n")
            manifests[j].append((_sp(task, s, j), _so(task, s, j)))
    launch = []
    for j in range(n):
        node, gpu = slots[j]
        mf = os.path.join(SD2, f"manifest_g{j}.tsv")
        with open(mf, "w", encoding="utf-8") as f:
            for p, o in manifests[j]:
                f.write(f"{p}\t{o}\n")
        log = os.path.join(SD2, f"worker_g{j}.log")
        remote = (f"cd {D.REPO}/src/cli_pipeline && export CUDA_VISIBLE_DEVICES={gpu} "
                  f"HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_LOGGING_LEVEL=WARNING "
                  f"VLLM_USE_V1=0 VLLM_ATTENTION_BACKEND=FLASH_ATTN "
                  f"CUDA_HOME=/home/zhengz2/miniconda3/envs/vllm "
                  f"PATH=/home/zhengz2/miniconda3/envs/vllm/bin:\\$PATH && "
                  f"{D.VLLM_PY} {D.INFER} --model {model_dir} --manifest {mf} > {log} 2>&1")
        launch.append(f"task run 'yv4b_g{j}' 'ssh {node} \"{remote}\"'")
    with open(os.path.join(SD2, "launch.sh"), "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\nexport PATH=/home/zhengz2/miniconda3/bin:$PATH\n" +
                "\n".join(launch) + "\n")
    # persist n for merge
    open(os.path.join(SD2, "ngpu.txt"), "w").write(str(n))
    print(f"prep4b done: {n} workers. launch: bash {SD2}/launch.sh")


def merge():
    n = int(open(os.path.join(SD2, "ngpu.txt")).read().strip())
    for task, s in PENDING:
        otmpl = D.TASKS[task][1]
        out = otmpl.format(m=MODEL, s=s)
        parts = [_so(task, s, j) for j in range(n)]
        if not all(os.path.exists(p) for p in parts):
            print(f"  SKIP {os.path.basename(out)}: missing shard(s)"); continue
        with open(out, "w", encoding="utf-8") as fo:
            for p in parts:
                fo.write(open(p, "r", encoding="utf-8").read())
        c = sum(1 for line in open(out) if "End of Query" in line)
        print(f"  merged {os.path.basename(out)} ({c} blocks)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["prep", "merge"])
    a = ap.parse_args(); prep() if a.cmd == "prep" else merge()
