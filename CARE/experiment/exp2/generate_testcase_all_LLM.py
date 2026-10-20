# 每一个步骤都使用LLM完成


import json
import os
from reuse.rule_testcase_relation_mining import get_rules
import requests
from tqdm import tqdm
from experiment.exp2.generate_testcase_no_requirement import request_llm
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r

classification_knowledge_file = "../../reuse/domain_knowledge/classification_knowledge.json"
knowledge_file = "../../reuse/domain_knowledge/knowledge.json"
sc_model = "../../model/trained/mengzi_rule_filtering"
tc_model = "../../model/trained/glm4_lora_exp"




def generate_testcase_all_llm(old_rule_file, old_testcase_file, upd_rule_file):
    dataset = old_rule_file.split("/")[-1].split(".json")[0]
    old_testcases = json.load(open(old_testcase_file, "r", encoding="utf-8"))
    old_texts, old_market_variety, old_sco = get_rules(old_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in old_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    # old_texts: [{'id': '10000', 'text': '纽约证券交易所拍卖市场买入和卖出规则（2015）', 'type': '1'}]

    # 生成需求
    clasification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    knowledge = json.load(open(knowledge_file, "r", encoding="utf-8"))
    fo = rule_formalization(old_texts, tc_model)
    r1 = to_r(fo, fix=True)  # mydsl format
    with open(f"all_llm/{dataset}_requirement.mydsl", "w", encoding="utf-8") as f:
        f.write(r1)

    # 生成场景，对齐测试用例和场景
    system_prompt = '你是一个法律专家。请判断给定的测试用例TC是否为给定的法律规则R的测试用例，即TC是不是在测试R。注意：1. TC不一定完整测试R，可能只测试R的一部分；2. TC可以是成功测试用例（所有条件完全符合规则），也可以是失败测试用例（部分条件不符合规则）。输入包括两项，规则R的自然语言表示，以及一种形式化表示FR。输出格式为{"is_TC_of_R": true/false, "reason": "简单一句话说明原因"}，不要输出任何其他内容。'
    relation = {}  # {"rule_id": ["testcase_id", ...], ...}
    old_rules = r1.strip().split("\n\n")
    input_data = {}  # {"rule_id": {"rule": "", "requirement": ""}}
    for req in old_rules:
        rule_id = ""
        for line in req.split("\n"):
            if "sourceid" in line.lower():
                rule_id = line.split(" ")[-1].strip()
                break
        if rule_id == "":
            continue
        if rule_id not in input_data:
            input_data[rule_id] = {"rule": "", "requirement": req}
            for rule in old_texts:
                if rule['id'] == rule_id:
                    input_data[rule_id]["rule"] = rule['text']
                    break
        else:
            input_data[rule_id]["requirement"] += "\n\n" + req

    for rule_id in tqdm(input_data):
        rule_text = input_data[rule_id]["rule"]
        requirement = input_data[rule_id]["requirement"]
        relation[rule_id] = []
        for idx, testcases in enumerate(old_testcases):
            testcase = testcases[0]
            testcase_id = testcase['testid']
            tc_rule_id = testcase['rule']
            del testcase['testid']
            del testcase['rule']
            user_prompt = f"法律规则R：{rule_text}\n\n形式化表示FR：{requirement}\n\n测试用例TC：{json.dumps(testcase, ensure_ascii=False)}"
            if request_llm(system_prompt, user_prompt)['is_TC_of_R']:
                relation[rule_id].append(testcase_id)
                for tc in testcases[1:]:
                    relation[rule_id].append(tc['testid'])
            testcase['testid'] = testcase_id
            testcase['rule'] = tc_rule_id
    json.dump(relation, open(f"all_llm/{dataset}_rule_testcase_relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    
    # 变更识别
    system_prompt = '你是一个法律专家。我给你两条规则，你判断这两条规则是否"语义相同"。当两条规则在内容、约束、义务或权利等方面与所有旧规则有不同，认为不同；如果仅仅是旧规则措辞或格式上的修改，认为相同。注意：大幅度或实质性的增加、删除、修改视为不同。输入包括四项，规则1的自然语言R1，规则1的形式化表达FR1，规则2的自然语言R2，规则2的形式化表达FR2。返回格式为{"same": true/false, "rule_id": "对应的旧规则的id", "reason": "简单一句话说明原因"}，不要输出任何其他内容。'
    new_texts, new_market_variety, new_sco = get_rules(upd_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in upd_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    del_rule_ids, add_rule_ids = [], []
    fo = rule_formalization(new_texts, tc_model)
    f1 = to_r(fo, fix=True)  # mydsl format

    new_input_data = {}
    new_rules = f1.strip().split("\n\n")
    for req in new_rules:
        rule_id = ""
        for line in req.split("\n"):
            if "sourceid" in line.lower():
                rule_id = line.split(" ")[-1].strip()
                break
        if rule_id == "":
            continue
        if rule_id not in new_input_data:
            new_input_data[rule_id] = {"rule": "", "requirement": req}
            for rule in new_texts:
                if rule['id'] == rule_id:
                    new_input_data[rule_id]["rule"] = rule['text']
                    break
        else:
            new_input_data[rule_id]["requirement"] += "\n\n" + req
    
    same = {}  # same{old_rule_id: new_rule_id}
    for new_rule_id in tqdm(new_input_data):
        new_rule_text = new_input_data[new_rule_id]["rule"]
        new_requirement = new_input_data[new_rule_id]["requirement"]
        for old_rule_id in input_data:
            old_rule_text = input_data[old_rule_id]["rule"]
            old_requirement = input_data[old_rule_id]["requirement"]
            if new_rule_text == old_rule_text:
                same[old_rule_id] = new_rule_id
                continue
            user_prompt = f"规则1的自然语言R1：{old_rule_text}\n\n规则1的形式化表达FR1：{old_requirement}\n\n规则2的自然语言R2：{new_rule_text}\n\n规则2的形式化表达FR2：{new_requirement}"
            result = request_llm(system_prompt, user_prompt)
            if result['same']:
                same[old_rule_id] = new_rule_id
    
    for old_rule_id in input_data:
        if old_rule_id not in same:
            del_rule_ids.append(old_rule_id)
    for new_rule_id in new_input_data:
        if new_rule_id not in same.values():
            add_rule_ids.append(new_rule_id)
    changed_rule_ids = add_rule_ids + del_rule_ids
    changed_rule_ids = list(set(changed_rule_ids))
    changed_rule_ids = [s for s in changed_rule_ids if s]
    json.dump(changed_rule_ids, open(f"all_llm/{dataset}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    # 测试用例更新/重用
    testcase = json.load(open(old_testcase_file, "r", encoding="utf-8"))
    testcase = [t for ti in testcase for t in ti]
    # 删除
    for del_rule_id in del_rule_ids:
        if del_rule_id in relation:
            del_testcase_ids = relation[del_rule_id]
            testcase = [tc for tc in testcase if tc['testid'] not in del_testcase_ids]
    # 新增
    system_prompt = '你是一个法律专家。请根据下面的法律规则，生成若干相关的测试用例。每条测试用例是一个json格式{testid: 1/2/3... , key1: value1, key2: value2, ...}，其中testid请用一个不重复的数字表示。例如，规则‘主做市商对基准做市品种开展持续做市交易’的测试用例可以是[{"testid": "1", "操作人": "主做市商", "交易品种": "基准做市品种", "操作部分": "持续做市业务", ...}, ...]。输入包括规则的自然语言表达R，以及形式化表达FR。返回一个json数组，包含所有生成的测试用例，不要输出任何其他内容。'
    for add_rule_id in tqdm(add_rule_ids):
        add_rule_text = new_input_data[add_rule_id]["rule"]
        add_requirement = new_input_data[add_rule_id]["requirement"]
        user_prompt = f"法律规则R：{add_rule_text}\n\n形式化表达FR：{add_requirement}"
        new_testcases = request_llm(system_prompt, user_prompt)
        for idx, t in enumerate(new_testcases):
            t['rule'] = add_rule_id
            testcase.append(t)
    json.dump(testcase, open(f"all_llm/{dataset}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)



if __name__ == "__main__":
    for i in range(1, 7):
        ini_file = f"dataset{i}_ini_rule.txt" if f"dataset{i}_ini_rule.txt" in os.listdir("data") else f"dataset{i}_ini_rule.pdf"
        upd_file = f"dataset{i}_upd_rule.txt" if f"dataset{i}_upd_rule.txt" in os.listdir("data") else f"dataset{i}_upd_rule.pdf"
        print(f"Processing {upd_file}...")
        generate_testcase_all_llm(f"data/{ini_file}", f"data/dataset{i}_ini_testcase.json", f"data/{upd_file}")
        print(f"Finished processing {upd_file}.\n")