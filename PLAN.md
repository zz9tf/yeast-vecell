# Yeast-VCWorld — Plan

A white-box "virtual cell" simulator for **Saccharomyces cerevisiae**, adapting the VCWorld
(ICLR 2026, arXiv:2512.00306) recipe: structured biological knowledge + LLM causal reasoning
to predict transcriptomic responses to perturbations, in a data-efficient and interpretable way.

Upstream reference implementation cloned at `../VCWorld`.

---

## Part A — What VCWorld actually does (pipeline dissection)

VCWorld is **not** a trained neural net. It is a **retrieval-augmented, prompt-engineered LLM**
that answers two per-triplet questions:

- **DE** (Differential Expression): does perturbing drug `P` change expression of gene `G`
  in cell line `C`?  → `Yes / No`
- **DIR** (Directional change): among DE hits, does `G` go `Increase / Decrease`?

The unit of prediction is a **(perturbation, gene, context) triplet**. Everything else is
machinery to give the LLM the right evidence and force stepwise mechanistic reasoning.

### The 3 conceptual blocks (from the paper figure)
1. **Sorted Retrieval** — perturbation pathway, cellular process, similar samples.
2. **LLM Augmentation** — descriptions, biological context, few-shot examples.
3. **Rule-based Generation** — fixed role ("molecular biologist"), fixed 5-step reasoning
   scaffold ("how & why"), single deterministic final answer.

### The 5 CLI stages (concrete I/O)

| Stage | Code | Input | Processing | Output |
|-------|------|-------|-----------|--------|
| **1. prepare** | `stages/prepare.py` | `.h5ad` scRNA-seq (Tahoe-100M, one cell line; `obs['drug']`, control `DMSO_TF`) | `normalize_total(1e4)`+`log1p` → `sc.tl.rank_genes_groups` (Wilcoxon, each drug vs DMSO, BH-FDR). DE label=1 if `padj<0.05 & |logFC|>0.25`; label=0 sampled (200/drug) from `pval>0.1`. DIR label=1 if `logFC>0` among DE hits. Perturbations split train/test 30/70. | `{cell}_DE.csv`, `{cell}_DIR.csv` → cols `pert, gene, label, split` |
| **2. retrieve** | `stages/retrieve.py` | DE/DIR CSV + **drug-sim JSON** + **gene-sim JSON** (KG neighbors) | Build `seen` maps (drug→genes, gene→drugs) from **train** split. For each test case, take top-k similar drugs & similar genes, then pull analogous **(drug,gene)** pairs observed in train (shared-drug / shared-gene / both). Budget-capped. | `retrieval.json`: list of `{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]...]}` |
| **3. prompt** | `stages/prompt.py` + `support/*_template.py` | retrieval.json + **drug-desc JSON** + **gene-desc JSON** + template (prompt scaffold + hand-written `cell_lines` descriptions) | Pick a cell-line context; format retrieved pairs into "Examples" (desc + a Result label); fill the 5-step DE/DIR template. | `prompts.txt` (blocks split by `====`) |
| **4a. infer** | `stages/infer.py` | prompts.txt + local HF model (e.g. Llama-3.1-8B) | Parse `[Start of Prompt]…`/`[Start of Input]…` into system+user msgs → chat template → `model.generate`. | `predictions.txt` (reasoning + final `Yes/No` or `Increase/Decrease`) |
| **4b. infer-api** | `stages/infer_api.py` | prompts.txt + OpenAI-compatible endpoint | Same, over HTTP `/chat/completions`. | `predictions.txt` |
| **(aux) single** | `stages/single_case/prompt.py` | one out-of-dataset `(pert,gene,cell)` | Resolve similar drugs/genes (case-insensitive / normalized / alias / **LLM-ranked fallback** if missing from JSON), gather evidence pairs from CSV, emit one prompt. | one-case `prompt.txt` |

### The knowledge assets (gitignored; from Google Drive + Zenodo)
- `combined_similarity_sorted.json` — **drug similarity** (chemical / MoA neighbors).
- `results_close_gene.json` — **gene similarity** = neighbors from an *open-world knowledge graph*
  (`direct_neighbors`, `two_hop_neighbors`, …); built from Reactome/UniProt/STRING per the figure.
- `drug_simp.json` — drug text descriptions (PubChem/DrugBank).
- `gene_output.json` — gene text descriptions.
- Cell-line descriptions are **hard-coded in the template** (tissue, hallmark mutations e.g. KRAS/TP53).

### Benchmark
**GeneTAK**, derived from the Tahoe-100M atlas: 5 cell lines, 348 drug compounds, DE + DIR tasks,
30/70 train/test-by-perturbation split to force few-shot behavior.

