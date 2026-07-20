#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yeast gene-name alias resolution.

Resolves any gene name (standard "SLA1", lowercase deletion form "sla1",
systematic ORF "YBL007C", SGD id, or a registered alias) to the canonical
systematic ORF, using the ``gene_alias.json`` built by ``src/knowledge``.

This unifies the Deleteome perturbagen namespace (lowercase standard names, e.g.
"sla1") with the ORF-keyed knowledge assets (``perturbagen_similarity.json``,
``gene_desc.json``, ``results_close_gene.json``) so retrieval / description
lookups line up. ``to_systematic`` is idempotent on ORFs (YBL007C -> YBL007C).
"""

import json
from typing import Dict, Optional


def load_alias(path: Optional[str]) -> Dict:
    """Load gene_alias.json; a missing/unreadable file yields {} (graceful)."""
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[alias] WARNING: alias map unavailable ({path}): {exc}. "
              f"Names will be left un-normalized.")
        return {}


def to_systematic(name: str, alias: Dict) -> Optional[str]:
    """Any name -> systematic ORF, or None if unresolvable."""
    if not name:
        return None
    return alias.get("to_systematic", {}).get(str(name).strip().lower())


def to_standard(orf: str, alias: Dict) -> Optional[str]:
    """Systematic ORF -> standard/common name, or None."""
    if not orf:
        return None
    return alias.get("systematic_to_standard", {}).get(str(orf))


def display_name(name: str, alias: Dict) -> str:
    """Human-readable 'STANDARD (ORF)' when resolvable, else the input unchanged."""
    orf = to_systematic(name, alias)
    if not orf:
        return str(name)
    std = to_standard(orf, alias)
    return f"{std} ({orf})" if std and std != orf else orf
