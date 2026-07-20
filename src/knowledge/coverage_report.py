#!/usr/bin/env python3
"""Cross-check gene_desc.json / gene_alias.json against the Deleteome matrix.

Reports, for the Deleteome file:
  * readout genes (column 2) that now have a description  -- count & %
  * perturbagens (header row 1, non-control) that resolve to a systematic name
    and that now have a description -- count & %
  * any perturbagen that still fails to resolve or lacks a description

Writes data/knowledge/coverage_report.txt and prints the same to stdout.
Run build_gene_alias.py and build_gene_desc.py first.
"""
import os
import json

import sources


def _load(name):
    with open(os.path.join(sources.KNOWLEDGE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def build_report():
    alias = _load("gene_alias.json")
    gene_desc = _load("gene_desc.json")          # flat {systematic: description}
    to_sys = alias["to_systematic"]

    seed = sources.load_seed_descriptions()
    sgd_desc = {}
    for f in sources.iter_sgd_features():
        s = f["systematic"]
        if (s and f["description"] and sources.is_gene_feature(f["feature_type"])
                and s not in sgd_desc):
            sgd_desc[s] = f["description"]

    def classify(g):
        if g in seed:
            return "seed"
        if g in sgd_desc:
            return "sgd_features"
        if g in gene_desc:
            return "go_fallback"
        return "MISSING"

    L = []
    def out(s=""):
        L.append(s)

    out("=" * 72)
    out("YEAST-VECELL KNOWLEDGE COVERAGE REPORT")
    out(f"deleteome: {os.path.basename(sources.resolve('deleteome'))}")
    out("=" * 72)

    # --- readout genes -----------------------------------------------------
    readouts = sorted(sources.deleteome_readout_genes())
    r_have = [g for g in readouts if g in gene_desc]
    r_src = {}
    for g in readouts:
        r_src[classify(g)] = r_src.get(classify(g), 0) + 1
    n_r = len(readouts)
    out("")
    out(f"READOUT GENES (Deleteome column 2 = systematicName): {n_r}")
    out(f"  with a description : {len(r_have)}/{n_r} "
        f"({100.0*len(r_have)/n_r:.2f}%)")
    for k in ("seed", "sgd_features", "go_fallback", "MISSING"):
        if k in r_src:
            out(f"    via {k:14s}: {r_src[k]} "
                f"({100.0*r_src[k]/n_r:.2f}%)")
    missing_r = [g for g in readouts if g not in gene_desc]
    if missing_r:
        out(f"  readouts STILL missing a description ({len(missing_r)}): "
            f"{', '.join(missing_r)}")

    # --- perturbagens ------------------------------------------------------
    exps = sources.deleteome_perturbagens()
    controls = [e for e in exps if e["is_control"]]
    pert = [e for e in exps if not e["is_control"]]
    out("")
    out(f"PERTURBAGEN EXPERIMENTS (Deleteome header row 1): {len(exps)}")
    out(f"  WT controls excluded : {len(controls)} "
        f"({', '.join(c['raw'] for c in controls)})")
    out(f"  perturbation experiments : {len(pert)}")

    resolved, unresolved = [], []
    for e in pert:
        sysname = to_sys.get(e["name"].lower())
        if sysname:
            resolved.append((e, sysname))
        else:
            unresolved.append(e)

    n_p = len(pert)
    have_desc = [(e, s) for (e, s) in resolved if s in gene_desc]
    no_desc = [(e, s) for (e, s) in resolved if s not in gene_desc]

    out(f"  resolve to a systematic name : {len(resolved)}/{n_p} "
        f"({100.0*len(resolved)/n_p:.2f}%)")
    out(f"  resolve AND have a description: {len(have_desc)}/{n_p} "
        f"({100.0*len(have_desc)/n_p:.2f}%)")

    uniq_genes = sorted({s for _, s in resolved})
    uniq_have = sorted({s for _, s in have_desc})
    out(f"  unique perturbagen genes : {len(uniq_genes)} "
        f"(with description: {len(uniq_have)})")

    # source breakdown for the unique resolved perturbagen genes
    p_src = {}
    for g in uniq_genes:
        p_src[classify(g)] = p_src.get(classify(g), 0) + 1
    for k in ("seed", "sgd_features", "go_fallback", "MISSING"):
        if k in p_src:
            out(f"    unique genes via {k:14s}: {p_src[k]}")

    if unresolved:
        out(f"  PERTURBAGENS THAT FAIL TO RESOLVE ({len(unresolved)}):")
        for e in unresolved:
            out(f"    raw='{e['raw']}'  stripped='{e['name']}'")
    else:
        out("  all perturbagens resolved to a systematic name.")

    if no_desc:
        out(f"  RESOLVED BUT NO DESCRIPTION ({len(no_desc)}):")
        for e, s in no_desc:
            out(f"    {e['name']} -> {s}")
    else:
        out("  every resolved perturbagen has a description.")

    out("")
    out("=" * 72)
    return "\n".join(L)


def main():
    report = build_report()
    dst = os.path.join(sources.KNOWLEDGE_DIR, "coverage_report.txt")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    print(report)
    print(f"\n[coverage] wrote {dst}")


if __name__ == "__main__":
    main()
