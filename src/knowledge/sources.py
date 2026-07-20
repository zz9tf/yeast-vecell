#!/usr/bin/env python3
"""Shared source-file resolution and parsers for the yeast knowledge builders.

All source data are read from *local* files (see docs/data_sources.md and the
Yeast DATA_MANIFEST). Every source has an ordered list of candidate paths; the
first readable one wins. Each can also be overridden with an environment
variable so the build stays reproducible on other machines.

Sources
-------
SGD_features.tab      alias map + one-line SGD descriptions   (col 3 systematic,
                      col 4 standard, col 5 aliases '|'-sep, col 15 description)
GAF (gene assoc.)     GO annotations for the description fallback
UniProt proteome tsv  GO-id -> GO-term-name dictionary (fallback term names)
gene_function_descriptions.csv   rich SGD-prose seed descriptions
Deleteome matrix      readout genes (col 2) + perturbagen header tokens
"""
import os
import re
import csv
import gzip
import io

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KNOWLEDGE_DIR = os.path.join(REPO, "data", "knowledge")
RAW_DIR = os.path.join(KNOWLEDGE_DIR, "raw")

_CANDIDATES = {
    "sgd_features": (
        "YEAST_SGD_FEATURES",
        [
            "/home/zhengz2/yeast-rank-cross-lab/data/SGD_features.tab",
            "/home/zhengz2/MiniShare/mini1/h100/public/Yeast/yeast_inputs/sgd/SGD_features.tab",
            os.path.join(RAW_DIR, "SGD_features.tab"),
        ],
    ),
    "gaf": (
        "YEAST_SGD_GAF",
        [
            "/home/zhengz2/yeast-rank-cross-lab/data/external/sgd_go_annotations.gaf.gz",
            "/home/zhengz2/MiniShare/mini1/h100/public/Yeast/yeast_inputs/sgd/gene_association.sgd",
            os.path.join(RAW_DIR, "sgd_go_annotations.gaf.gz"),
        ],
    ),
    "uniprot": (
        "YEAST_UNIPROT_TSV",
        [
            "/home/zhengz2/MiniShare/mini1/h100/public/Yeast/yeast_inputs/proteome/uniprot_UP000002311.tsv",
            os.path.join(RAW_DIR, "uniprot_UP000002311.tsv"),
        ],
    ),
    "seed_desc": (
        "YEAST_SEED_DESC",
        [
            "/home/zhengz2/yeast-rank-cross-lab/data/gene_function_descriptions.csv",
        ],
    ),
    "deleteome": (
        "YEAST_DELETEOME",
        [
            os.path.join(REPO, "data", "perturbation",
                         "deleteome_all_mutants_ex_wt_var_controls.txt"),
        ],
    ),
}


def _readable(path):
    try:
        with open(path, "rb") as fh:
            fh.read(1)
        return True
    except OSError:
        return False


def resolve(name, required=True):
    """Return the first readable candidate path for a logical source name."""
    env, cands = _CANDIDATES[name]
    ordered = []
    if os.environ.get(env):
        ordered.append(os.environ[env])
    ordered.extend(cands)
    for p in ordered:
        if p and os.path.exists(p) and _readable(p):
            return p
    if required:
        raise FileNotFoundError(
            f"No readable source for '{name}'. Tried: {ordered}. "
            f"Set ${env} to override."
        )
    return None


# ---------------------------------------------------------------------------
# SGD_features.tab
# ---------------------------------------------------------------------------
# 0 SGDID | 1 feature_type | 2 qualifier | 3 systematic | 4 standard |
# 5 alias('|') | 6 parent | 7 sec_SGDID | 8 chr | 9 start | 10 stop |
# 11 strand | 12 gen_pos | 13 coord_ver | 14 seq_ver | 15 description
GENE_FEATURE_TYPES = {
    "ORF", "pseudogene", "blocked reading frame", "transposable element gene",
}


def is_gene_feature(feature_type):
    """Gene-like features that legitimately carry a gene description."""
    return feature_type in GENE_FEATURE_TYPES or feature_type.endswith("gene")


def iter_sgd_features(path=None):
    """Yield dicts for every 16-column data row of SGD_features.tab."""
    path = path or resolve("sgd_features")
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) < 16:
                continue
            yield {
                "sgdid": c[0].strip(),
                "feature_type": c[1].strip(),
                "qualifier": c[2].strip(),
                "systematic": c[3].strip(),
                "standard": c[4].strip(),
                "aliases_raw": c[5].strip(),
                "description": c[15].strip(),
            }


def split_aliases(alias_field):
    """Split the SGD alias field, keeping only identifier-like tokens.

    The field mixes short aliases (FUN15, ARG5,6, MF(ALPHA)2) with a long
    descriptive protein name. Identifiers never contain whitespace, so that is
    a clean separator.
    """
    out = []
    for tok in alias_field.split("|"):
        tok = tok.strip()
        if tok and not re.search(r"\s", tok):
            out.append(tok)
    return out


