# 如果没有需求，相当于没有形式化表示。
# 我们的步骤：
## 1. 构建规则-测试用例关系，直接用LLM构建
## 2. 变更识别，直接用LLM识别
## 3. 测试用例更新/重用，不考虑scenario关系，只考虑本身

# nohup python -u generate_testcase_no_requirement.py >log/generate_testcase_no_requirement.log &


from time import sleep
import json
import os
from reuse.rule_testcase_relation_mining import get_rules
import requests
from tqdm import tqdm


classification_knowledge_file = "../../reuse/domain_knowledge/classification_knowledge.json"
knowledge_file = "../../reuse/domain_knowledge/knowledge.json"
sc_model = "../../model/trained/mengzi_rule_filtering"
tc_model = "../../model/trained/glm4_lora_exp"



# def request_llm(system_prompt, user_prompt):
#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user", "content": user_prompt}
#     ]
#     # 循环调用直到不出错
#     while True:
#         try:
#             response = requests.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers={"Authorization": "01756160e2e140b3ab68c70e06498377.vYJE7Xuin6MLfl6m", "Content-Type": "application/json"}, json={"model": "GLM-4.5-Flash", "messages": messages, "temperature": 0.7}).json()
#             content = response['choices'][0]['message']['content'].replace("\"", "\\\"").replace("'", '"')
#             print(content)
#             if "```json" in content:
#                 content = content.split("```json")[1].split("```")[0].strip()
#             elif "```" in content:
#                 content = content.split("```")[1].strip()
#             result = json.loads(content)
#             return result
#         except Exception as e:
#             print(f"Error occurred: {e}. Retrying...")
#             continue

port = json.load(open("../../qwen3_service/config.json", "r", encoding="utf-8"))['port']
def request_llm(system_prompt, user_prompt):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    # 循环调用直到不出错
    while True:
        try:
            response = requests.post(f"http://127.0.0.1:{port}/chat", json={"messages": messages}).json()
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



