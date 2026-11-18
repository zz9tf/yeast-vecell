#!/bin/bash
set -e
cd /home/zhengz2/projects/yeast-vecell
PY=/usr/bin/python3.12
B=data/task2b
for s in 0 1 2; do
  echo "===== seed $s $(date +%H:%M:%S) ====="
  $PY src/task2b/cli.py de  retrieve --data-csv $B/sga_full_DE_pairs.csv  --out $B/t2bde_retr_full_s$s.json  --budget 10 --seed $s
  $PY src/task2b/cli.py de  prompt   --retrieval $B/t2bde_retr_full_s$s.json  --out $B/t2bde_prompts_full_s$s.txt --context-idx 0
  $PY src/task2b/cli.py dir retrieve --data-csv $B/sga_full_DIR_pairs.csv --out $B/t2bdir_retr_full_s$s.json --budget 10 --seed $s
  $PY src/task2b/cli.py dir prompt   --retrieval $B/t2bdir_retr_full_s$s.json --out $B/t2bdir_prompts_full_s$s.txt --context-idx 0
  echo "seed $s done: DE=$(grep -c 'End of Query' $B/t2bde_prompts_full_s$s.txt) DIR=$(grep -c 'End of Query' $B/t2bdir_prompts_full_s$s.txt)"
done
echo "ALL T2B PROMPTS DONE $(date)"
