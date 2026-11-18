#!/bin/bash
# Re-run GAT/GenKI/KGE-TGI/MultiXrank with --dump-preds to get per-case test
# predictions (never saved before) for the Task-1 decomposition tables.
# Same seeds/hyperparams as the already-recorded aggregate runs -> scores will
# match data/runs/*_baseline/*_seedN.json exactly, this only adds per-case detail.
set -e
cd /home/zhengz2/projects/yeast-vecell
PY=/home/zhengz2/miniconda3/envs/dtibase/bin/python
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
R=data/runs

for task in de dir; do
  for s in 0 1 2; do
    echo "===== gat $task s$s $(date +%H:%M:%S) ====="
    $PY src/eval/gat_baseline.py --task $task --seed $s \
      --dump-preds $R/gat_baseline/preds/gat_${task}_s${s}.json \
      --json /tmp/gat_${task}_s${s}_check.json
  done
done

for task in de dir; do
  for s in 0 1 2; do
    echo "===== genki $task s$s $(date +%H:%M:%S) ====="
    $PY src/eval/genki_baseline.py --task $task --seed $s \
      --dump-preds $R/genki_baseline/preds/genki_${task}_s${s}.json \
      --json /tmp/genki_${task}_s${s}_check.json
  done
done

for task in de dir; do
  for s in 0 1 2; do
    echo "===== kge_tgi $task s$s $(date +%H:%M:%S) ====="
    $PY src/eval/kge_tgi_baseline.py --task $task --seed $s \
      --dump-preds $R/kge_tgi_baseline/preds/kge_${task}_s${s}.json \
      --json /tmp/kge_${task}_s${s}_check.json
  done
done

for task in de dir; do
  for s in 0 1 2; do
    echo "===== multixrank $task s$s $(date +%H:%M:%S) ====="
    $PY src/eval/multixrank_baseline.py --task $task --seed $s \
      --dump-preds $R/multixrank_baseline/preds/multixrank_${task}_s${s}.json \
      --json /tmp/multixrank_${task}_s${s}_check.json
  done
done

echo "ALL DECOMP-ML PREDS DONE $(date)"
