#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score DE/DIR predictions against ground truth and print metrics.

VCWorld ships no scorer; this fills that gap. It parses the closed-set final
answer out of each model response in a ``predictions.txt`` (as written by
``stages/infer.py`` / ``infer_api.py``), joins it BY ORDER to the retrieval
JSON's ``test_case`` list (prompts are generated, run, and written in retrieval
order), looks up the true label from the DE/DIR CSV, and reports:

  answered% (non-abstain), overall accuracy (abstain = wrong), and — over the
  answered subset — macro-F1 and MCC (the metrics that matter given the strong
  class imbalance; see docs/task_decomposition_analysis.md).

Final-answer vocabulary (verbatim from support/{DE,DIR}_template.py, kept
identical by the A/B prompt variants):
  DE : "Yes. Deletion of ... differential expression"  -> 1
       "No. Deletion of ... does not differentially express" -> 0
  DIR: "Increase. ..." -> 1 ; "Decrease. ..." -> 0
  both: "insufficient evidence" -> abstain

Usage:
  python src/eval/score.py --task de \
      --predictions out/DE_pred.txt --retrieval out/DE_retr.json \
      --labels-csv out/deleteome_DE.csv [--json out/DE_score.json]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from typing import Dict, List, Optional, Tuple

PROMPT_SEPARATOR = "=" * 80


# ---- parsing the model's closed-set final answer ------------------------------

# Each entry: (label, list of regex patterns). We take the pattern whose LAST
# match occurs latest in the response (robust to keywords used mid-reasoning).
_PATTERNS = {
    "de": [
        (1, [r"results in differential expression", r"\byes[.,]?\s+deletion"]),
        (0, [r"does not differentially express", r"\bno[.,]?\s+deletion"]),
        (None, [r"insufficient evidence"]),
    ],
    "dir": [
        (1, [r"results in an increase", r"\bincrease[.:]\s+deletion", r"\bincrease\b"]),
        (0, [r"results in a decrease", r"\bdecrease[.:]\s+deletion", r"\bdecrease\b"]),
        (None, [r"insufficient evidence"]),
    ],
    # Task2 growth phenotype (DE-analog: does deletion change growth y/n).
    # NB: "causes a growth phenotype" also appears inside the *insufficient* sentence,
    # so label-1 keys only on the affirmative "Yes. Deletion" starter.
    "growth": [
        (1, [r"\byes[.,]?\s+deletion"]),
        (0, [r"does not cause a growth phenotype", r"\bno[.,]?\s+deletion"]),
        (None, [r"insufficient evidence"]),
    ],
    # Task2 growth direction (sensitive/resistant).
    "growth_dir": [
        (1, [r"more resistant", r"\bresistant[.:]\s+deletion", r"\bresistant\b"]),
        (0, [r"more sensitive", r"\bsensitive[.:]\s+deletion", r"\bsensitive\b"]),
        (None, [r"insufficient evidence"]),
    ],
}


def parse_answer(response: str, task: str) -> Optional[int]:
    """Return 1 / 0 / None(abstain or unparseable) for a model response."""
    text = response.lower()
    best_pos, best_label = -1, "UNPARSED"
    for label, patterns in _PATTERNS[task]:
        for pat in patterns:
            for m in re.finditer(pat, text):
                if m.start() > best_pos:
                    best_pos, best_label = m.start(), label
    return None if best_label in (None, "UNPARSED") else best_label


def _split_blocks(pred_text: str) -> List[str]:
    return [b.strip() for b in pred_text.split(PROMPT_SEPARATOR) if b.strip()]