### Two things worth flagging before porting
1. **Bulk `prompt` stage assigns few-shot example labels with `random.choice(choices)`** — the
   retrieved pairs carry no label, so the "Result:" line in each example is *random*. Only the
   `single_case` path uses the true label. For yeast we should **carry real labels through retrieval**
   so the in-context examples are actually informative (or deliberately keep a "label-free analogue"
   ablation).
2. **The retrieval heuristic is ad-hoc** (`get_drug_gene_pairs`). It's a good baseline but yeast's
   far richer, higher-confidence networks let us do genuine graph-aware retrieval.

---

## Part B — Mapping VCWorld → Yeast

The key reframing: yeast is unicellular, so there is **no "cell line" axis and (usually) no drug**.
The natural, data-rich analog is **genetic perturbation → transcriptome**.

| VCWorld (human) | Yeast-VCWorld | Notes |
|---|---|---|
| Perturbation = **drug compound** | Perturbation = **single-gene deletion / TF induction / overexpression** (chemical optional) | Genetic perturbation is the gold-standard, best-covered yeast data |
| Read-out = human gene | Read-out = yeast ORF (~6000) | systematic name `YFL039C` + standard name `ACT1` |
| Context = **cancer cell line** (5) + hallmark mutations | Context = **strain background + growth condition/medium/stress** (e.g. BY4741 in YPD; +/- stress) | Replaces "cell_lines" list in template |
| DEG label vs DMSO control | DEG label vs **WT / mock** | same Wilcoxon/limma logic |
| Drug-sim (chemical/MoA) | **Perturbagen-sim** = genetic-interaction (SGA) profile correlation and/or GO/functional similarity between deleted genes | Boone/Costanzo SGA is a huge asset |
| Gene-sim KG (Reactome/STRING) | **Yeast co-functional KG**: STRING, BioGRID, YeastNet, KEGG, GO | denser & higher quality than human |
| Drug descriptions (PubChem) | **Gene descriptions** = SGD description + GO terms (perturbagen == deleted gene) | one description source serves both roles |
| Gene descriptions (UniProt) | SGD/UniProt-yeast gene descriptions | |
| — (implicit regulation) | **YEASTRACT TF→target regulatory network** | *the* asset for DIR (direction) reasoning; near-complete for yeast |

### Recommended perturbation dataset (the "Tahoe analog")
- **Primary: Deleteome** (Kemmeren et al., Cell 2014) — ~1484 single-gene-deletion strains ×
  ~6000 genes, expression vs WT, with published logFC + p-values. This is a near drop-in for
  GeneTAK: it already yields `(deleted_gene, measured_gene, logFC, pval)` triplets → DE/DIR labels.
- **Alternatives / extensions**:
  - **IDEA** (Hackett et al. 2020) — 200+ TF induction time courses (great for DIR/dynamics).
  - **Hughes compendium** (2000) — 300 deletions/treatments (older, cross-validation).
  - **Chemical**: if a drug axis is wanted, add a compound-perturbation set + PubChem descriptions
    to keep the exact VCWorld framing (then perturbagen-sim = chemical similarity again).
  - **User's existing yeast assets** (growth / het / expression matrices in `yeast-rank-cross-lab`)
    can seed additional context axes or an evaluation set — confirm scope before wiring in.

### Task definition on yeast
- **DE**: does deleting/inducing `P` differentially express ORF `G` (in condition `C`)? `Yes/No`
- **DIR**: `Increase/Decrease` among DE hits.
- Same 30/70 train/test **split by perturbagen** to preserve the few-shot, data-efficient premise.

---

## Part C — Implementation phases

Mirror VCWorld's stage layout (`src/cli_pipeline/stages/`) so the CLI stays familiar; swap the
data/knowledge backends underneath.

**Phase 0 — Scaffold & data acquisition**
- Clone VCWorld CLI structure; keep `cli.py` subcommands (`prepare/retrieve/prompt/infer`).
- Download Deleteome matrices + p-values → `data/perturbation/`.
- Pull knowledge: SGD gene descriptions + GO, STRING/BioGRID/YeastNet edges, YEASTRACT TF→target,
  Costanzo SGA profiles → `data/knowledge/`.

**Phase 1 — `prepare` (labels)**
- If starting from Deleteome's precomputed logFC/p-values: skip `rank_genes_groups`, apply the same
  thresholds directly (`padj<0.05 & |logFC|>thr` → DE=1; sample non-DE negatives per perturbagen).
- If starting from raw counts: keep the scanpy path (normalize→log1p→Wilcoxon vs WT).
- Emit `{condition}_DE.csv`, `{condition}_DIR.csv` with `pert, gene, label, split`.

**Phase 2 — Knowledge builders (the real work)**
- `build_gene_sim.py` → `results_close_gene.json`: for each ORF, ranked co-functional neighbors
  from STRING/BioGRID/YeastNet (+ GO semantic similarity), with `direct_neighbors` / `two_hop`.
