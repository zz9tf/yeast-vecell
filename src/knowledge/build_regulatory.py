#!/usr/bin/env python3
"""
build_regulatory.py — build tf_targets.json for yeast-vecell (Phase 2, PLAN.md).

Asset: the S. cerevisiae transcriptional regulatory network from YEASTRACT
(http://www.yeastract.com/), keyed by systematic ORF name, with the
activation/repression SIGN captured where YEASTRACT documents it. This
powers "DIR" (directional) reasoning in the DE/DIR prompting pipeline
(e.g. "repressing a documented activator -> Increase").

Schema written to --out:
    { "<TF_ORF>": {"activates": [...], "represses": [...], "targets": [...]}, ... }
`targets` = union of activates + represses + any additional documented
(binding-and/or-expression-evidence) target not otherwise signed.

--- Why script-driven live queries, not a single bulk file ------------------
YEASTRACT has NO bulk flat-file download of the full regulatory network
(download.php / "Retrieve flat files" literally just says "Contact Us"; the
nav entry is marked "Discontinued services" in the page source). The
Regulation Matrix tool (formregmatrix.php -> regmatrix.php) *can* answer
"all TFs in the DB" (POST field tfs=dbtfs) x "all genes" at once and emits
machine-readable RegulationMatrix*.csv / RegulationTwoColumnTable*.tsv
files — but "dbtfs" turned out to mean "test every gene in the genome as a
candidate regulator" (7135 candidate rows for a 5-gene test target list,
which took ~100s for just 300 target genes -> too slow to scale to the
full ~6600-gene genome: extrapolates to 1-2 hours PER sign-filtered query).

So instead this script uses the equivalent, but far cheaper, per-TF tool
"Search for Genes" (formfindregulated.php -> findregulated.php), submitting
our OWN curated TF candidate list (see below) as the `tfs` field (many TFs
per POST, newline-separated) and reads the `formtgs` hidden-field target
list embedded per TF in the result HTML. This is ~20 TFs / 4-6s per request
regardless of which TFs (fixed cost is per-target-gene-with-actual-data,
not per genome-wide candidate row), so the whole network completes in
~2-3 minutes across ~30 requests.

--- TF candidate list --------------------------------------------------------
YEASTRACT itself does not expose a plain TF list either (the "TF-Consensus
List" page only lists the ~128 TFs with a distilled DNA motif -- a subset).
We derive our candidate TF universe locally + reproducibly from S. cerevisiae
GO Cellular Component/Function annotations (already mirrored locally):
    /home/zhengz2/yeast-rank-cross-lab/data/external/sgd_go_annotations.gaf.gz
using GO terms for classical sequence-specific DNA-binding TF activity:
    GO:0003700  DNA-binding transcription factor activity
    GO:0000981  DNA-binding TF activity, RNA polymerase II-specific
    GO:0001228  DNA-binding transcription ACTIVATOR activity, RNAP II-specific
    GO:0001227  DNA-binding transcription REPRESSOR activity, RNAP II-specific
(197 gene symbols) plus a small manual addendum (10 genes) for well-known
regulators the GO slim misses for annotation-completeness reasons: 7 TFs
present on YEASTRACT's own consensus-motif list but not GO-tagged with the
above terms (DAL82, GCR2, HAP4, IME1, IXR1, MOT2, MSS11), and 3 classic
general co-regulators that act through DNA-binding partners rather than
binding DNA themselves but are heavily documented in YEASTRACT with sign
(TUP1, CYC8/SSN6, GAL80). ORF resolution uses:
    /home/zhengz2/yeast-rank-cross-lab/data/SGD_features.tab
Entries that are protein-COMPLEX GO annotations (identifiers like "CPX-684",
10 of them) are dropped (not single genes). Entries that resolve to no ORF
in SGD_features.tab (3 of them: MAL23/MAL43/MAL63, redundant MAL-locus
activators on subtelomeric repeats absent from the S288C reference genome)
are dropped too. Net candidate TF count: see stderr log / --stats.

Usage:
    python build_regulatory.py [--batch-size 20] [--sleep 1.0] \
        [--out /home/zhengz2/yeast-vecell/data/knowledge/tf_targets.json] \
        [--cache-dir /tmp/.../yeastract_cache]   # raw HTML cached so re-runs are cheap/idempotent

Idempotent: re-running with an intact --cache-dir re-parses cached HTML
instead of re-querying the live site; deleting the cache forces a fresh
(deterministic, modulo YEASTRACT's own data updates) re-download.
"""
import argparse
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests

