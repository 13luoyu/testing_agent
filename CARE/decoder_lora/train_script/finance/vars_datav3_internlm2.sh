#!/bin/bash

output_dir=./output/internlm2
predict_dir=./predict_data/internlm2
train_files=../data/data_for_LLM_decoder/internlm2/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/internlm2/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/internlm2/formalization_data.csv
model_name_or_path=../model/pretrained/internlm2-7b
target_modules=wqkv,wo,w1,w2,w3
model_type=internlm2

