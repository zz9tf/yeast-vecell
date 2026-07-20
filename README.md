# yeast-vecell

A white-box **virtual cell for *Saccharomyces cerevisiae***, adapting **VCWorld**
(ICLR 2026, arXiv:2512.00306) — structured biological knowledge + LLM causal reasoning to
predict transcriptomic responses to perturbations in a data-efficient, interpretable way.

- **Reference implementation** analyzed & cloned at `../VCWorld`.
- **VCWorld pipeline dissection:** [`docs/vcworld_pipeline.md`](docs/vcworld_pipeline.md) — exact
  inputs → processing → outputs for all 5 CLI stages, knowledge assets, and observations.
- **Design / roadmap:** [`PLAN.md`](PLAN.md) — the yeast adaptation plan (human→yeast mapping, data
  sources, phased implementation, open questions).

## Status
Planning stage. Next actions and open questions are at the bottom of `PLAN.md`.

## Repo layout
```
src/cli_pipeline/   # ported CLI: de/dir  prepare|retrieve|prompt|infer
support/            # DE/DIR prompt templates (yeast conditions + reasoning scaffold)
data/perturbation/  # Deleteome / IDEA → DE/DIR label CSVs
data/knowledge/     # gene descriptions, gene-sim (STRING/BioGRID), pert-sim (SGA), TF→target (YEASTRACT)
docs/               # dataset & knowledge-graph build notes, eval reports
```
