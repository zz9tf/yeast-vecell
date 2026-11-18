#!/bin/bash
# args: $1=hub_dirname  $2=gpu  $3=tag  $4=batch
LOG=/home/zhengz2/projects/yeast-vecell/data/runs/eval_$3.log
exec > "$LOG" 2>&1
set -x
cd /home/zhengz2/projects/yeast-vecell/src/cli_pipeline
export CUDA_VISIBLE_DEVICES=$2
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PY=/home/zhengz2/miniconda3/envs/inplacettt/bin/python
R=/home/zhengz2/projects/yeast-vecell/data/runs
MODEL_DIR=$(ls -d /home/zhengz2/.cache/huggingface/hub/$1/snapshots/*/ | head -1)
echo "TAG=$3 GPU=$2 MODEL=$MODEL_DIR host=$(hostname) $(date)"
$PY cli.py de  infer --model "$MODEL_DIR" --prompts $R/DE_prompts500.txt  --out $R/DE_pred_$3.txt  --batch-size $4 --max-new-tokens 1024 --dtype bfloat16 --device-map auto ; echo "DE_EXIT=$?"
$PY cli.py dir infer --model "$MODEL_DIR" --prompts $R/DIR_prompts500.txt --out $R/DIR_pred_$3.txt --batch-size $4 --max-new-tokens 1024 --dtype bfloat16 --device-map auto ; echo "DIR_EXIT=$?"
echo "ALL DONE $(date)"
