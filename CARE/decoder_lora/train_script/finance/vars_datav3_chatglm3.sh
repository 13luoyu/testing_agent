#!/bin/bash

output_dir=./output/chatglm3
predict_dir=./predict_data/chatglm3
train_files=../data/data_for_LLM_decoder/chatglm3/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/chatglm3/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/chatglm3/formalization_data.csv
target_modules=query_key_value,dense,dense_h_to_4h,dense_4h_to_h
model_name_or_path=../model/pretrained/chatglm3-6b
model_type=chatglm3

