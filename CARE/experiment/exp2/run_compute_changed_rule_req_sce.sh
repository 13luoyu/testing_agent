#!/bin/bash

# ps -ef|grep python | grep compute_changed_rule_req_sce.py | awk '{print $2}' | xargs kill -9

mkdir -p log

methods=("ours" "no_requirement" "no_scenario" "no_change_impact_analysis" "ESIM" "RPTSP")
datasets=("dataset1" "dataset2" "dataset3" "dataset4" "dataset5" "dataset6")

for method in "${methods[@]}"; do
  for dataset in "${datasets[@]}"; do
    nohup python compute_changed_rule_req_sce.py \
      --method "$method" \
      --dataset "$dataset" \
      > "log/run_compute_changed_rule_req_sce_${method}_${dataset}.log" &
  done
done
