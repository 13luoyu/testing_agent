import json
import os
from support.generate_data_for_glm4 import main

def generate_llm_chat_data(datas):
    s = "\"text\"\n"
    for data in datas:
        prompt = data['prompt']
        system, user = prompt.split("\n")[0], "\n".join(prompt.split("\n")[1:])
        s += f"\"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n你是一个金融科技领域的专家。{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n{data['answer']}<|eot_id|><|end_of_text|>\"\n"
    return s



if __name__ == "__main__":
    root_dir = "../data/data_for_LLM_decoder/llama3/"
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)
    main(root_dir, generate_llm_chat_data)
