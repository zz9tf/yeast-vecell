#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vLLM-based inference over a prompts.txt (drop-in fast path for stages/infer.py).

Parses the same block format ([Start of Prompt]…[End of Prompt] system +
[Start of Input]…[End of Output] user), runs them through vLLM's continuous-batching
``LLM.chat`` (10-50x faster than HF generate at scale), and writes predictions.txt
in the exact format score.py expects.

Usage:
  python src/eval/infer_vllm.py --model <local_snapshot_dir> \
      --prompts prompts.txt --out pred.txt \
      [--max-model-len 6144] [--max-new-tokens 1024] [--gpu-mem 0.90]
"""

from __future__ import annotations

import argparse
import re
import time
from typing import List, Optional

PROMPT_SEPARATOR = "=" * 80


def _parse_block(block: str):
    hm = re.search(r"===\s*(Prompt\s*\d+).*?===", block)
    header = hm.group(1).strip() if hm else "Unknown Prompt"
    sm = re.search(r"\[Start of Prompt\](.*?)\[End of Prompt\]", block, re.DOTALL)
    um = re.search(r"\[Start of Input\](.*?)\[End of Output\]", block, re.DOTALL)
    if not sm or not um:
        return None, None, header, "markers not found"
    return sm.group(1).strip(), um.group(0).strip(), header, None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local snapshot dir")
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-model-len", type=int, default=6144)
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    from vllm import LLM, SamplingParams

    with open(args.prompts, "r", encoding="utf-8") as f:
        blocks = [b.strip() for b in f.read().split(PROMPT_SEPARATOR) if b.strip()]

    convs, meta = [], []
    for b in blocks:
        sysp, userp, header, err = _parse_block(b)
        if err:
            meta.append({"header": header, "err": err})
            continue
        convs.append([{"role": "system", "content": sysp},
                      {"role": "user", "content": userp}])
        meta.append({"header": header, "err": None})
    if not convs:
        print("No valid prompts")
        return 0

    llm = LLM(model=args.model, dtype="bfloat16", gpu_memory_utilization=args.gpu_mem,
              max_model_len=args.max_model_len, seed=args.seed)
    sp = SamplingParams(temperature=args.temperature, top_p=args.top_p,
                        max_tokens=args.max_new_tokens, seed=args.seed)

    t0 = time.time()
    outs = llm.chat(convs, sp)
    dt = time.time() - t0
    texts = [o.outputs[0].text for o in outs]
    print(f"[infer_vllm] {len(texts)} generations in {dt:.1f}s "
          f"= {len(texts)/dt:.2f} gen/s")

    results, gi = [], 0
    for m in meta:
        if m["err"]:
            body = f"ERROR during parsing: {m['err']}"
        else:
            body = texts[gi].strip(); gi += 1
        results.append(f"--- Query for {m['header']} ---\n{body}\n"
                       f"--- End of Query for {m['header']} ---\n\n{PROMPT_SEPARATOR}\n\n")
    with open(args.out, "w", encoding="utf-8") as f:
        f.writelines(results)
    print(f"Saved outputs: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
