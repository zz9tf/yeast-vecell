#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute the three biological decompositions for T1a-DE / T1b-DIR (task_definitions.md
Task 1 'biology decomposition' section) using real assets + real cached predictions.

Decomp1: STRING hop distance (results_close_gene.json: direct_neighbors=1hop, two_hop_neighbors=2hop)
Decomp2: Gasch 2000 ESR gene set (data/knowledge/esr_genes_gasch2000.json, from Gasch Lab's own
         "updated ESR gene sets" page, ORIGINAL ESR GROUPS column = iESR+PAC+RP = 868 genes,
         matches literature 283 induced + 585 repressed exactly)
Decomp3: CYC2008-lineage complex co-membership. The MiniShare CYC2008_complex.tab was a corrupted
         download (S3 directory-listing HTML) and wodaklab.org is unreachable (ECONNREFUSED from
         both this node and the WebFetch tool) -- first pass substituted EBI Complex Portal's yeast
         complexome (successor curated with SGD/UniProt, explicitly builds on CYC2008). The user
         then located the real CYC2008 data: NAR paper Pu et al. 2009 (Oxford NAR manuscript
         gkn1005) Supplementary Data zip, file `nar-02139-s-2008-File005.xls` sheet
         `CYC2008_complex` -- the *original* 1627-gene/408-complex catalogue (matches the paper's
         "408 manually curated complexes" exactly). Archived as
         data/knowledge/CYC2008_complex_raw.xls + data/knowledge/cyc2008_complex_members.json.
         Rerun with the real data reproduces the same qualitative finding as the Complex Portal
         substitute (co-complex subset scores much worse than cross-complex on both DE/DIR, all 4
         models) -- cross-validates that the earlier result wasn't a Complex Portal substitution
         artifact.

