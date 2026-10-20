import json
import os
from support.generate_data_for_glm4 import main


def generate_llm_chat_data(datas):
    s = "\"text\"\n"
    for data in datas:
        prompt = data['prompt']
        system, user = prompt.split("\n")[0], "\n".join(prompt.split("\n")[1:])
        s += f"\"<|im_start|>system\n你是一个金融科技领域的专家。{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{data['answer']}<|im_end|>\"\n"
    return s



if __name__ == "__main__":
    root_dir = "../data/data_for_LLM_decoder/qwen2/"
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)
    main(root_dir, generate_llm_chat_data)