# ---------------------------------------------------------------------------
# GAF -> per-identifier GO annotations grouped by aspect (P/F/C)
# ---------------------------------------------------------------------------
def _open_text(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8",
                                errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def load_gaf_index(path=None):
    """Return {lower_identifier: {'P':set,'F':set,'C':set}} of GO ids.

    Identifiers indexed per row: SGD ID (col2), symbol (col3) and every
    whitespace-free synonym token (col11, systematic name + aliases).
    """
    path = path or resolve("gaf")
    idx = {}

    def bucket(key):
        return idx.setdefault(key.lower(), {"P": set(), "F": set(), "C": set()})

    with _open_text(path) as fh:
        for line in fh:
            if not line or line[0] == "!":
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 15:
                continue
            sgdid, symbol, goid, aspect, syn = c[1], c[2], c[4], c[8], c[10]
            if aspect not in ("P", "F", "C"):
                continue
            keys = {sgdid, symbol}
            keys.update(t for t in syn.split("|") if t and not re.search(r"\s", t))
            for k in keys:
                if k:
                    bucket(k)[aspect].add(goid)
    return idx


# ---------------------------------------------------------------------------
# UniProt proteome tsv -> GO-id -> GO-term-name
# ---------------------------------------------------------------------------
_GO_TERM_RX = re.compile(r"([^;]+?)\s+\[(GO:\d{7})\]")

# Ontology root terms are never annotated to proteins in UniProt, so seed them
# so a gene annotated only to a root reads as "biological_process", etc.
_GO_ROOTS = {
    "GO:0008150": "biological_process",
    "GO:0003674": "molecular_function",
    "GO:0005575": "cellular_component",
}


def load_go_name_map(path=None):
    """Return {GO:id -> term name} parsed from the UniProt GO columns.

    Returns the three ontology roots only (never {}) if the UniProt tsv cannot
    be read, so the fallback degrades to raw GO ids but roots still render.
    """
    names = dict(_GO_ROOTS)
    try:
        path = path or resolve("uniprot")
    except FileNotFoundError:
        return names
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            rdr = csv.DictReader(fh, delimiter="\t")
            go_cols = [c for c in (rdr.fieldnames or [])
                       if c.startswith("Gene Ontology")]
            for row in rdr:
                for col in go_cols:
                    for m in _GO_TERM_RX.finditer(row.get(col, "") or ""):
                        names[m.group(2)] = m.group(1).strip()
    except OSError:
        return names
    return names


# ---------------------------------------------------------------------------
# Seed descriptions
# ---------------------------------------------------------------------------
def load_seed_descriptions(path=None):
    """Return {systematic_ORF: description} from gene_function_descriptions.csv."""
    path = path or resolve("seed_desc")
    out = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            g = (row.get("gene") or "").strip()
            d = (row.get("desc") or "").strip()
            if g and d:
                out[g] = d
    return out


# ---------------------------------------------------------------------------
# Deleteome matrix
# ---------------------------------------------------------------------------
def deleteome_readout_genes(path=None):
    """Return the sorted set of readout systematic names (column 2, rows 3+)."""
    path = path or resolve("deleteome")
    genes = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i < 2:
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) > 1 and c[1].strip():
                genes.add(c[1].strip())
    return genes


_VS_RX = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)


def strip_perturbagen(token):
    """'swd1-del-matA vs. wt-matA' -> 'swd1'; 'yil014c-a-del vs. wt' -> 'yil014c-a'.

    Take the text before ' vs', then drop the '-del' marker and everything
    after it (strain '-matA', replicate '-1', ...). Names with a suffixed
    systematic letter ('-A'/'-B'), comma ('arg5,6') or parentheses
    ('mf(alpha)2') are preserved because the split is on the literal '-del'.
    """
    left = _VS_RX.split(token.strip(), maxsplit=1)[0].strip()
    return re.split(r"-del", left, maxsplit=1)[0].strip()


def deleteome_perturbagens(path=None):
    """Parse header row 1 into perturbation experiments.

    Returns a list of dicts: {'raw': header token, 'name': stripped name,
    'is_control': bool}. One entry per experiment (M/A/p triple collapsed).
    """
    path = path or resolve("deleteome")
    with open(path, encoding="utf-8", errors="replace") as fh:
        header = fh.readline().rstrip("\n").split("\t")
    tokens = header[3:]                      # drop reporterId/systematic/symbol
    exps = []
    for j in range(0, len(tokens), 3):       # one experiment per M/A/p triple
        raw = tokens[j].strip()
        name = strip_perturbagen(raw)
        nl = name.lower()
        # True WT-control columns are 'wt-matA', 'wt-by4743', 'wt-ypd' (form
        # 'wt' or 'wt-...'). Do NOT match real genes WTM1/WTM2 ('wtm1'/'wtm2').
        exps.append({
            "raw": raw,
            "name": name,
            "is_control": nl == "wt" or nl.startswith("wt-"),
        })
    return exps