Uses regex-based extraction of (pert,gene) test_case order (NOT json.load on the 278MB/912MB
retrieval JSONs) + load_parsed() .parsed caches for O(1) prediction loading.
"""
import csv, json, os, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402
from cache_preds import load_parsed  # noqa: E402

R = os.path.join(REPO, "data", "runs")
KNOW = os.path.join(REPO, "data", "knowledge")
MODELS = ["qwen14b", "qwen7b", "qwen4b", "llama8b"]
SEEDS = [0, 1, 2]

TASKS = {
    "T1a-DE":  ("de",  f"{R}/DE_pred_{{m}}_s{{s}}.txt",  f"{R}/DE_retr_full_s{{s}}.json",  f"{R}/deleteome_DE.csv"),
    "T1b-DIR": ("dir", f"{R}/DIR_pred_{{m}}_s{{s}}.txt", f"{R}/DIR_retr_full_s{{s}}.json", f"{R}/deleteome_DIR.csv"),
}

_RE = re.compile(r'"test_case":\s*\{\s*"pert":\s*"([^"]+)",\s*"gene":\s*"([^"]+)"', re.DOTALL)


def extract_pg(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return [(m.group(1), m.group(2)) for m in _RE.finditer(text)]


def load_label_map(labels_csv):
    m = {}
    with open(labels_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m[(row["pert"], row["gene"])] = int(row["label"])
    return m


def ms(vals):
    return st.mean(vals), (st.pstdev(vals) if len(vals) > 1 else 0.0)


# ---------------- knowledge assets ----------------

def load_string_hops():
    return json.load(open(os.path.join(KNOW, "results_close_gene.json"), encoding="utf-8"))


def load_esr():
    return set(json.load(open(os.path.join(KNOW, "esr_genes_gasch2000.json"), encoding="utf-8")).keys())


def load_complex_members():
    """Real CYC2008 (Pu et al. 2009, File005.xls/CYC2008_complex sheet, 1627 genes/408 complexes).
    Complex Portal substitute (complex_members_complexportal.json) kept on disk for cross-check."""
    d = json.load(open(os.path.join(KNOW, "cyc2008_complex_members.json"), encoding="utf-8"))
    return {g: set(v) for g, v in d.items()}


def mask_decomp1(pg, string_hops):
    direct, indirect = [], []
    for pert, gene in pg:
        info = string_hops.get(pert)
        if info is None:
            direct.append(False); indirect.append(False); continue
        d1 = gene in info.get("direct_neighbors", [])
        d2 = (not d1) and gene in info.get("two_hop_neighbors", [])
        direct.append(d1); indirect.append(d2)
    return {"direct(1hop)": direct, "indirect(2hop)": indirect}


def mask_decomp2(pg, esr):
    is_esr = [gene in esr for _, gene in pg]
    return {"ESR": is_esr, "non-ESR": [not x for x in is_esr]}


def mask_decomp3(pg, complex_members):
    co = []
    for pert, gene in pg:
        cp = complex_members.get(pert)
        cg = complex_members.get(gene)
        co.append(bool(cp and cg and (cp & cg)))
    return {"co-complex": co, "cross-complex/none": [not x for x in co]}


def sub_metrics(preds, truth, mask, task):
    p = [x for x, m in zip(preds, mask) if m]
    t = [x for x, m in zip(truth, mask) if m]
    return compute_metrics(p, t, task)


def run(decomp_name, mask_fn, tasks=("T1a-DE", "T1b-DIR")):
    print(f"\n########## {decomp_name} ##########")
    out = {}
    for tk in tasks:
        stask, ptm, rtm, lab = TASKS[tk]
        print(f"\n===== {tk} =====")
        seed_pg = {s: extract_pg(rtm.format(s=s)) for s in SEEDS}
        label_map = load_label_map(lab)
        seed_truth = {s: [label_map.get(pg) for pg in seed_pg[s]] for s in SEEDS}
        seed_masks = {s: mask_fn(seed_pg[s]) for s in SEEDS}
        subsets = list(next(iter(seed_masks.values())).keys())
        n0 = {sub: sum(seed_masks[SEEDS[0]][sub]) for sub in subsets}
        print("  subset sizes (seed0, raw case count before truth-filter):",
              ", ".join(f"{k}={v}" for k, v in n0.items()))
        out[tk] = {"sizes": n0, "models": {}}
        for m in MODELS:
            per = {sub: {"macro_f1": [], "mcc": [], "n": []} for sub in subsets}
            ok = True
            for s in SEEDS:
                p = ptm.format(m=m, s=s)
                if not os.path.exists(p + ".parsed"):
                    ok = False; break
                preds = load_parsed(p)
                truth = seed_truth[s]
                for sub in subsets:
                    mk = seed_masks[s][sub]
                    met = sub_metrics(preds, truth, mk, stask)
                    per[sub]["macro_f1"].append(met["macro_f1"])
                    per[sub]["mcc"].append(met["mcc"])
                    per[sub]["n"].append(met["n_total"])
            if not ok:
                print(f"  {m:10s} (preds missing)"); continue
            row = {}
            line = f"  {m:10s}"
            for sub in subsets:
                f1m, f1s = ms(per[sub]["macro_f1"])
                mccm, mccs = ms(per[sub]["mcc"])
                nmean = st.mean(per[sub]["n"])
                row[sub] = {"macro_f1": (f1m, f1s), "mcc": (mccm, mccs), "n": nmean}
                line += f"  | {sub}: F1={f1m:.3f}±{f1s:.3f} MCC={mccm:.3f}±{mccs:.3f} n~{nmean:.0f}"
            print(line)
            out[tk]["models"][m] = row
    return out


if __name__ == "__main__":
    string_hops = load_string_hops()
    esr = load_esr()
    complex_members = load_complex_members()

    r1 = run("Decomp1: STRING hop (1-hop direct vs 2-hop indirect)",
             lambda pg: mask_decomp1(pg, string_hops))
    r2 = run("Decomp2: Gasch2000 ESR vs non-ESR",
             lambda pg: mask_decomp2(pg, esr))
    r3 = run("Decomp3: CYC2008-lineage (Complex Portal) co-complex vs not",
             lambda pg: mask_decomp3(pg, complex_members))

    json.dump({"decomp1": r1, "decomp2": r2, "decomp3": r3},
              open(os.path.join(R, "decomp123.json"), "w"), indent=2)
    print("\nwrote", os.path.join(R, "decomp123.json"))
