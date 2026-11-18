#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Same four T1 biological decompositions as decomp_bio_t1.py (+ slice_results.py's
TF/non-TF axis), but for the GAT baseline instead of the LLMs.

Unlike the LLM path, GAT never had per-case predictions cached -- gat_baseline.py
only ever dumped the aggregate test_metrics. This reads the per-case
[{pert,gene,true,pred}] dumps written by `gat_baseline.py --dump-preds ...`
(added alongside this script), available under
data/runs/gat_baseline/preds/gat_{de,dir}_s{seed}.json for whichever seeds have
been (re)run with --dump-preds.

Note: GAT's train/test split comes straight from the CSV's `split` column and
does NOT depend on `seed` (seed only affects model init / minibatch shuffling),
so the (pert,gene) test-case SET is identical across seeds -- we use seed 0's
case list to build all decomposition masks and apply them per-seed.

Usage: python src/eval/decomp_bio_t1_gat.py
Writes data/runs/decomp_gat.json.
"""
import json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402
from decomp_bio_t1 import (  # noqa: E402
    load_string_hops, load_esr, load_complex_members,
    mask_decomp1, mask_decomp2, mask_decomp3,
)

R = os.path.join(REPO, "data", "runs")
KNOW = os.path.join(REPO, "data", "knowledge")
PREDS_DIR = os.path.join(R, "gat_baseline", "preds")

TASKS = {"T1a-DE": ("de", "gat_de_s{s}.json"), "T1b-DIR": ("dir", "gat_dir_s{s}.json")}


def load_tf_targets():
    return set(json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8")))


def mask_decomp0(pg, tf):
    is_tf = [pert in tf for pert, _ in pg]
    return {"TF-deletion": is_tf, "non-TF": [not x for x in is_tf]}


def available_seeds(fname_tmpl):
    seeds = []
    for s in (0, 1, 2):
        if os.path.exists(os.path.join(PREDS_DIR, fname_tmpl.format(s=s))):
            seeds.append(s)
    return seeds


def load_cases(fname_tmpl, s):
    with open(os.path.join(PREDS_DIR, fname_tmpl.format(s=s)), encoding="utf-8") as f:
        return json.load(f)


def ms(vals):
    return st.mean(vals), (st.pstdev(vals) if len(vals) > 1 else 0.0)


def run_decomp(name, mask_fn):
    print(f"\n########## {name} (GAT) ##########")
    out = {}
    for tk, (stask, fname_tmpl) in TASKS.items():
        seeds = available_seeds(fname_tmpl)
        if not seeds:
            print(f"  {tk}: NO per-case dumps yet (run gat_baseline.py --task "
                  f"{stask} --seed S --dump-preds ...)")
            out[tk] = None
            continue
        cases0 = load_cases(fname_tmpl, seeds[0])
        pg = [(c["pert"], c["gene"]) for c in cases0]
        truth = [c["true"] for c in cases0]
        mask = mask_fn(pg)
        subsets = list(mask.keys())
        n0 = {sub: sum(mask[sub]) for sub in subsets}
        print(f"\n===== {tk} (seeds={seeds}) subset sizes: "
              + ", ".join(f"{k}={v}" for k, v in n0.items()))
        per = {sub: {"macro_f1": [], "mcc": [], "n": []} for sub in subsets}
        for s in seeds:
            cases = load_cases(fname_tmpl, s)
            preds = [c["pred"] for c in cases]
            for sub in subsets:
                mk = mask[sub]
                p = [x for x, m in zip(preds, mk) if m]
                t = [x for x, m in zip(truth, mk) if m]
                met = compute_metrics(p, t, stask)
                per[sub]["macro_f1"].append(met["macro_f1"])
                per[sub]["mcc"].append(met["mcc"])
                per[sub]["n"].append(met["n_total"])
        row = {}
        line = "  GAT      "
        for sub in subsets:
            f1m, f1s = ms(per[sub]["macro_f1"])
            mccm, mccs = ms(per[sub]["mcc"])
            nmean = st.mean(per[sub]["n"])
            row[sub] = {"macro_f1": (round(f1m, 4), round(f1s, 4)),
                        "mcc": (round(mccm, 4), round(mccs, 4)), "n": nmean}
            line += f"  | {sub}: F1={f1m:.3f}±{f1s:.3f} MCC={mccm:.3f}±{mccs:.3f} n~{nmean:.0f}"
        print(line)
        out[tk] = {"seeds": seeds, "sizes": n0, "row": row}
    return out


if __name__ == "__main__":
    tf = load_tf_targets()
    string_hops = load_string_hops()
    esr = load_esr()
    complex_members = load_complex_members()

    r0 = run_decomp("Decomp0: TF-deletion vs non-TF", lambda pg: mask_decomp0(pg, tf))
    r1 = run_decomp("Decomp1: STRING hop (1-hop direct vs 2-hop indirect)",
                    lambda pg: mask_decomp1(pg, string_hops))
    r2 = run_decomp("Decomp2: Gasch2000 ESR vs non-ESR", lambda pg: mask_decomp2(pg, esr))
    r3 = run_decomp("Decomp3: CYC2008 co-complex vs cross-complex/none",
                    lambda pg: mask_decomp3(pg, complex_members))

    json.dump({"decomp0": r0, "decomp1": r1, "decomp2": r2, "decomp3": r3},
              open(os.path.join(R, "decomp_gat.json"), "w"), indent=2)
    print("\nwrote", os.path.join(R, "decomp_gat.json"))
