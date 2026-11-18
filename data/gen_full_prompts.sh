#!/bin/bash
cd /home/zhengz2/projects/yeast-vecell/src/cli_pipeline
PY=/usr/bin/python3.12; R=../../data/runs; T=../../data/task2; K=../../data/knowledge
for s in 0 1 2; do
  echo "===== seed $s $(date +%H:%M:%S) ====="
  # T1a DE (full test)
  $PY cli.py de  retrieve --data-csv $R/deleteome_DE.csv  --out $R/DE_retr_full_s$s.json  --budget 10 --seed $s
  $PY cli.py de  prompt   --retrieval $R/DE_retr_full_s$s.json  --out $R/DE_prompts_full_s$s.txt  --context-idx 0
  # T1b DIR (full)
  $PY cli.py dir retrieve --data-csv $R/deleteome_DIR.csv --out $R/DIR_retr_full_s$s.json --budget 10 --seed $s
  $PY cli.py dir prompt   --retrieval $R/DIR_retr_full_s$s.json --out $R/DIR_prompts_full_s$s.txt --context-idx 0
  # T2A-DE (Hillenmeyer full)
  $PY cli.py de  retrieve --data-csv $T/hillenmeyer_phenotype.csv --readout-col context --pert-sim $K/perturbagen_similarity.json --gene-sim $K/condition_similarity.json --out $T/t2de_retr_full_s$s.json --budget 10 --seed $s
  $PY cli.py de  prompt   --retrieval $T/t2de_retr_full_s$s.json --template ../../support/task2/DE_template.py --gene-desc $T/context_desc.json --pert-desc $K/gene_desc.json --out $T/t2de_prompts_full_s$s.txt --context-idx 0
  # T2A-DIR (Hillenmeyer full)
  $PY cli.py dir retrieve --data-csv $T/hillenmeyer_direction.csv --readout-col context --pert-sim $K/perturbagen_similarity.json --gene-sim $K/condition_similarity.json --out $T/t2dir_retr_full_s$s.json --budget 10 --seed $s
  $PY cli.py dir prompt   --retrieval $T/t2dir_retr_full_s$s.json --template ../../support/task2/DIR_template.py --gene-desc $T/context_desc.json --pert-desc $K/gene_desc.json --out $T/t2dir_prompts_full_s$s.txt --context-idx 0
  echo "seed $s done: DE=$(grep -c '=== Prompt' $R/DE_prompts_full_s$s.txt) DIR=$(grep -c '=== Prompt' $R/DIR_prompts_full_s$s.txt) T2DE=$(grep -c '=== Prompt' $T/t2de_prompts_full_s$s.txt) T2DIR=$(grep -c '=== Prompt' $T/t2dir_prompts_full_s$s.txt)"
done
echo "ALL PROMPTS DONE $(date)"
