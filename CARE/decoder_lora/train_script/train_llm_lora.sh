#!/bin/bash


# ------------------------------------------------------------------------------------------------------------------------------------------------------
# run command (finance):
# ----- v3 -----
# ************ glm4 ************
# nohup bash train_llm_lora.sh finance/vars_datav3_glm4.sh >../output/glm4/run_glm4.log &

# ************ internlm2 ************
# nohup bash train_llm_lora.sh finance/vars_datav3_internlm2.sh >../output/internlm2/run_internlm2.log &

# ************ llama3-instruct ************
# nohup bash train_llm_lora.sh finance/vars_datav3_llama3-instruct.sh >../output/llama3-instruct/run_llama3-instruct.log &

# ************ qwen2 ************
# nohup bash train_llm_lora.sh finance/vars_datav3_qwen2-instruct.sh >../output/qwen2-instruct/run_qwen2-instruct.log &

# ************ llama3.2-1B-instruct ************
# nohup bash train_llm_lora.sh finance/vars_datav3_llama3.2-instruct-1B.sh >../output/llama3.2-instruct-1B/run_llama3.2-instruct-1B.log &

# ************ llama3.2-3B-instruct ************
# nohup bash train_llm_lora.sh finance/vars_datav3_llama3.2-instruct-3B.sh >../output/llama3.2-instruct-3B/run_llama3.2-instruct-3B.log &

# ************ chatglm3 ************
# nohup bash train_llm_lora.sh finance/vars_datav3_chatglm3.sh >../output/chatglm3/run_chatglm3.log &

# ************ qwen1.5 ************
# nohup bash train_llm_lora.sh finance/vars_datav3_qwen1.5.sh >../output/qwen1.5/run_qwen1.5.log &
# ------------------------------------------------------------------------------------------------------------------------------------------------------


# 变量定义
vars=$1

source $vars
# 现在output_dir、predict_dir、train_files、validation_files、all_files、model_name_or_path、model_type、target_modules已定义
cd ..

if [ ! -d ${output_dir} ];then  
    mkdir -p ${output_dir}
fi
if [ ! -d ${predict_dir} ];then  
    mkdir -p ${predict_dir}
fi

# 如果glm4在model_name_or_path中，不使用flash attention
if [[ ${model_name_or_path} == *"glm"* ]]; then
    use_flash_attention=false
else
    use_flash_attention=true
fi

# 训练模型
python train_lora_model.py \
    --model_name_or_path ${model_name_or_path} \
    --train_files ${train_files} \
    --validation_files ${validation_files} \
    --per_device_train_batch_size 1 \
    --per_device_eval_batch_size 1 \
    --do_train \
    --do_eval \
    --use_fast_tokenizer false \
    --output_dir ${output_dir} \
    --evaluation_strategy  steps \
    --max_eval_samples 800 \
    --learning_rate 1e-5 \
    --gradient_accumulation_steps 8 \
    --num_train_epochs 10 \
    --warmup_steps 800 \
    --load_in_bits 4 \
    --lora_r 8 \
    --lora_alpha 16 \
    --target_modules ${target_modules} \
    --logging_dir ${output_dir}/logs \
    --logging_strategy steps \
    --logging_steps 10 \
    --save_strategy steps \
    --preprocessing_num_workers 10 \
    --save_steps 300 \
    --eval_steps 100 \
    --save_total_limit 20 \
    --seed 42 \
    --ddp_find_unused_parameters false \
    --report_to tensorboard \
    --overwrite_output_dir \
    --ignore_data_skip true \
    --bf16 \
    --gradient_checkpointing \
    --bf16_full_eval \
    --ddp_timeout 18000000 \
    --torch_dtype float16 \
    --test_output_file ${predict_dir}/predict_result_framework.txt \
    --disable_tqdm true \
    --load_best_model_at_end true \
    --block_size 4096 \
    --optimizer AdamW32bit \
    --use_flash_attention ${use_flash_attention}


# 初始化一个空数组来存储所有文件的整数部分
file_numbers=()
# 这里的目录需要替换成你实际的目录
for file in $(find $output_dir -type d -name 'best_lora_model_*' | grep -oP 'best_lora_model_\K\d+'); do
    file_numbers+=("$file")
done
# 如果没有找到任何文件，则退出脚本
if [ ${#file_numbers[@]} -eq 0 ]; then
    echo "没有找到匹配的文件。"
    exit 1
fi
# 使用sort和tail找到最大的整数
max_number=$(printf "%s\n" "${file_numbers[@]}" | sort -n | tail -1)
# 构建最大的文件名
filename="best_lora_model_$max_number"


# 预测
python predict.py \
    --model_name_or_path ${output_dir}/${filename} \
    --mode 4bit-lora \
    --tokenizer_fast false \
    --eval_dataset ${validation_files} \
    --prediction_file ${predict_dir}/predict_result_${filename}_4bit_load_lora.json \
    --model_type ${model_type}

python predict.py \
    --model_name_or_path ${output_dir}/${filename} \
    --mode 4bit-lora \
    --tokenizer_fast false \
    --eval_dataset ${all_files} \
    --prediction_file ${predict_dir}/predict_result_${filename}_4bit_load_lora_all.json \
    --model_type ${model_type}


cd ${output_dir}
rm -rf checkpoint-*


