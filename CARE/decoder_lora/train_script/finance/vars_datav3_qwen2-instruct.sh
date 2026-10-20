#!/bin/bash

output_dir=./output/qwen2-instruct
predict_dir=./predict_data/qwen2-instruct
train_files=../data/data_for_LLM_decoder/qwen2/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/qwen2/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/qwen2/formalization_data.csv
model_name_or_path=../model/pretrained/Qwen2-7B-Instruct
target_modules=q_proj,k_proj,v_proj,o_proj,down_proj,gate_proj,up_proj
model_type=qwen2


