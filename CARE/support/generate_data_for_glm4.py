import json
import os


def main(root_dir, transfer_func):
    datas = json.load(open(f"{root_dir}../formalization_data.json", "r", encoding="utf-8"))
    s = transfer_func(datas)
    with open(root_dir + "formalization_data.csv", "w", encoding="utf-8") as f:
        f.write(s)
    datas = json.load(open(f"{root_dir}../formalization_train_data.json", "r", encoding="utf-8"))
    s = transfer_func(datas)
    with open(root_dir + "formalization_train_data.csv", "w", encoding="utf-8") as f:
        f.write(s)
    datas = json.load(open(f"{root_dir}../formalization_validate_data.json", "r", encoding="utf-8"))
    s = transfer_func(datas)
    with open(root_dir + "formalization_validate_data.csv", "w", encoding="utf-8") as f:
        f.write(s)
    datas = json.load(open(f"{root_dir}../formalization_train_data_augmented.json", "r", encoding="utf-8"))
    s = transfer_func(datas)
    with open(root_dir + "formalization_train_data_augmented.csv", "w", encoding="utf-8") as f:
        f.write(s)


def generate_llm_chat_data(datas):
    s = "\"text\"\n"
    for data in datas:
        prompt = data['prompt']
        system, user = prompt.split("\n")[0], "\n".join(prompt.split("\n")[1:])
        s += f"\"[gMASK]<sop><|system|>\n你是一个金融科技领域的专家。{system}<|user|>\n{user}<|assistant|>\n{data['answer']}<|user|>\"\n"
    return s



if __name__ == "__main__":
    root_dir = "../data/data_for_LLM_decoder/glm4/"
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)
    main(root_dir, generate_llm_chat_data)
