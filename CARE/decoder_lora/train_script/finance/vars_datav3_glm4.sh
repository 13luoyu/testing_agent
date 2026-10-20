#!/bin/bash

output_dir=./output/finance/v3/glm4
predict_dir=./predict_data/finance/v3/glm4
train_files=../data/data_for_LLM_decoder/glm4/formalization_train_data_augmented.csv
validation_files=../data/data_for_LLM_decoder/glm4/formalization_validate_data.csv
all_files=../data/data_for_LLM_decoder/glm4/formalization_data.csv
target_modules=query_key_value,dense,dense_h_to_4h,dense_4h_to_h
model_name_or_path=../model/pretrained/glm-4-9b-chat
model_type=glm4

