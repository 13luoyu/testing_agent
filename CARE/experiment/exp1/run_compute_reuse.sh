#!/bin/bash

methods=("ours" "gemini" "gpt" "grok" "expert" "RPTSP" "ESIM")
datasets=("dataset1" "dataset2" "dataset3" "dataset4" "dataset5" "dataset6")

for method in "${methods[@]}"; do
  for dataset in "${datasets[@]}"; do
    nohup python compute_reuse.py \
      --method "$method" \
      --dataset "$dataset" \
      > "log/run_compute_reuse_${method}_${dataset}.log" &
  done
done

