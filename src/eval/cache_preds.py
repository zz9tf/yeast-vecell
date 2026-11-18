#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse every full-scale prediction file ONCE -> compact <file>.parsed cache.

parse_answer over 245k text blocks x 48 files is the slicing bottleneck. Here we
parse each file exactly once (in parallel across files) and write a sibling
``<pred>.parsed`` with one token per line in retrieval order: ``1`` / ``0`` /
``-`` (abstain/None). Downstream (slice_results, aggregate) can then load ints
directly and skip all regex. Idempotent: skips files whose .parsed is newer.
"""
from __future__ import annotations
import os, sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from score import load_predictions
from aggregate_seeds import TASKS

MODELS = ["qwen14b", "qwen7b", "llama8b", "qwen4b"]
SEEDS = [0, 1, 2]


def _targets():
    jobs = []
    for tk, (stask, ptm, _rtm, _lab, _rcol) in TASKS.items():
        for m in MODELS:
            for s in SEEDS:
                p = ptm.format(m=m, s=s)
                if os.path.exists(p):
                    jobs.append((p, stask))
    return jobs


def _one(job):
    path, stask = job
    cache = path + ".parsed"
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return (path, "skip", 0)
    preds = load_predictions(path, stask)
    with open(cache, "w") as f:
        f.write("\n".join("-" if p is None else str(p) for p in preds))
    return (path, "ok", len(preds))


def load_parsed(path):
    """Read <path>.parsed -> list[Optional[int]] (None for '-')."""
    with open(path + ".parsed") as f:
        return [None if t == "-" else int(t) for t in f.read().split("\n") if t != ""]


def main():
    jobs = _targets()
    print(f"parsing {len(jobs)} prediction files (parallel)...")
    with Pool(min(len(jobs), os.cpu_count() or 8)) as pool:
        for path, status, n in pool.imap_unordered(_one, jobs):
            print(f"  [{status}] {os.path.basename(path)} ({n})")
    print("cache_preds done")


if __name__ == "__main__":
    main()
