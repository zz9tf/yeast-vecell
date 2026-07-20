#!/usr/bin/env python3
"""
build_gene_sim.py — build the yeast co-functional gene-similarity network
("gene neighbors") used in retrieval.

Output: data/knowledge/results_close_gene.json
  { "<systematic_ORF>": { "direct_neighbors": [...], "two_hop_neighbors": [...] }, ... }

Species: Saccharomyces cerevisiae only. Keys are canonical systematic ORF names
(e.g. YFL039C), ranked most-similar first.

Primary source: STRING v12.0, S. cerevisiae (NCBI taxon 4932), protein links file
(protein1 protein2 combined_score). STRING already keys yeast proteins by systematic
ORF name (e.g. "4932.YFL039C"), so no symbol->ORF resolution is needed beyond
stripping the "4932." taxon prefix — confirmed empirically (every node id matches
/^[YQR]/, i.e. nuclear "Y..." / mitochondrial "Q..." / rDNA "R..." systematic names).

This project has a local, byte-identical copy of the STRING v12.0 yeast links file
(md5 0a477e579f8a3660a96094ab184d89d2) at:
    /home/zhengz2/yeast-rank-cross-lab/data/external/string_4932_links.txt.gz
The script reads that file in place by default. It only falls back to downloading
from stringdb-downloads.org if the local copy is missing or fails a gzip integrity
check (`gzip -t`).

SGD_features.tab (also read in place from yeast-rank-cross-lab) supplies the full
list of annotated S. cerevisiae ORFs (systematic name + standard name + aliases). It
is used only for (a) an optional defensive symbol->ORF resolver and (b) coverage
bookkeeping in the printed summary — the network's node set itself is driven by
whatever appears in the STRING links file.

Method
------
direct_neighbors(g):
    Neighbors of g in the STRING graph with combined_score >= 700 ("high
    confidence" per STRING's own convention), ranked by combined_score
    descending, capped at DIRECT_CAP (25).

two_hop_neighbors(g):
    Neighbors-of-direct-neighbors within the same >=700 graph, excluding g
    itself and anything already in direct_neighbors(g), deduplicated. Ranked
    by the best two-edge path confidence
        score(g, d) * score(d, t) / 1000
    maximized over all direct neighbors d that bridge to t (STRING scores are
    ~probabilities scaled to 0-999, so this product/1000 is a standard way to
    combine two independent-ish edge confidences into one path confidence).
    Capped at TWO_HOP_CAP (25).

Idempotency
-----------
Re-running with no arguments always reads the same input files and
deterministically rewrites results_close_gene.json (ties broken by ORF name),
so repeated runs produce byte-identical output. No network access happens
unless the local STRING copy is missing/corrupt.

Optional BioGRID enrichment (off by default)
---------------------------------------------
A local BioGRID file is available at:
    /home/zhengz2/MiniShare/mini1/h100/public/Yeast/yeast_inputs/interaction/
    BIOGRID-PROJECT-kinome_project_sc-INTERACTIONS-5.0.258.tab3.txt
but it is scoped to the BioGRID "kinome project" only (interactions involving
~260 kinase/related genes), not full-genome BioGRID. Unioning it in by default
would selectively enrich kinase-adjacent genes and bias the network's
node-degree distribution. Per the task spec ("optional ... not required if
STRING alone works"), it is left as an opt-in via --biogrid <path> and is NOT
applied in the default build. STRING alone gives >=1 high-confidence (>=700)
neighbor for the large majority of the ~6500 proteins in its yeast network.
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import urllib.request
from collections import defaultdict

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "knowledge", "results_close_gene.json")
FALLBACK_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "knowledge", "raw")

# Local canonical copy (byte-identical to the STRING download, md5 confirmed
# 2026-07: 0a477e579f8a3660a96094ab184d89d2).
LOCAL_STRING_LINKS = "/home/zhengz2/yeast-rank-cross-lab/data/external/string_4932_links.txt.gz"
LOCAL_SGD_FEATURES = "/home/zhengz2/yeast-rank-cross-lab/data/SGD_features.tab"

STRING_TAXON = "4932"
STRING_VERSION = "v12.0"
FALLBACK_LINKS_URL = (
    f"https://stringdb-downloads.org/download/protein.links.{STRING_VERSION}/"
    f"{STRING_TAXON}.protein.links.{STRING_VERSION}.txt.gz"
)

DIRECT_SCORE_THRESHOLD = 700
DIRECT_CAP = 25
TWO_HOP_CAP = 25


# ---------------------------------------------------------------------------
# Input resolution (local-first, download fallback only if corrupt/missing)
# ---------------------------------------------------------------------------

def _gzip_ok(path: str) -> bool:
    """Cheap integrity check: `gzip -t` the whole stream."""
    try:
        result = subprocess.run(["gzip", "-t", path], capture_output=True, timeout=120)
        return result.returncode == 0
    except Exception:
        return False


def resolve_links_path(explicit_path: str, force_download: bool) -> str:
    """Return a path to a valid STRING links .gz file, preferring the local copy."""
    if explicit_path:
        if not _gzip_ok(explicit_path):
            raise RuntimeError(f"--links-path {explicit_path} failed gzip integrity check")
        return explicit_path

    if not force_download and os.path.exists(LOCAL_STRING_LINKS):
        if _gzip_ok(LOCAL_STRING_LINKS):
            print(f"[input] using local STRING links file: {LOCAL_STRING_LINKS}")
            return LOCAL_STRING_LINKS
        print(f"[warn] local STRING file at {LOCAL_STRING_LINKS} failed gzip -t; "
              f"falling back to downloading from STRING.")

    os.makedirs(FALLBACK_RAW_DIR, exist_ok=True)
    dest = os.path.join(FALLBACK_RAW_DIR, f"{STRING_TAXON}.protein.links.{STRING_VERSION}.txt.gz")
    if not force_download and os.path.exists(dest) and _gzip_ok(dest):
        print(f"[input] using previously-downloaded fallback copy: {dest}")
        return dest

    print(f"[download] local copy unavailable/corrupt; fetching {FALLBACK_LINKS_URL} -> {dest}")
    tmp = dest + ".part"
    req = urllib.request.Request(FALLBACK_LINKS_URL, headers={"User-Agent": "yeast-vecell/build_gene_sim.py"})
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    if not _gzip_ok(dest):
        raise RuntimeError(f"downloaded {FALLBACK_LINKS_URL} but it failed gzip -t")
    return dest


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def strip_taxon(protein_id: str) -> str:
    prefix = STRING_TAXON + "."
    return protein_id[len(prefix):] if protein_id.startswith(prefix) else protein_id


def load_edges(links_path: str):
    """Parse the STRING links file (space-delimited: protein1 protein2 combined_score).

    Returns dict[orf] -> list[(neighbor_orf, combined_score)] restricted to
    combined_score >= DIRECT_SCORE_THRESHOLD. STRING lists each undirected edge
    twice (A B score and B A score), so this dict is already symmetric.
    """
    adj = defaultdict(list)
    n_lines = 0
    n_kept = 0
    with gzip.open(links_path, "rt") as f:
        header = f.readline()  # "protein1 protein2 combined_score"
        for line in f:
            n_lines += 1
            parts = line.split()
            if len(parts) != 3:
                continue
            p1, p2, score_s = parts
            try:
                score = int(score_s)
            except ValueError:
                continue
            if score < DIRECT_SCORE_THRESHOLD:
                continue
            n_kept += 1
            adj[strip_taxon(p1)].append((strip_taxon(p2), score))
    return adj, n_lines, n_kept


def load_sgd_orf_universe(sgd_features_path: str):
    """Return (systematic_orfs:set, symbol_to_orf:dict) from SGD_features.tab.

    Column layout (tab-delimited, no header):
      0 SGDID, 1 feature type, 2 feature qualifier, 3 feature name (systematic
      ORF), 4 standard gene name, 5 aliases (pipe-separated), ...
    Used only for optional symbol->ORF resolution and coverage bookkeeping —
    not for the network's node set.
    """
    orfs = set()
    symbol_to_orf = {}
    if not sgd_features_path or not os.path.exists(sgd_features_path):
        return orfs, symbol_to_orf
    with open(sgd_features_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6 or parts[1] != "ORF":
                continue
            systematic = parts[3].strip()
            if not systematic:
                continue
            orfs.add(systematic)
            standard = parts[4].strip()
            if standard:
                symbol_to_orf[standard.upper()] = systematic
            for alias in parts[5].split("|"):
                alias = alias.strip()
                if alias:
                    symbol_to_orf.setdefault(alias.upper(), systematic)
    return orfs, symbol_to_orf


def resolve_to_orf(gene_id: str, known_orfs: set, symbol_to_orf: dict) -> str:
    """Best-effort resolution of a gene identifier to a systematic ORF name.

    STRING yeast IDs are already systematic ORF names, so in practice this is a
    no-op; kept as a defensive fallback for any caller that hands in a standard
    gene symbol instead (per task spec: "if a gene identifier is a standard
    name, resolve to systematic").
    """
    if gene_id in known_orfs:
        return gene_id
    return symbol_to_orf.get(gene_id.upper(), gene_id)


# ---------------------------------------------------------------------------
# Optional BioGRID enrichment (opt-in only, see module docstring)
# ---------------------------------------------------------------------------

def load_biogrid_edges(biogrid_path: str):
    """Parse a BioGRID *.tab3.txt file into dict[orf] -> set(neighbor_orf).

    Uses the 'Systematic Name Interactor A/B' columns directly (already
    systematic ORF names for yeast). No score column is populated in the
    kinome-project export (Score == '-'), so these edges are unscored.
    """
    adj = defaultdict(set)
    with open(biogrid_path, "r", encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n").split("\t")
        try:
            ia = header.index("Systematic Name Interactor A")
            ib = header.index("Systematic Name Interactor B")
        except ValueError:
            raise RuntimeError("BioGRID file missing expected 'Systematic Name Interactor A/B' columns")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= max(ia, ib):
                continue
            g1, g2 = parts[ia].strip(), parts[ib].strip()
            if not g1 or not g2 or g1 == g2:
                continue
            adj[g1].add(g2)
            adj[g2].add(g1)
    return adj


# ---------------------------------------------------------------------------
# Network build
# ---------------------------------------------------------------------------

def build(adj, biogrid_adj=None):
    result = {}
    all_genes = set(adj.keys())
    if biogrid_adj:
        all_genes |= set(biogrid_adj.keys())

    for g in sorted(all_genes):
        neighbors_sorted = sorted(adj.get(g, []), key=lambda x: (-x[1], x[0]))

        direct = []
        seen = set()
        for n, s in neighbors_sorted:
            if n == g or n in seen:
                continue
            seen.add(n)
            direct.append(n)
            if len(direct) >= DIRECT_CAP:
                break

        if biogrid_adj and len(direct) < DIRECT_CAP:
            # Unscored supplementary edges are appended only after all ranked
            # STRING (>=700) neighbors, and only to fill remaining cap slots —
            # they never outrank a scored STRING edge.
            for n in sorted(biogrid_adj.get(g, ())):
                if n == g or n in seen:
                    continue
                seen.add(n)
                direct.append(n)
                if len(direct) >= DIRECT_CAP:
                    break

        direct_set = set(direct)
        direct_score_map = {n: s for n, s in neighbors_sorted}

        two_hop_scores = {}
        for d in direct:
            score_gd = direct_score_map.get(d, DIRECT_SCORE_THRESHOLD)  # BioGRID-only edge: treat at threshold
            for t, score_dt in adj.get(d, []):
                if t == g or t in direct_set:
                    continue
                combined = (score_gd * score_dt) / 1000.0
                if t not in two_hop_scores or combined > two_hop_scores[t]:
                    two_hop_scores[t] = combined

        two_hop_sorted = sorted(two_hop_scores.items(), key=lambda x: (-x[1], x[0]))
        two_hop = [t for t, _ in two_hop_sorted[:TWO_HOP_CAP]]

        result[g] = {
            "direct_neighbors": direct,
            "two_hop_neighbors": two_hop,
        }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--links-path", default=None,
                        help="explicit path to a STRING protein.links .gz file "
                             "(default: local yeast-rank-cross-lab copy, else download)")
    parser.add_argument("--sgd-features", default=LOCAL_SGD_FEATURES,
                        help="path to SGD_features.tab, for coverage bookkeeping only")
    parser.add_argument("--force-download", action="store_true",
                        help="ignore the local STRING copy and (re-)download from stringdb-downloads.org")
    parser.add_argument("--biogrid", default=None,
                        help="optional path to a BioGRID *.tab3.txt file to union in as "
                             "supplementary (unscored) direct-neighbor edges; off by default")
    parser.add_argument("--out", default=OUT_PATH, help="output JSON path")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    links_path = resolve_links_path(args.links_path, args.force_download)

    print(f"[parse] loading STRING links, filtering combined_score >= {DIRECT_SCORE_THRESHOLD} ...")
    adj, n_lines, n_kept = load_edges(links_path)
    print(f"  {n_lines} raw edge rows (both directions); {n_kept} rows >= {DIRECT_SCORE_THRESHOLD}; "
          f"{len(adj)} genes have >=1 high-confidence neighbor")

    biogrid_adj = None
    if args.biogrid:
        print(f"[parse] loading optional BioGRID enrichment from {args.biogrid} ...")
        biogrid_adj = load_biogrid_edges(args.biogrid)
        print(f"  {len(biogrid_adj)} genes with >=1 BioGRID edge (kinome-project subset)")

    print("[build] ranking direct_neighbors / two_hop_neighbors ...")
    result = build(adj, biogrid_adj)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    # ---- summary ----
    n_genes = len(result)
    n_with_direct = sum(1 for v in result.values() if v["direct_neighbors"])
    n_with_two_hop = sum(1 for v in result.values() if v["two_hop_neighbors"])
    avg_direct = (sum(len(v["direct_neighbors"]) for v in result.values()) / n_genes) if n_genes else 0.0
    avg_two_hop = (sum(len(v["two_hop_neighbors"]) for v in result.values()) / n_genes) if n_genes else 0.0

    known_orfs, _ = load_sgd_orf_universe(args.sgd_features)
    covered_sgd_orfs = len(known_orfs & set(result.keys())) if known_orfs else None

    print(f"[done] wrote {args.out}")
    print(f"  genes (network nodes): {n_genes}")
    print(f"  genes with >=1 direct_neighbor: {n_with_direct}; with >=1 two_hop_neighbor: {n_with_two_hop}")
    print(f"  avg direct_neighbors: {avg_direct:.2f}; avg two_hop_neighbors: {avg_two_hop:.2f}")
    if covered_sgd_orfs is not None:
        print(f"  overlap with SGD_features.tab annotated ORFs ({len(known_orfs)} total): {covered_sgd_orfs}")


if __name__ == "__main__":
    main()
