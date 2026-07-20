# VCWorld pipeline — dissection

Reference: **VCWorld: A Biological World Model for Virtual Cell Simulation** (ICLR 2026,
arXiv:2512.00306). Code analyzed from the official repo cloned at `../VCWorld`.

This note records exactly what the upstream pipeline consumes, does, and produces, so the yeast
port (`../PLAN.md`) can swap backends without re-reading the source.

---

## 1. Core idea

VCWorld is **not a trained model**. It is a **retrieval-augmented, prompt-engineered LLM** that
answers, per **(perturbation, gene, context) triplet**, one of two questions:

- **DE** (Differential Expression): does perturbing drug `P` change expression of gene `G` in cell
  line `C`? → `Yes / No`
- **DIR** (Directional change): among DE hits, does `G` go `Increase / Decrease`?

Everything in the pipeline exists to (a) mine ground-truth labels from single-cell data, (b) retrieve
the most relevant analogue cases + biological descriptions as evidence, and (c) force the LLM through
a fixed mechanistic reasoning scaffold to a single deterministic answer.

The paper figure frames it as three blocks:
1. **Sorted Retrieval** — perturbation pathway, cellular process, similar samples.
2. **LLM Augmentation** — descriptions, biological context, few-shot examples.
3. **Rule-based Generation** — fixed role ("molecular biologist"), fixed 5-step "how & why" reasoning,
   one final answer.

---

## 2. Data flow

```
 .h5ad (Tahoe-100M, 1 cell line)
        │  prepare  (scanpy: normalize→log1p→rank_genes_groups vs DMSO)
        ▼
 {cell}_DE.csv / {cell}_DIR.csv        cols: pert, gene, label, split (train/test 30/70)
        │  retrieve  (+ drug-sim JSON, gene-sim KG JSON)
        ▼
 retrieval.json     [{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]...]}]
        │  prompt   (+ drug-desc JSON, gene-desc JSON, DE/DIR template w/ cell-line descriptions)
        ▼
 prompts.txt        (blocks separated by "====")
        │  infer  /  infer-api  (local HF model  OR  OpenAI-compatible endpoint)
        ▼
 predictions.txt    (5-step reasoning trace + final Yes/No or Increase/Decrease)
```

---

## 3. Stage-by-stage I/O

### Stage 1 — `prepare` (`src/cli_pipeline/stages/prepare.py`)
- **Input**: one `.h5ad` AnnData for a single cell line. `obs[perturbation_col]` (default `drug`)
  holds the perturbation; control group = `DMSO_TF`.
- **Processing**:
  1. `sc.pp.normalize_total(target_sum=1e4)` → `sc.pp.log1p`.
  2. `sc.tl.rank_genes_groups(groupby=drug, reference=DMSO_TF, method="wilcoxon",
     corr_method="benjamini-hochberg")` → per drug: `logfoldchanges, pvals, pvals_adj` per gene.
  3. **Split**: shuffle perturbations, first `train_fraction` (0.3) → train, rest → test.
  4. **DE labels**: `label=1` if `pvals_adj < fdr(0.05) & |logFC| > lfc(0.25)`;
     `label=0` sampled (`n_neg=200` / drug) from non-significant genes (`pvals > pval_neg(0.1)`).
  5. **DIR labels**: among the DE hits, `label=1` if `logFC>0` else `0`.
- **Output**: `{cell}_DE.csv`, `{cell}_DIR.csv`, columns `pert, gene, label, split`.

### Stage 2 — `retrieve` (`src/cli_pipeline/stages/retrieve.py`)
- **Input**: DE/DIR CSV + **drug-similarity JSON** + **gene-similarity JSON**.
  - `load_similarity_json` is tolerant: accepts `{key:[...]}`, `{key:[{"Drug":..}]}`, or KG dicts
    with `direct_neighbors / two_hop_neighbors / neighbors / …`.
- **Processing**:
  - `build_seen_structures(train)` → `seen: drug→[genes]`, `seen_gene: gene→[drugs]` (train only).
  - For each unique test `(drug,gene)`: `close_drugs`, `close_genes` = top-`budget` similar.
  - `get_drug_gene_pairs` assembles analogue evidence pairs from train, in priority tiers:
    shared-drug pairs, shared-gene pairs, "both-similar" pairs, then backfill — all budget-capped
    with a seeded RNG.
- **Output**: `retrieval.json` = list of `{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]…]}`.
- ⚠️ **Note**: `retrieved_pairs` carry **no label** — see §6.

### Stage 3 — `prompt` (`src/cli_pipeline/stages/prompt.py` + `support/{DE,DIR}_template.py`)
- **Input**: retrieval.json + **drug-desc JSON** + **gene-desc JSON** + template file.
  - Template is a Python file `exec`'d to pull `cell_lines` (list of `(short, description)`),
    `prompt_vcworld_DE/DIR` (the scaffold), `choices_de/dir`.
