#!/usr/bin/env python3
"""Build data/knowledge/gene_alias.json from SGD_features.tab.

Canonical key everywhere in this project is the *systematic ORF name*
(e.g. YFL039C). This map lets code resolve ANY identifier -- systematic name,
standard/common name (ACT1) and its lowercase deletion-style form (act1),
SGD ID (S000...), or any registered alias -- back to the systematic name.

Output structure (gene_alias.json)
-----------------------------------
{
  "meta": {...},
  "systematic":            [ "YAL001C", ... ],              # all gene systematics
  "to_systematic":         { "<anything lowercased>": "YFL039C", ... },
  "systematic_to_standard":{ "YFL039C": "ACT1", ... },
  "systematic_to_sgdid":   { "YFL039C": "S000001855", ... },
  "systematic_to_aliases": { "YFL039C": ["ABY1","ACT1","END7", ...], ... }
}

`to_systematic` keys are lowercased. On collision, priority is
systematic-self > SGD-id > standard name > alias, so a real systematic name
always resolves to itself.
"""
import os
import json
import datetime

import sources


def build():
    feats = list(sources.iter_sgd_features())

    systematic = set()
    sys_to_std = {}
    sys_to_sgdid = {}
    sys_to_aliases = {}

    # Aggregate per systematic name over its (possibly several) feature rows.
    for f in feats:
        sysname = f["systematic"]
        if not sysname or not sources.is_gene_feature(f["feature_type"]):
            continue
        systematic.add(sysname)
        if f["standard"] and sysname not in sys_to_std:
            sys_to_std[sysname] = f["standard"]
        if f["sgdid"] and sysname not in sys_to_sgdid:
            sys_to_sgdid[sysname] = f["sgdid"]
        al = sys_to_aliases.setdefault(sysname, set())
        al.update(sources.split_aliases(f["aliases_raw"]))

    # Build lowercased resolver with priority ordering (later stages use
    # setdefault so earlier/stronger identifiers win on collision).
    to_systematic = {}

    def add(key, sysname):
        if key:
            to_systematic.setdefault(key.lower(), sysname)

    for s in sorted(systematic):                     # 1. systematic self-map
        add(s, s)
    for s, sgdid in sys_to_sgdid.items():            # 2. SGD id
        add(sgdid, s)
    for s, std in sys_to_std.items():                # 3. standard name (+ del-form)
        add(std, s)
    for s in sorted(sys_to_aliases):                 # 4. aliases
        for a in sorted(sys_to_aliases[s]):
            add(a, s)

    out = {
        "meta": {
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": os.path.basename(sources.resolve("sgd_features")),
            "source_path": sources.resolve("sgd_features"),
            "note": "keys of to_systematic are lowercased; resolve any id to "
                    "the systematic ORF name.",
            "n_systematic": len(systematic),
            "n_resolver_keys": len(to_systematic),
        },
        "systematic": sorted(systematic),
        "to_systematic": to_systematic,
        "systematic_to_standard": sys_to_std,
        "systematic_to_sgdid": sys_to_sgdid,
        "systematic_to_aliases": {k: sorted(v) for k, v in sys_to_aliases.items()},
    }
    return out


def main():
    out = build()
    os.makedirs(sources.KNOWLEDGE_DIR, exist_ok=True)
    dst = os.path.join(sources.KNOWLEDGE_DIR, "gene_alias.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=1)
    m = out["meta"]
    print(f"[gene_alias] wrote {dst}")
    print(f"[gene_alias] systematic genes : {m['n_systematic']}")
    print(f"[gene_alias] resolver keys    : {m['n_resolver_keys']}")
    print(f"[gene_alias] with std name     : {len(out['systematic_to_standard'])}")


if __name__ == "__main__":
    main()
