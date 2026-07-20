#!/usr/bin/env python3
"""Build data/knowledge/gene_desc.json -> {systematic_ORF: description_text}.

Priority per gene:
  1. seed prose      gene_function_descriptions.csv  (rich SGD prose, ~4554)
  2. SGD one-liner   SGD_features.tab column 16       (full-genome top-up)
  3. GO fallback     "STD; GO: <BP>; <MF>; <CC>"  from the SGD GAF, term names
                     via the UniProt proteome tsv

Key universe = every gene-like systematic with an SGD description, UNION the
Deleteome readout genes, UNION the resolved Deleteome perturbagen systematics,
so both roles a gene can play (readout and perturbagen) are always covered.

Requires gene_alias.json (run build_gene_alias.py first).
"""
import os
import json
import datetime

import sources

MAX_TERMS_PER_ASPECT = 12


def _load_alias():
    p = os.path.join(sources.KNOWLEDGE_DIR, "gene_alias.json")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _go_fallback_string(key, alias, gaf_idx, go_names):
    """Synthesise 'STANDARD; GO: <BP>; <MF>; <CC>' for a gene with no desc."""
    std = alias["systematic_to_standard"].get(key, key)
    # candidate lookup identifiers into the GAF index
    lookups = [key]
    if key in alias["systematic_to_standard"]:
        lookups.append(alias["systematic_to_standard"][key])
    if key in alias["systematic_to_sgdid"]:
        lookups.append(alias["systematic_to_sgdid"][key])
    lookups.extend(alias["systematic_to_aliases"].get(key, []))

    merged = {"P": set(), "F": set(), "C": set()}
    for lk in lookups:
        b = gaf_idx.get(lk.lower())
        if b:
            for asp in "PFC":
                merged[asp].update(b[asp])

    def names(asp):
        terms = sorted(go_names.get(g, g) for g in merged[asp])
        return terms[:MAX_TERMS_PER_ASPECT]

    bp, mf, cc = names("P"), names("F"), names("C")
    if not (bp or mf or cc):
        return f"{std}; uncharacterized (no SGD description or GO annotation available)"
    seg = "; ".join([
        ", ".join(bp) if bp else "NA",
        ", ".join(mf) if mf else "NA",
        ", ".join(cc) if cc else "NA",
    ])
    return f"{std}; GO: {seg}"


def build():
    alias = _load_alias()
    seed = sources.load_seed_descriptions()

    # SGD one-line descriptions keyed by systematic name (gene features only).
    sgd_desc = {}
    for f in sources.iter_sgd_features():
        s = f["systematic"]
        if (s and f["description"] and sources.is_gene_feature(f["feature_type"])
                and s not in sgd_desc):
            sgd_desc[s] = f["description"]

    readouts = sources.deleteome_readout_genes()
    perts = sources.deleteome_perturbagens()
    to_sys = alias["to_systematic"]
    pert_systematics = {
        to_sys[p["name"].lower()]
        for p in perts
        if not p["is_control"] and p["name"].lower() in to_sys
    }

    universe = set(sgd_desc) | set(seed) | readouts | pert_systematics

    gaf_idx = sources.load_gaf_index()
    go_names = sources.load_go_name_map()

    gene_desc = {}
    src_count = {"seed": 0, "sgd_features": 0, "go_fallback": 0,
                 "go_fallback_empty": 0}
    for g in sorted(universe):
        if g in seed:
            gene_desc[g] = seed[g]
            src_count["seed"] += 1
        elif g in sgd_desc:
            gene_desc[g] = sgd_desc[g]
            src_count["sgd_features"] += 1
        else:
            s = _go_fallback_string(g, alias, gaf_idx, go_names)
            gene_desc[g] = s
            if "uncharacterized (no SGD" in s:
                src_count["go_fallback_empty"] += 1
            else:
                src_count["go_fallback"] += 1

    meta = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "n_genes": len(gene_desc),
        "by_source": src_count,
        "seed_source": os.path.basename(sources.resolve("seed_desc")),
        "sgd_source": os.path.basename(sources.resolve("sgd_features")),
        "gaf_source": os.path.basename(sources.resolve("gaf")),
        "go_name_terms": len(go_names),
        "go_name_source": ("uniprot_UP000002311.tsv" if go_names
                           else "UNAVAILABLE (fallback shows raw GO ids)"),
    }
    return gene_desc, meta


def main():
    gene_desc, meta = build()
    os.makedirs(sources.KNOWLEDGE_DIR, exist_ok=True)
    # gene_desc.json is a flat {systematic_ORF: description} map (drop-in for a
    # VCWorld-style gene_output.json); provenance goes to a sidecar.
    dst = os.path.join(sources.KNOWLEDGE_DIR, "gene_desc.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(gene_desc, fh, ensure_ascii=False, sort_keys=True, indent=1)
    with open(os.path.join(sources.KNOWLEDGE_DIR, "gene_desc.meta.json"),
              "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, sort_keys=True, indent=1)
    print(f"[gene_desc] wrote {dst}")
    print(f"[gene_desc] total genes : {meta['n_genes']}")
    for k, v in meta["by_source"].items():
        print(f"[gene_desc]   {k:20s}: {v}")
    print(f"[gene_desc] GO term names loaded: {meta['go_name_terms']}")


if __name__ == "__main__":
    main()