- `build_pert_sim.py` → `perturbagen_similarity.json`: for each deleted gene, similar perturbagens
  by SGA genetic-interaction-profile correlation and/or GO/functional similarity.
- `build_descriptions.py` → `gene_desc.json` (SGD "Description" + GO BP/MF/CC + aliases), reused as
  perturbagen descriptions.
- `build_regulatory.py` → `tf_targets.json` from YEASTRACT (used to make DIR reasoning mechanistic).
- Author `support/DE_template.py` / `DIR_template.py`: replace `cell_lines` with a **conditions**
  list (strain + medium + active-pathway notes); rewrite the 5-step scaffold in yeast terms
  (deletion → epistasis/pathway → TF (YEASTRACT) → target ORF → direction).

**Phase 3 — `retrieve` (improve over the baseline heuristic)**
- Keep VCWorld's `seen`/budget logic as a baseline.
- Add graph-aware retrieval: prefer analogue pairs where perturbagen is an SGA/pathway neighbor
  **and** the read-out gene is a network neighbor; rank by combined edge confidence.
- **Fix the random-label issue**: carry the true train label into `retrieved_pairs` so few-shot
  "Result:" lines are real evidence. Keep a `--shuffle-labels` flag for the ablation.

**Phase 4 — `prompt` + `infer`**
- Reuse `prompt.py`/`infer.py`/`infer_api.py` nearly verbatim (they're data-agnostic once the
  template + JSONs are yeast).
- Inference: start with an API model for iteration; local HF (Llama-3.1-8B / Qwen) for cost/repro.

**Phase 5 — Evaluation & baselines**
- Parser: map final line → label; compute Accuracy / F1 / AUROC (DE), directional accuracy (DIR),
  per-perturbagen and per-condition breakdowns.
- Baselines to beat: (a) majority class, (b) "network-neighbor → DE" heuristic, (c) LLM **without**
  retrieval (ablate evidence), (d) a simple supervised model (logistic reg on network features).
- Interpretability check (VCWorld's headline claim): do the LLM's cited TF→target bridges match
  YEASTRACT ground truth? Report mechanistic-consistency rate.

**Phase 6 — Extensions (optional)**
- Add condition/stress as a real second axis (environmental gene-expression compendium).
- Move from binary DE to magnitude/regression; from static to time-course (IDEA).

---

## Part D — Key design decisions & pitfalls

- **Why yeast is a good fit**: model organism → LLMs already carry strong priors; networks
  (YEASTRACT, SGA, STRING) are dense and high-confidence → white-box reasoning is more grounded than
  in human. Deleteome gives thousands of clean perturbation→transcriptome triplets for cheap.
- **Identifier hygiene**: unify on systematic ORF names; keep an alias map (standard name ↔
  systematic ↔ SGD ID). VCWorld already needs a gene-alias table — yeast needs a bigger one.
- **Direction (DIR) is where knowledge pays off**: encode YEASTRACT activator/repressor signs so the
  template's "suppress an activator → Decrease" logic is checkable, not hand-wavy.
- **Carry real labels in retrieval** (see Part A note 1) — likely the single biggest quality lever.
- **Leakage**: split by perturbagen (not by pair); ensure retrieval only reads the **train** split.
- **Evaluation honesty**: always report the no-retrieval and majority-class baselines alongside.

---

## Open questions (need user input)

1. **Perturbation type**: genetic-only (Deleteome, recommended) or also keep a chemical/drug axis to
   stay maximally faithful to VCWorld?
2. **Context axis**: single reference condition (BY4741/YPD) to start, or multi-condition/stress from
   day one?
3. **Data source**: use Deleteome as-is, or wire in the existing yeast matrices from
   `yeast-rank-cross-lab`? (What do those matrices contain — perturbation-response or phenotype?)
4. **Inference budget**: API model (fast iteration) vs local HF (repro/cost) for the first runs?

---

## Repo layout (this project)
```
yeast-vecell/
├── PLAN.md                     # this file
├── README.md
├── src/cli_pipeline/
│   ├── cli.py                  # de/dir prepare|retrieve|prompt|infer  (ported)
│   └── stages/                 # prepare, retrieve, prompt, infer, infer_api, single_case
├── support/                    # DE_template.py, DIR_template.py (yeast conditions + 5-step scaffold)
├── data/
│   ├── perturbation/           # Deleteome / IDEA matrices → DE/DIR CSVs
│   └── knowledge/              # gene_desc, gene_sim (STRING/BioGRID), pert_sim (SGA), tf_targets (YEASTRACT)
└── docs/                       # dataset notes, KG build notes, eval reports
```
