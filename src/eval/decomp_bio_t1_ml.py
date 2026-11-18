#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Same four T1 biological decompositions as decomp_bio_t1.py (LLM path), but
for the four traditional-ML baselines (GAT/GenKI/KGE-TGI/MultiXrank).

Generalizes decomp_bio_t1_gat.py (which only covered GAT) to all four methods.
Reads the per-case [{pert,gene,true,pred}] dumps written by each baseline's
--dump-preds flag, under data/runs/{method}_baseline/preds/{method}_{de,dir}_s{seed}.json
(produced by data/run_decomp_ml_preds.sh, same seeds as the already-recorded
aggregate scores in data/runs/{method}_baseline/*_seed{seed}.json).

Note: each method's train/test split comes straight from the CSV's `split`
column and does NOT depend on `seed` (seed only affects model init / minibatch
shuffling / XGBoost's random_state), so the (pert,gene) test-case SET is
identical across seeds for a given method -- we use the first available seed's
case list to build all decomposition masks and apply them per-seed.

Usage: python src/eval/decomp_bio_t1_ml.py
Writes data/runs/decomp_ml.json.
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

METHODS = {
    "GAT":        ("gat_baseline",        "gat_{t}_s{{s}}.json"),
    "GenKI":      ("genki_baseline",      "genki_{t}_s{{s}}.json"),
    "KGE-TGI":    ("kge_tgi_baseline",    "kge_{t}_s{{s}}.json"),
    "MultiXrank": ("multixrank_baseline", "multixrank_{t}_s{{s}}.json"),
}
TASKS = {"T1a-DE": "de", "T1b-DIR": "dir"}


def load_tf_targets():
    return set(json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8")))


def mask_decomp0(pg, tf):
    is_tf = [pert in tf for pert, _ in pg]
    return {"TF-deletion": is_tf, "non-TF": [not x for x in is_tf]}


def available_seeds(preds_dir, fname_tmpl):
    seeds = []
    for s in (0, 1, 2):
        if os.path.exists(os.path.join(preds_dir, fname_tmpl.format(s=s))):
            seeds.append(s)
    return seeds


def load_cases(preds_dir, fname_tmpl, s):
    with open(os.path.join(preds_dir, fname_tmpl.format(s=s)), encoding="utf-8") as f:
        return json.load(f)


def ms(vals):
    return st.mean(vals), (st.pstdev(vals) if len(vals) > 1 else 0.0)


def run_decomp(name, mask_fn):
    print(f"\n########## {name} ##########")
    out = {}
    for tk, stask in TASKS.items():
        out[tk] = {}
        print(f"\n===== {tk} =====")
        for method, (subdir, tmpl_base) in METHODS.items():
            preds_dir = os.path.join(R, subdir, "preds")
            fname_tmpl = tmpl_base.format(t=stask)
            seeds = available_seeds(preds_dir, fname_tmpl)
            if not seeds:
                print(f"  {method:10s}: NO per-case dumps yet")
                out[tk][method] = None
                continue
            cases0 = load_cases(preds_dir, fname_tmpl, seeds[0])
            pg = [(c["pert"], c["gene"]) for c in cases0]
            truth = [c["true"] for c in cases0]
            mask = mask_fn(pg)
            subsets = list(mask.keys())
            n0 = {sub: sum(mask[sub]) for sub in subsets}
            per = {sub: {"macro_f1": [], "mcc": [], "n": []} for sub in subsets}
            for s in seeds:
                cases = load_cases(preds_dir, fname_tmpl, s)
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
            line = f"  {method:10s} (seeds={seeds})"
            for sub in subsets:
                f1m, f1s = ms(per[sub]["macro_f1"])
                mccm, mccs = ms(per[sub]["mcc"])
                nmean = st.mean(per[sub]["n"])
                row[sub] = {"macro_f1": (round(f1m, 4), round(f1s, 4)),
                            "mcc": (round(mccm, 4), round(mccs, 4)), "n": nmean}
                line += f"  | {sub}: F1={f1m:.3f}±{f1s:.3f} MCC={mccm:.3f}±{mccs:.3f} n~{nmean:.0f}"
            print(line)
            out[tk][method] = {"seeds": seeds, "sizes": n0, "row": row}
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
              open(os.path.join(R, "decomp_ml.json"), "w"), indent=2)
    print("\nwrote", os.path.join(R, "decomp_ml.json"))