GAF_PATH = "/home/zhengz2/yeast-rank-cross-lab/data/external/sgd_go_annotations.gaf.gz"
SGD_FEATURES_PATH = "/home/zhengz2/yeast-rank-cross-lab/data/SGD_features.tab"
DEFAULT_OUT = "/home/zhengz2/yeast-vecell/data/knowledge/tf_targets.json"
DEFAULT_CACHE = "/home/zhengz2/yeast-vecell/data/knowledge/.yeastract_cache"

YEASTRACT_URL = "https://www.yeastract.com/findregulated.php"

TF_GO_TERMS = {"GO:0003700", "GO:0000981", "GO:0001228", "GO:0001227"}
MANUAL_TF_ADDENDUM = ["DAL82", "GCR2", "HAP4", "IME1", "IXR1", "MOT2", "MSS11",
                       "TUP1", "CYC8", "GAL80"]

ORF_RE = re.compile(r"^(Y[A-Z]{2}\d{3}[WC](-[A-Z])?|Q\d{4})$")

FORM_PAIR_RE = re.compile(
    r'name="formtfs"\s+value="([^"]+)"\s*/>\s*<input[^>]*id="formtgs"[^>]*\s+value="([^"]*)"',
    re.S)


def load_sgd_features(path: str):
    sym2orf = {}
    orfs = set()
    with open(path, encoding="latin-1") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > 4 and parts[3]:
                orfs.add(parts[3])
                if parts[4]:
                    sym2orf[parts[4].upper()] = parts[3]
    return sym2orf, orfs


