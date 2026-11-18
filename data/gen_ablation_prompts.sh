#!/bin/bash
# Generates prompts for ablation C (w/o Biocontext) and D (w/o CoT), T1 (DE/DIR)
# + T2A (t2de/t2dir), 3 seeds each -- reuses the SAME retrieval jsons as the
# main matrix / A-B branches (retrieval itself is unchanged by these ablations,
# only the prompt template + description lookups differ).
set -e
cd /home/zhengz2/yeast-vecell/src/cli_pipeline
PY=/usr/bin/python3.12
R=../../data/runs; T=../../data/task2; K=../../data/knowledge; AB=../../data/ab
EMPTY=$AB/_empty_desc.json
SUP=../../support/variants

for s in 0 1 2; do
  echo "===== seed $s $(date +%H:%M:%S) ====="
  # ---- Ablation C: w/o Biocontext (blank descriptions via $EMPTY) ----
  $PY cli.py de  prompt --retrieval $R/DE_retr_full_s$s.json  --template $SUP/C_no_biocontext/DE_template.py  --gene-desc $EMPTY --pert-desc $EMPTY --out $AB/DE_prompts_C_s$s.txt  --context-idx 0
  $PY cli.py dir prompt --retrieval $R/DIR_retr_full_s$s.json --template $SUP/C_no_biocontext/DIR_template.py --gene-desc $EMPTY --pert-desc $EMPTY --out $AB/DIR_prompts_C_s$s.txt --context-idx 0
  $PY cli.py de  prompt --retrieval $T/t2de_retr_full_s$s.json  --template $SUP/C_no_biocontext/task2/DE_template.py  --gene-desc $EMPTY --pert-desc $EMPTY --out $AB/t2de_prompts_C_s$s.txt  --context-idx 0
  $PY cli.py dir prompt --retrieval $T/t2dir_retr_full_s$s.json --template $SUP/C_no_biocontext/task2/DIR_template.py --gene-desc $EMPTY --pert-desc $EMPTY --out $AB/t2dir_prompts_C_s$s.txt --context-idx 0

  # ---- Ablation D: w/o CoT (full biocontext, same JSONs as v1) ----
  $PY cli.py de  prompt --retrieval $R/DE_retr_full_s$s.json  --template $SUP/D_no_cot/DE_template.py  --out $AB/DE_prompts_D_s$s.txt
  $PY cli.py dir prompt --retrieval $R/DIR_retr_full_s$s.json --template $SUP/D_no_cot/DIR_template.py --out $AB/DIR_prompts_D_s$s.txt
  $PY cli.py de  prompt --retrieval $T/t2de_retr_full_s$s.json  --template $SUP/D_no_cot/task2/DE_template.py  --gene-desc $T/context_desc.json --pert-desc $K/gene_desc.json --out $AB/t2de_prompts_D_s$s.txt  --context-idx 0
  $PY cli.py dir prompt --retrieval $T/t2dir_retr_full_s$s.json --template $SUP/D_no_cot/task2/DIR_template.py --gene-desc $T/context_desc.json --pert-desc $K/gene_desc.json --out $AB/t2dir_prompts_D_s$s.txt --context-idx 0

  echo "seed $s counts: $(for f in DE DIR t2de t2dir; do for v in C D; do echo -n "$f-$v=$(grep -c '=== Prompt' $AB/${f}_prompts_${v}_s$s.txt) "; done; done)"
done
echo "ALL ABLATION PROMPTS DONE $(date)"
