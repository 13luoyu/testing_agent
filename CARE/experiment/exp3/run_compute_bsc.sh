#!/bin/bash

methods=("ours")
datasets=("dataset1" "dataset2" "dataset3" "dataset4" "dataset5")

for method in "${methods[@]}"; do
  for dataset in "${datasets[@]}"; do
    nohup python compute_bsc.py \
      --method "$method" \
      --dataset "$dataset" \
      > "log/run_compute_bsc_${method}_${dataset}.log" &
  done
done
