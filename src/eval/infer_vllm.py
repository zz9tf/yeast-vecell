#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vLLM-based inference over prompts.txt file(s) — fast path for stages/infer.py.

Parses the block format ([Start of Prompt]…[End of Prompt] system +
[Start of Input]…[End of Output] user), runs via vLLM ``LLM.chat`` (continuous
batching), writes predictions.txt in the format score.py expects.

Two modes:
  single:    --prompts P --out O
  manifest:  --manifest M   (each line: "<prompts_path>\t<out_path>"; model
             loaded ONCE, all jobs run in sequence — used by the 16-GPU dispatcher)

Env for this cluster (no system CUDA; driver 12.8; flashinfer removed):
  CUDA_HOME=<vllm env>  VLLM_USE_V1=0  VLLM_ATTENTION_BACKEND=FLASH_ATTN
"""

from __future__ import annotations

import argparse
import re
import time
from typing import List, Optional, Tuple

PROMPT_SEPARATOR = "=" * 80


def _parse_block(block: str):
    hm = re.search(r"===\s*(Prompt\s*\d+).*?===", block)
    header = hm.group(1).strip() if hm else "Unknown Prompt"
    sm = re.search(r"\[Start of Prompt\](.*?)\[End of Prompt\]", block, re.DOTALL)
    um = re.search(r"\[Start of Input\](.*?)\[End of Output\]", block, re.DOTALL)
    if not sm or not um:
        return None, None, header, "markers not found"
    return sm.group(1).strip(), um.group(0).strip(), header, None


def _load(prompts_path: str):
    with open(prompts_path, "r", encoding="utf-8") as f:
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
    return convs, meta


def run_one(llm, sp, prompts_path: str, out_path: str) -> None:
    convs, meta = _load(prompts_path)
    if not convs:
        print(f"[infer_vllm] no valid prompts in {prompts_path}")
        open(out_path, "w").close()
        return
    t0 = time.time()
    outs = llm.chat(convs, sp)
    texts = [o.outputs[0].text for o in outs]
    dt = time.time() - t0
    print(f"[infer_vllm] {out_path}: {len(texts)} gen in {dt:.1f}s "
          f"= {len(texts)/dt:.2f} gen/s")
    results, gi = [], 0
    for m in meta:
        body = (f"ERROR during parsing: {m['err']}" if m["err"]
                else texts[gi].strip())
        if not m["err"]:
            gi += 1
        results.append(f"--- Query for {m['header']} ---\n{body}\n"
                       f"--- End of Query for {m['header']} ---\n\n{PROMPT_SEPARATOR}\n\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(results)


def _jobs(args) -> List[Tuple[str, str]]:
    if args.manifest:
        jobs = []
        with open(args.manifest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                p, o = line.split("\t")
                jobs.append((p, o))
        return jobs
    return [(args.prompts, args.out)]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local snapshot dir")
    ap.add_argument("--prompts", help="single-mode prompts file")
    ap.add_argument("--out", help="single-mode output file")
    ap.add_argument("--manifest", help="manifest: lines of '<prompts>\\t<out>'")
    ap.add_argument("--max-model-len", type=int, default=6144)
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--enforce-eager", action="store_true",
                    help="disable CUDA graphs (slower; use only if graph capture fails)")
    args = ap.parse_args(argv)

    from vllm import LLM, SamplingParams
    llm = LLM(model=args.model, dtype="bfloat16", gpu_memory_utilization=args.gpu_mem,
              max_model_len=args.max_model_len, seed=args.seed,
              enforce_eager=args.enforce_eager)
    sp = SamplingParams(temperature=args.temperature, top_p=args.top_p,
                        max_tokens=args.max_new_tokens, seed=args.seed)

    for prompts_path, out_path in _jobs(args):
        run_one(llm, sp, prompts_path, out_path)
    print("[infer_vllm] ALL JOBS DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
