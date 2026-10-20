from transformers import AutoModelForSequenceClassification, AutoTokenizer
import json
import torch
import requests
from time import sleep


def request_llm(system_prompt, user_prompt):
    port = json.load(open("../../qwen3_service/config.json", "r", encoding="utf-8"))['port']
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    # 循环调用直到不出错
    while True:
        try:
            response = requests.post(f"http://127.0.0.1:{port}/chat", json={"messages": messages, "temperature": 1.0, "do_sample": False, "repetition_penalty": 1.3}).json()
            content = response['response']
            print(content)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
            result = json.loads(content)
            return result
        except Exception as e:
            print(f"Error occurred: {e}. Retrying...")
            sleep(1)
            continue


def sequence_classification_api(sci, model_path, batch_size=8, sequence_max_length=512):
    system_prompt = '你是一位需求专家，请判断给定的规则是否是需求。需求指的是可以用软件或硬件实现的具体的功能、非功能需求等，而不是抽象的说明、背景、解释性知识、标题、目录等内容。输出格式为{"is_requirement": true/false, "reason": "简单一句话说明原因"}，不要输出任何其他内容。'
    for i, sc in enumerate(sci):
        user_prompt = f"规则文本：{sc['text']}"
        result = request_llm(system_prompt, user_prompt)
        if result['is_requirement']:
            sco_type = '1'
        else:
            sco_type = '0'
        sci[i]['type'] = sco_type
    return sci



def sequence_classification(sci, model_path, batch_size=8, sequence_max_length=512):
    """
    主函数: 使用mengzi模型对sci数据进行分类，返回带有分类结果的数据sco
    """

    if "api" in model_path:
        return sequence_classification_api(sci, model_path, batch_size, sequence_max_length)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForSequenceClassification.from_pretrained(model_path, num_labels=3)
    model.eval()
    model.to(device)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    inputs = [s['text'] for s in sci]

    def predict_sequence_classification(inputs):
        outputs = []
        for i in range(0, len(sci), batch_size):
            batch = inputs[i:i + batch_size]
            input_ids = tokenizer(batch, padding="max_length", truncation=True, max_length=sequence_max_length, return_tensors="pt").input_ids
            input_ids = input_ids.to(device)
            logits = model(input_ids = input_ids).logits
            _, output = torch.max(logits, dim=1)
            output = output.cpu().numpy().tolist()
            outputs.extend(output)
        return outputs

    with torch.no_grad():
        outputs = predict_sequence_classification(inputs)
    sco = sci.copy()
    for i, output in enumerate(outputs):
        sco[i]["type"] = str(output)
    
    return sco




if __name__ == "__main__":
    sci_data = json.load(open("cache/sci.json", "r", encoding="utf-8"))
    sco_data = sequence_classification(sci_data, "../model/trained/encoder/mengzi_rule_filtering")
    json.dump(sco_data, open("cache/sco.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)


