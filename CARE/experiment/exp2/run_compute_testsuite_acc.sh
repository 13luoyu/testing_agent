#!/bin/bash

# ps -ef|grep python | grep compute_testsuite_acc.py | awk '{print $2}' | xargs kill -9

mkdir -p log

methods=("ours" "directly" "no_change_impact_analysis", "llm4fin")
datasets=("dataset1" "dataset2" "dataset3" "dataset4" "dataset5" "dataset6")

for method in "${methods[@]}"; do
  for dataset in "${datasets[@]}"; do
    nohup python compute_testsuite_acc.py \
      --method "$method" \
      --dataset "$dataset" \
      > "log/run_compute_testsuite_acc_${method}_${dataset}.log" &
  done
done
