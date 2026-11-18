#!/bin/bash
LOG=/home/zhengz2/projects/yeast-vecell/data/runs/vllm_probe.log
exec > "$LOG" 2>&1
set -x
export CUDA_VISIBLE_DEVICES=3
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_LOGGING_LEVEL=WARNING
export CUDA_HOME=/home/zhengz2/miniconda3/envs/vllm
export PATH=$CUDA_HOME/bin:$PATH
export VLLM_USE_V1=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
MODEL=$(ls -d /home/zhengz2/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/*/ | head -1)
echo "host=$(hostname) $(date)"
/home/zhengz2/miniconda3/envs/vllm/bin/python /home/zhengz2/projects/yeast-vecell/src/eval/infer_vllm.py \
  --model "$MODEL" --prompts /home/zhengz2/projects/yeast-vecell/data/runs/DE_prompts500.txt \
  --out /home/zhengz2/projects/yeast-vecell/data/runs/vllm_probe_pred.txt --max-model-len 6144
echo "PROBE DONE $(date)"
