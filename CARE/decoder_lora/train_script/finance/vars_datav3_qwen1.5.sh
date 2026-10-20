#!/bin/bash

output_dir=./output/qwen1.5
predict_dir=./predict_data/qwen1.5
train_files=../data/data_for_LLM_decoder/qwen2/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/qwen2/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/qwen2/formalization_data.csv
model_name_or_path=../model/pretrained/Qwen1.5-4B-Chat
target_modules=q_proj,k_proj,v_proj,o_proj,down_proj,gate_proj,up_proj
model_type=qwen2


