#!/bin/bash

# ps -ef|grep python | grep compute_bsc.py | awk '{print $2}' | xargs kill -9

mkdir -p log

methods=("ours" "no_requirement" "no_scenario" "directly" "no_change_impact_analysis" "ESIM" "RPTSP" "llm4fin")
datasets=("dataset1" "dataset2" "dataset3" "dataset4" "dataset5" "dataset6")

for method in "${methods[@]}"; do
  for dataset in "${datasets[@]}"; do
    nohup python compute_bsc.py \
      --method "$method" \
      --dataset "$dataset" \
      > "log/run_compute_bsc_${method}_${dataset}.log" &
  done
done
