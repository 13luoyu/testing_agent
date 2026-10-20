#!/bin/bash

output_dir=./output/llama3-instruct
predict_dir=./predict_data/llama3-instruct
train_files=../data/data_for_LLM_decoder/llama3/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/llama3/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/llama3/formalization_data.csv
model_name_or_path=../model/pretrained/Meta-Llama-3-8B-Instruct
target_modules=q_proj,k_proj,v_proj,o_proj,down_proj,gate_proj,up_proj
model_type=llama3