def generate_testcase_no_requirement(old_rule_file, old_testcase_file, upd_rule_file):
    dataset = old_rule_file.split("/")[-1].split("_")[0]
    old_testcases = json.load(open(old_testcase_file, "r", encoding="utf-8"))
    old_texts, old_market_variety, old_sco = get_rules(old_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in old_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    # old_texts: [{'id': '10000', 'text': '纽约证券交易所拍卖市场买入和卖出规则（2015）', 'type': '1'}]

    # 构建old_texts和old_testcases的关系
    system_prompt = '你是一个法律专家。请判断给定的测试用例TC是否为给定的法律规则R的测试用例，即TC是不是在测试R。注意：1. TC不一定完整测试R，可能只测试R的一部分；2. TC可以是成功测试用例（所有条件完全符合规则），也可以是失败测试用例（部分条件不符合规则）。返回格式为{"is_TC_of_R": true/false, "reason": "简单一句话说明原因"}，不要输出任何其他内容。'
    relation = {}  # {"rule_id": ["testcase_id", ...], ...}
    for rule in tqdm(old_texts):
        rule_id = rule['id']
        rule_text = rule['text']
        relation[rule_id] = []
        for idx, testcases in enumerate(old_testcases):
            testcase = testcases[0]
            testcase_id = testcase['testid']
            tc_rule_id = testcase['rule']
            del testcase['testid']
            del testcase['rule']
            user_prompt = f"法律规则R：{rule_text}\n\n测试用例TC：{json.dumps(testcase, ensure_ascii=False)}"
            if request_llm(system_prompt, user_prompt)['is_TC_of_R']:
                relation[rule_id].append(testcase_id)
                for tc in testcases[1:]:
                    relation[rule_id].append(tc['testid'])
            testcase['testid'] = testcase_id
            testcase['rule'] = tc_rule_id
    print("Constructed rule-testcase relation.")
    json.dump(relation, open(f"no_requirement/{dataset}_rule_testcase_relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    # 变更识别
    system_prompt = '你是一个法律专家。我给你一篇旧法规文档，以及一条新的规则，你要判断这条新规则是否在旧法规中出现。当新规则在内容、约束、义务或权利等方面与所有旧规则有不同，认为没有出现；如果仅仅是某条旧规则措辞或格式上的修改，认为出现。注意：相较某条旧规则大幅度或实质性的增加、删除、修改视为没有出现。返回格式为{"occur": true/false, "rule_id": "对应的旧规则的id", "reason": "简单一句话说明原因"}，不要输出任何其他内容。'
    new_texts, new_market_variety, new_sco = get_rules(upd_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in upd_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    del_rule_ids, add_rule_ids = [], []

    for new_rule in tqdm(new_texts):
        new_rule_id = new_rule['id']
        new_rule_text = new_rule['text']
        find = False
        for old_rule in old_texts:
            old_rule_id = old_rule['id']
            old_rule_text = old_rule['text']
            if new_rule_text == old_rule_text:
                find = True
                break
        if find:
            continue
        # 需要和所有旧规则比较
        user_prompt = f"旧法规文档：{json.dumps(old_texts, ensure_ascii=False)}\n\n新的规则：{new_rule_text}"
        result = request_llm(system_prompt, user_prompt)
        if not result['occur']:
            del_rule_ids.append(result['rule_id'])
            add_rule_ids.append(new_rule_id)
    changed_rule_ids = add_rule_ids + del_rule_ids
    changed_rule_ids = list(set(changed_rule_ids))
    changed_rule_ids = [s for s in changed_rule_ids if s]
    json.dump(changed_rule_ids, open(f"no_requirement/{dataset}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Identified changed rules.")

    # 测试用例更新/重用
    testcase = json.load(open(old_testcase_file, "r", encoding="utf-8"))
    testcase = [t for ti in testcase for t in ti]
    # 删除
    for del_rule_id in del_rule_ids:
        if del_rule_id in relation:
            del_testcase_ids = relation[del_rule_id]
            testcase = [t for t in testcase if t['testid'] != del_testcase_ids]
    # 新增
    system_prompt = '你是一个法律专家。请根据下面的法律规则，生成若干相关的测试用例。每条测试用例是一个json格式{testid: 1/2/3... , key1: value1, key2: value2, ...}，其中testid请用一个不重复的数字表示。例如，规则‘主做市商对基准做市品种开展持续做市交易’的测试用例可以是[{"testid": "1", "操作人": "主做市商", "交易品种": "基准做市品种", "操作部分": "持续做市业务", ...}, ...]。请返回一个json数组，包含所有生成的测试用例，不要输出任何其他内容。'
    for add_rule_id in tqdm(add_rule_ids):
        add_rule_text = ""
        for rule in new_texts:
            if rule['id'] == add_rule_id:
                add_rule_text = rule['text']
                break
        user_prompt = f"法律规则：{add_rule_text}"
        new_testcases = request_llm(system_prompt, user_prompt)
        for idx, t in enumerate(new_testcases):
            t['rule'] = add_rule_id
            testcase.append(t)
    print("Updated testcases.")
    json.dump(testcase, open(f"no_requirement/{dataset}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)















if __name__ == "__main__":
    for i in range(1, 7):
        ini_file = f"dataset{i}_ini_rule.txt" if f"dataset{i}_ini_rule.txt" in os.listdir("data") else f"dataset{i}_ini_rule.pdf"
        upd_file = f"dataset{i}_upd_rule.txt" if f"dataset{i}_upd_rule.txt" in os.listdir("data") else f"dataset{i}_upd_rule.pdf"
        print(f"Processing {upd_file}...")
        generate_testcase_no_requirement(f"data/{ini_file}", f"data/{ini_file.split('.')[0][:-5]}_testcase.json", f"data/{upd_file}")
        print(f"{upd_file} finished.")