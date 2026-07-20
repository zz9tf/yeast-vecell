# Prompt optimization — two A/B branches for the yeast DE/DIR tasks

Two drop-in prompt-template variant sets to be A/B benchmarked against the current
v1 baseline (`support/DE_template.py`, `support/DIR_template.py`). Each branch is a
full **DE + DIR** template set living under `support/variants/`, loaded via the
existing `prompt` stage with `--template`.

| Branch | Path | One-line idea |
|---|---|---|
| **v1 (baseline)** | `support/DE_template.py`, `support/DIR_template.py` | Current yeast port of VCWorld's 5-step scaffold. |
| **A — mechanism-structured** | `support/variants/A_mechanism/{DE,DIR}_template.py` | Make the causal chain explicit and *checkable*; force a YEASTRACT TF-sign step and mandatory analogue citation. |
| **B — calibration / few-shot-centric** | `support/variants/B_calibration/{DE,DIR}_template.py` | Treat "is it DE / which direction" as a *calibration* problem; anchor on the true-labelled same-context Examples; lean reasoning, tighter output, stated confidence. |

All three define the **same variable names** (`contexts`, `desc_pert`,
`desc_gene`, `desc_context`, `desc_obs`, `prompt_yeast_DE` / `prompt_yeast_DIR`,
`choices_de` / `choices_dir`) and the **same `.format()` fields**
(`pert, gene, pert_desc, gene_desc, context_short, context_desc, obs`), so any
variant is a drop-in for `prompt.py`. The `[Start of Prompt]…[End of Prompt]` /
`[Start of Input]…[End of Output]` markers are byte-for-byte preserved so
`infer.py`'s regexes parse each block. **The final closed-set answer sentences are
kept verbatim from v1** in both branches, so whatever answer-line parser is built
for v1 scoring works unchanged for A and B — the branches differ only in the
*reasoning scaffold* and the *output block*, never in the decision vocabulary.

---

## Branch A — mechanism-structured

**Hypothesis.** v1's 5-step scaffold is under-specified: it *mentions* pathways,
TFs and analogue cases but does not force the model to commit to them or to check
its own chain. Precision should rise if every claim is anchored to either a named
mechanism or a labelled analogue, rather than to name-similarity. Concretely A:

1. **Frames yeast biology explicitly** — a deletion is a *complete null* (100%
   loss of function, not a partial knock-down); the readout is a new *steady
   state* (so feedback / de-repression / compensation count); the *slow-growth /
   ESR confound* is called out as a real but non-specific cause of DE and kept
   separate from a gene-specific effect.
2. **Forces a YEASTRACT TF-sign step** — the model must name the TF(s) regulating
   the readout and fill in two signs explicitly: (Sign 1) activator vs repressor
   of the gene, and (Sign 2) does the deletion raise or lower that TF's activity.
3. **Makes the DIR logic crisp and checkable** — because a deletion is a *full
   loss of function* (not a drug agonist/antagonist), the YEASTRACT edge sign
   resolves the direction cleanly. DIR step 3 first checks the **direct edge**
   (is the deleted gene itself a TF regulating the readout? → delete an
   **activator** ⇒ **Decrease**, delete a **repressor** ⇒ **Increase**), then
   step 4 gives the full 4-row indirect truth table (lower an activator →
   Decrease; lower a repressor → Increase; raise an activator → Increase; raise a
   repressor → Decrease), followed by a mandatory cross-check against the true
   directions of same-pathway analogue Examples (same-pathway analogue wins on
   disagreement).
5. **Encodes the de-repression prior and reasons past it** — Deleteome DIR labels
   run ~**66% Increase / 34% Decrease** (deletions de-repress targets more often
   than they down-regulate), so a naive "always Increase" already scores 66% Acc.
   Branch A states this ~2:1 prior as a *weak* default for genuinely ambiguous
   cases only, and — because evaluation uses **macro-F1 / MCC**, not raw accuracy
   — explicitly instructs the model to **commit to Decrease** whenever the sign
   rule or the closest analogues warrant it, rather than retreating to the
   majority Increase. Catching the minority Decrease class is where macro-F1 / MCC
   are won.
4. **Mandates analogue citation** — the model must cite ≥1 Example *by number*,
   quote its true Result/direction, and state whether it supports or argues
   against the link. "No supporting Example + no regulatory link = weak evidence."

**Cost.** Longer prompt and longer expected completion (more tokens). Best paired
with a stronger backbone (Qwen2.5-14B) where the extra structure can be followed.

---

## Branch B — calibration / few-shot-centric

**Hypothesis.** The model never sees the raw effect size or the `|logFC|` / FDR
cutoff that *defines* a DE hit, so "is this differentially expressed?" is really
"does this clear **this dataset's** threshold?" — a calibration question, not a
pure mechanism question. The only in-context evidence of where that threshold
sits (and how permissive the dataset is) is the set of **true-labelled analogue
Examples from the same context**. So B makes the model *anchor on the Examples*
and use mechanism only as a light adjustment / tie-breaker. Concretely B:

1. **States the calibration framing up front** — "You cannot see effect sizes or
   the cutoff; the labelled same-context Examples are your calibration set;
   anchor on them."
