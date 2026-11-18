#!/bin/bash
LOG=/home/zhengz2/yeast-vecell/data/runs/val_infer.log
exec > "$LOG" 2>&1
set -x
cd /home/zhengz2/yeast-vecell/src/cli_pipeline
export CUDA_VISIBLE_DEVICES=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
echo "host=$(hostname) $(date)"
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader | head -1
MODEL_DIR=$(ls -d /home/zhengz2/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/*/ | head -1)
echo "model=$MODEL_DIR"
/home/zhengz2/miniconda3/envs/inplacettt/bin/python cli.py de infer \
  --model "$MODEL_DIR" \
  --prompts /home/zhengz2/yeast-vecell/data/runs/DE_val_prompts.txt \
  --out /home/zhengz2/yeast-vecell/data/runs/DE_val_pred_qwen7b.txt \
  --batch-size 8 --max-new-tokens 1024 --dtype bfloat16 --device-map auto
echo "PY_EXIT=$?"
echo "infer DONE $(date)"