def load_predictions(path: str, task: str) -> List[Optional[int]]:
    """Ordered list of parsed predictions (one per prompt block)."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    preds: List[Optional[int]] = []
    for block in _split_blocks(content):
        m = re.search(r"---\s*Query for .*?---(.*?)(?:---\s*End of Query|$)",
                      block, re.DOTALL)
        body = m.group(1) if m else block
        if "ERROR" in body[:80] and "insufficient" not in body.lower():
            preds.append(None)  # parse/generation error block
            continue
        preds.append(parse_answer(body, task))
    return preds


# ---- ground truth -------------------------------------------------------------

def load_truth(retrieval_json: str, labels_csv: str,
               readout_col: str = "gene") -> List[Optional[int]]:
    """True label per test_case, in retrieval order (None if not found).

    ``readout_col`` names the readout column in the labels CSV (Task1 = "gene",
    Task2 = "context"); the retrieval JSON always stores it under "gene".
    """
    import csv
    label_map: Dict[Tuple[str, str], int] = {}
    with open(labels_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label_map[(row["pert"], row[readout_col])] = int(row["label"])
    with open(retrieval_json, "r", encoding="utf-8") as f:
        retrieval = json.load(f)
    truth: List[Optional[int]] = []
    for item in retrieval:
        tc = item["test_case"]
        truth.append(label_map.get((str(tc["pert"]), str(tc["gene"]))))
    return truth


# ---- metrics (manual, no sklearn dependency) ----------------------------------

def _f1(tp: int, fp: int, fn: int) -> float:
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else 0.0


def compute_metrics(preds: List[Optional[int]], truth: List[Optional[int]],
                    task: str) -> Dict:
    n = min(len(preds), len(truth))
    preds, truth = preds[:n], truth[:n]
    pos_name, neg_name = {
        "de": ("DE", "non-DE"),
        "dir": ("Increase", "Decrease"),
        "growth": ("phenotype", "no-phenotype"),
        "growth_dir": ("Resistant", "Sensitive"),
    }.get(task, ("pos", "neg"))

    # overall accuracy: abstain / missing-truth handling
    scored = [(p, t) for p, t in zip(preds, truth) if t is not None]
    n_total = len(scored)
    answered = [(p, t) for p, t in scored if p is not None]
    n_answered = len(answered)

    acc_overall = sum(1 for p, t in scored if p == t) / n_total if n_total else 0.0

    # confusion on answered subset (class 1 = positive)
    tp = sum(1 for p, t in answered if p == 1 and t == 1)
    tn = sum(1 for p, t in answered if p == 0 and t == 0)
    fp = sum(1 for p, t in answered if p == 1 and t == 0)
    fn = sum(1 for p, t in answered if p == 0 and t == 1)

    f1_pos = _f1(tp, fp, fn)
    f1_neg = _f1(tn, fn, fp)
    macro_f1 = (f1_pos + f1_neg) / 2
    acc_answered = (tp + tn) / n_answered if n_answered else 0.0

    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn - fp * fn) / denom) if denom else 0.0

    base_rate = sum(1 for _, t in scored if t == 1) / n_total if n_total else 0.0
    return {
        "task": task, "n_total": n_total, "n_answered": n_answered,
        "answered_pct": round(100 * n_answered / n_total, 2) if n_total else 0.0,
        "acc_overall": round(acc_overall, 4),
        "acc_answered": round(acc_answered, 4),
        "macro_f1": round(macro_f1, 4),
        "mcc": round(mcc, 4),
        "f1_pos": round(f1_pos, 4), "f1_neg": round(f1_neg, 4),
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "positive_base_rate": round(base_rate, 4),
        "pos_class": pos_name, "neg_class": neg_name,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score DE/DIR/growth predictions")
    ap.add_argument("--task", required=True, choices=["de", "dir", "growth", "growth_dir"])
    ap.add_argument("--predictions", required=True, help="predictions.txt from infer")
    ap.add_argument("--retrieval", required=True, help="retrieval JSON used to build the prompts")
    ap.add_argument("--labels-csv", required=True, help="CSV with the true labels")
    ap.add_argument("--readout-col", default="gene",
                    help="readout column in the labels CSV (Task1='gene', Task2='context')")
    ap.add_argument("--json", default=None, help="Optional path to write metrics JSON")
    args = ap.parse_args(argv)

    preds = load_predictions(args.predictions, args.task)
    truth = load_truth(args.retrieval, args.labels_csv, readout_col=args.readout_col)
    if len(preds) != len(truth):
        print(f"[score] NOTE: #predictions ({len(preds)}) != #test_cases "
              f"({len(truth)}); scoring the first {min(len(preds), len(truth))} "
              f"by order.")
    m = compute_metrics(preds, truth, args.task)

    print(f"\n===== {args.task.upper()} score =====")
    print(f"cases: {m['n_total']}  answered: {m['n_answered']} "
          f"({m['answered_pct']}%)  positive base-rate: {m['positive_base_rate']}")
    print(f"Accuracy (overall, abstain=wrong): {m['acc_overall']}")
    print(f"Accuracy (answered only):          {m['acc_answered']}")
    print(f"Macro-F1: {m['macro_f1']}   MCC: {m['mcc']}   "
          f"(F1 {m['pos_class']}={m['f1_pos']}, {m['neg_class']}={m['f1_neg']})")
    print(f"confusion (pos={m['pos_class']}): {m['confusion']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