- **Processing**: per case, pick a cell-line context (random or `--cell-line-idx`); build the
  "Examples" block from retrieved pairs (drug/gene + descriptions + a `Result:` line); `.format(...)`
  the template with `pert, gene, pert_desc, gene_desc, cell_short, cell_desc, obs`.
- **Output**: `prompts.txt` — one block per case, split by an 80-`=` separator; each block has
  `[Start of Prompt]…[End of Prompt]` (system) and `[Start of Input]…[End of Output]` (user).

### Stage 4 — `infer` / `infer-api` (`stages/infer.py`, `stages/infer_api.py`)
- **Input**: prompts.txt + a local HF model path (`AutoModelForCausalLM`) **or** an
  OpenAI-compatible `/chat/completions` endpoint (`--api-url`, `--api-model`, key via flag/env).
- **Processing**: regex-parse each block into `system`+`user` messages → `apply_chat_template` →
  sample (`temperature=0.6, top_p=0.9`, default `max_new_tokens`). Local path batches; API path loops.
- **Output**: `predictions.txt` — per case, the model's 5-step reasoning + final deterministic line.

### Aux — `single` (`stages/single_case/prompt.py`)
For an out-of-dataset `(pert, gene, cell)`: resolve similar drugs/genes via the JSONs with
case-insensitive + alphanumeric-normalized matching, a hardcoded gene-alias map, and an **LLM-ranked
fallback** when the query is absent from the similarity JSON. Collects evidence pairs from the CSV and
emits a single prompt. Unlike bulk `prompt`, it uses the **true** train label in each example.

---

## 4. The reasoning scaffold (templates)

Both `DE_template.py` and `DIR_template.py` set:
- `cell_lines`: 5 hand-written descriptions (C32, PANC-1, HepG2/C3A, HOP62, Hs766T) with tissue of
  origin + hallmark mutations (KRAS, TP53, BRAF V600E, …). The prompt explicitly tells the LLM to
  *augment* this with its internal knowledge of the cell line.
- A fixed **5-step** analysis the model must fill:
  1. Mechanism & analogue identification (shared MoA / pathway nodes).
  2. Specificity & relevance (drug–gene–cell triad; is the target relevant given the mutations).
  3. Downstream signaling cascade simulation.
  4. Causal bridge & evidence synthesis (`Drug → Target → Pathway → TF → Gene`, cite analogue cases).
  5. Final deterministic prediction (one exact sentence from a closed set).
- DIR adds explicit **directional logic**: "suppress an *activator* → Decrease; suppress a
  *repressor* → Increase" (and vice versa).

---

## 5. Knowledge assets & benchmark

External files (gitignored upstream; from Google Drive + Zenodo):
- `combined_similarity_sorted.json` — **drug similarity** (chemical / MoA neighbors).
- `results_close_gene.json` — **gene similarity** = neighbors from an *open-world knowledge graph*
  (Reactome / UniProt / STRING per the figure), exposing `direct_neighbors`, `two_hop_neighbors`, …
- `drug_simp.json` — drug text descriptions (PubChem / DrugBank).
- `gene_output.json` — gene text descriptions.

**Benchmark — GeneTAK**: derived from the Tahoe-100M single-cell atlas. 5 cell lines, 348 drug
compounds, DE + DIR tasks, formatted as `(cell line, perturbation, gene)` triplets, split
train/test-by-perturbation **30/70** to simulate few-shot conditions.

**Requirements**: Python 3.10; `numpy, pandas, scanpy, anndata, scipy, scikit-learn, statsmodels`
(data pipeline) + `torch, transformers, accelerate` (local inference).

---

## 6. Observations to carry into the port

1. **Few-shot example labels in bulk `prompt` are random.** `retrieved_pairs` drop the label, so
   `format_observations` fills each `Result:` line with `random.choice(choices)`. Only `single_case`
   uses the true label. The yeast port should thread the real train label through retrieval (keep a
   `--shuffle-labels` flag for the ablation). Likely the single biggest quality lever.
2. **Retrieval is a hand-tuned heuristic** (`get_drug_gene_pairs`). Fine as a baseline; yeast's
   denser, higher-confidence networks (STRING/BioGRID/SGA/YEASTRACT) enable genuine graph-aware,
   confidence-ranked retrieval.
3. **Cell-line context is hardcoded prose**, not data. In yeast this becomes a
   strain/condition list — cheap to author, and the "hallmark mutation" hook maps onto strain
   background / active pathways.
4. **Templates are `exec`'d Python**, so they can embed logic, not just strings — handy for encoding
   YEASTRACT activator/repressor signs directly into the DIR scaffold.
5. No evaluation/metrics script ships in the CLI — scoring (answer-line → label → Acc/F1/AUROC) is
   left to the user and must be built for the port.