def build_tf_candidates(sym2orf: dict, all_orfs: set):
    """Return dict: query_name (as sent to YEASTRACT) -> orf."""
    go_symbols = set()
    with gzip.open(GAF_PATH, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 11:
                continue
            go_id = parts[4]
            if go_id in TF_GO_TERMS:
                go_symbols.add(parts[2].upper())

    candidates = sorted(go_symbols | {s.upper() for s in MANUAL_TF_ADDENDUM})

    tf_query2orf = {}
    dropped = []
    for sym in candidates:
        if sym.startswith("CPX-"):
            dropped.append((sym, "protein-complex GO id, not a gene"))
            continue
        if ORF_RE.match(sym):
            if sym in all_orfs:
                tf_query2orf[sym] = sym
            else:
                dropped.append((sym, "looks like ORF but not in SGD_features"))
            continue
        orf = sym2orf.get(sym)
        if orf:
            # use Title-case query form (matches YEASTRACT's own sample usage;
            # its gene-name resolver is case-insensitive but this keeps request
            # bodies readable / matches documented examples)
            query_name = sym[0] + sym[1:].lower()
            tf_query2orf[query_name] = orf
        else:
            dropped.append((sym, "no ORF mapping in SGD_features.tab"))

    print(f"[tf-candidates] {len(candidates)} GO+manual symbols -> "
          f"{len(tf_query2orf)} resolved TFs, {len(dropped)} dropped:",
          file=sys.stderr)
    for sym, reason in dropped:
        print(f"    dropped {sym}: {reason}", file=sys.stderr)
    return tf_query2orf


def resolve_target(name: str, sym2orf: dict, all_orfs: set):
    name = name.strip()
    if not name:
        return None
    if name in all_orfs or ORF_RE.match(name.upper()):
        # normalize case for systematic names (site sometimes lowercases e.g. "YAL066w")
        upper = name.upper()
        return upper if upper in all_orfs else name
    orf = sym2orf.get(name.upper())
    return orf  # may be None -> caller drops / counts as unmapped


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def query_yeastract(tf_names, evidence, t_pos, t_neg, use_na, cache_dir: Path, sleep_s: float):
    data = {
        "tfs": "\n".join(tf_names),
        "type": "doc",
        "evidence": evidence,
        "t_pos": "true" if t_pos else "false",
        "t_neg": "true" if t_neg else "false",
        "use_na": "true" if use_na else "false",
        "biggroup": "0",
        "subgroup": "0",
        "species": "0",
        "submit": "Search",
    }
    key = hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = cache_dir / f"findregulated_{key}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace")

    t0 = time.time()
    r = requests.post(YEASTRACT_URL, data=data, timeout=180,
                       headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    dt = time.time() - t0
    print(f"  [http] evidence={evidence} t_pos={t_pos} t_neg={t_neg} "
          f"n_tfs={len(tf_names)} -> {len(r.content)} bytes in {dt:.1f}s",
          file=sys.stderr)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(r.text, encoding="utf-8")
    if sleep_s > 0:
        time.sleep(sleep_s)
    return r.text


def parse_response(html: str, query_names_this_batch, sym2orf, all_orfs):
    """Return dict: matched_query_name (case/format-normalized) -> [target names]."""
    out = {}
    norm_lookup = {re.sub(r"[^a-z0-9]", "", q.lower()): q for q in query_names_this_batch}
    for anchor_val, targets_val in FORM_PAIR_RE.findall(html):
        anchor = anchor_val.strip()
        norm = re.sub(r"[^a-z0-9]", "", anchor.lower())
        if norm.endswith("p"):
            norm = norm[:-1]
        q = norm_lookup.get(norm)
        if q is None:
            continue
        targets = [t.strip() for t in targets_val.split("\n") if t.strip()]
        out[q] = targets
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE)
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    cache_dir = Path(args.cache_dir)
    sym2orf, all_orfs = load_sgd_features(SGD_FEATURES_PATH)
    tf_query2orf = build_tf_candidates(sym2orf, all_orfs)
    query_names = sorted(tf_query2orf.keys())

    network = {orf: {"activates": set(), "represses": set(), "targets": set()}
               for orf in tf_query2orf.values()}

    query_specs = [
        ("targets", dict(evidence="plus", t_pos=True, t_neg=True, use_na=True)),
        ("activates", dict(evidence="indir", t_pos=True, t_neg=False, use_na=False)),
        ("represses", dict(evidence="indir", t_pos=False, t_neg=True, use_na=False)),
    ]

    n_unmapped_targets = 0
    unmapped_examples = []

    for batch in chunked(query_names, args.batch_size):
        print(f"[batch] {batch[0]}..{batch[-1]} ({len(batch)} TFs)", file=sys.stderr)
        for bucket, spec in query_specs:
            html = query_yeastract(batch, cache_dir=cache_dir, sleep_s=args.sleep, **spec)
            parsed = parse_response(html, batch, sym2orf, all_orfs)
            for q, target_names in parsed.items():
                tf_orf = tf_query2orf[q]
                for tname in target_names:
                    torf = resolve_target(tname, sym2orf, all_orfs)
                    if torf is None:
                        n_unmapped_targets += 1
                        if len(unmapped_examples) < 20:
                            unmapped_examples.append(tname)
                        continue
                    network[tf_orf][bucket].add(torf)
                    if bucket in ("activates", "represses"):
                        network[tf_orf]["targets"].add(torf)
                    else:
                        network[tf_orf]["targets"].add(torf)

    # finalize: sort lists deterministically
    result = {}
    for tf_orf, buckets in network.items():
        result[tf_orf] = {
            "activates": sorted(buckets["activates"]),
            "represses": sorted(buckets["represses"]),
            "targets": sorted(buckets["targets"]),
        }

    n_tfs_with_targets = sum(1 for v in result.values() if v["targets"])
    n_signed_edges = sum(len(v["activates"]) + len(v["represses"]) for v in result.values())
    n_target_edges = sum(len(v["targets"]) for v in result.values())
    print(f"[summary] TFs total: {len(result)} | TFs with >=1 target: {n_tfs_with_targets} | "
          f"total target edges: {n_target_edges} | total signed (activates+represses) edges: "
          f"{n_signed_edges} | unmapped target-name occurrences dropped: {n_unmapped_targets}",
          file=sys.stderr)
    if unmapped_examples:
        print(f"[summary] example unmapped target names: {unmapped_examples}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(f"[write] {out_path} ({len(result)} TFs)", file=sys.stderr)


if __name__ == "__main__":
    main()