2. **Leaner reasoning** — 3 short steps instead of 5:
   - **DE:** (1) tally Example base rate + closest-analogue vote → prior;
     (2) brief mechanistic adjustment up/down; (3) calibrated decision.
   - **DIR:** (1) direction vote among Examples (Increase vs Decrease) + closest
     analogues' modal direction; (2) activator/repressor sign rule as a *tie-
     breaker* only; (3) calibrated direction.
3. **Tighter, more parseable output** — the output block ends in explicit
   `Confidence:` (High/Medium/Low) and `Final:` lines, so a downstream parser can
   grab a confidence signal (useful later for Answered% / abstention / AUROC-style
   analysis) and the final closed-set sentence deterministically.
5. **DIR base-rate note without over-anchoring** — B's DIR key-fact block states
   the ~2:1 Increase:Decrease class prior, but frames it as a *weak tie-breaker*
   used only when the closest same-context analogues are split, and (since scoring
   is macro-F1 / MCC) tells the model to commit to Decrease when the sign rule
   points there rather than defaulting to the Increase majority.
4. **Conflict rule** — when the analogue vote and the mechanism disagree, trust
   the same-context Examples unless the mechanism/sign rule is decisive. This is
   the operational statement of "calibrate to the data you can see."

**Cost.** Cheaper (fewer tokens), and leans hardest on retrieval quality — it is
the natural partner to the "thread the *true* train label into `retrieved_pairs`"
fix (PLAN.md Part A.1 / Phase 3), since its whole premise is that the Example
labels are real, informative, and same-context.

---

## How A and B differ from v1 (summary)

| Axis | v1 | A (mechanism) | B (calibration) |
|---|---|---|---|
| Reasoning steps | 5 | 5, richer + checkable | 3 + Confidence/Final |
| Null framing | context prose only | explicit "complete null / steady state" assumptions block | one calibration-framing block |
| TF sign step | narrative ("YEASTRACT-style") | mandatory 2-sign fill-in per TF | tie-breaker only |
| DIR direction logic | 2 bullet rules | direct-edge rule + full 4-row truth table + cross-check + tie-break | vote-first, sign rule as tie-break |
| DIR class prior (~66% Inc) | not stated | stated as weak default; **commit to Decrease** on evidence (macro-F1/MCC) | stated as weak tie-breaker; commit to Decrease on sign rule |
| Use of Examples | cite (optional) | **cite ≥1 by number, state agreement** | **anchor / vote; Examples are the prior** |
| Output | numbered 1–5 | numbered 1–5 | 1–3 + `Confidence:` + `Final:` |
| Final answer sentences | closed set | **identical** | **identical** |
| Token cost | medium | higher | lower |

Everything else (context axis, description fields, evidence-block construction) is
identical, so any accuracy delta is attributable to the scaffold change alone.

---

## How to run each branch

The variants are drop-in for the existing `prompt` stage — only `--template`
changes. Run from `src/cli_pipeline`. Point `--retrieval` at a retrieval JSON from
the `retrieve` stage (or a hand-made one; see "Verification" below).

```bash
cd src/cli_pipeline

# ---- Branch A (mechanism-structured) ----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  \
  --template ../../support/variants/A_mechanism/DE_template.py   \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DE_prompts_A.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json \
  --template ../../support/variants/A_mechanism/DIR_template.py  \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DIR_prompts_A.txt

# ---- Branch B (calibration / few-shot-centric) ----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  \
  --template ../../support/variants/B_calibration/DE_template.py \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DE_prompts_B.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json \
  --template ../../support/variants/B_calibration/DIR_template.py \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DIR_prompts_B.txt

# ---- v1 baseline (default template; omit --template) ----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  --out out/cond_DE_prompts_v1.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json --out out/cond_DIR_prompts_v1.txt
```

Then feed each `*_prompts_*.txt` to `de|dir infer --model … --prompts … --out …`
(Qwen2.5-14B main; 7B/4B/Llama3.1-8B for the scale ablation), score the final
answer line, and record one row per (task, model, prompt_ver) in `RESULTS.md`
(config column already has a `prompt_ver` slot: `v1` / `A` / `B`).

---

## Verification (done, no LLM needed)

Rendered all six template sets (v1/A/B × DE/DIR) on a 2-case minimal retrieval
fixture (`test_case` = `YEL009C`(GCN4)→`YAL003W`(EFB1) and `YPL240C`(HSP82)→
`YFL039C`(ACT1), with true-labelled `retrieved_pairs`) through the real
`stages/prompt.py:generate_prompts` loader with `data/knowledge/gene_desc.json`.
For every rendered block: the `[Start of Prompt]/[End of Prompt]` and
`[Start of Input]/[End of Output]` markers are present exactly, `infer.py`'s two
extraction regexes match, real SGD descriptions and true-labelled Examples fill in,
and there are **zero** leftover `{…}` format placeholders (no NameError/KeyError
from the f-string). Both branches parse identically to v1.
```
render_v1_de/dir            blocks=2  markers OK  placeholders OK
render_A_mechanism_de/dir   blocks=2  markers OK  placeholders OK
render_B_calibration_de/dir blocks=2  markers OK  placeholders OK
```
