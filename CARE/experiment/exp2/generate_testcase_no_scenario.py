# 如果没有场景，则我们的步骤为：
## 1. 生成形式化需求
## 2. 需求-测试用例关系构建
## 3. 变更识别
## 4. 不考虑变更影响分析，直接重用/生成测试用例

# nohup python generate_testcase_no_scenario.py > log/generate_testcase_no_scenario.log &

import copy
import json
import os
import re
from reuse.rule_testcase_relation_mining import get_rules, rule_formalization, to_r, mydsl_to_rules, transfer_new_rule_format_to_old, is_number, contain_number
from reuse.update_testcase import rules_to_mydsl, transfer_old_rule_format_to_new
from reuse.process_r3_to_testcase import process_r3_to_testcase, is_num_key, is_price_key, is_time_key
from tqdm import tqdm



classification_knowledge_file = "../../reuse/domain_knowledge/classification_knowledge.json"
knowledge_file = "../../reuse/domain_knowledge/knowledge.json"
sc_model = "../../model/trained/mengzi_rule_filtering"
tc_model = "../../model/trained/glm4_lora_exp"



def judge_conflict(rule, testcase):
    """
    判断testcase是不是rule下的测试用例。
    首先看看rule和testcase的value是否能够匹配，要求必须完全相同
    """
    rule, testcase = copy.deepcopy(rule), copy.deepcopy(testcase)
    success = True
    if "结果" not in testcase or testcase['结果'] in ["不成功", "失败"]:
        success = False
    other_keys = ['测试关注点', 'testid', 'rule', '结果']
    rule_keys, rule_values = [], {}
    testcase_keys, testcase_values = [], {}
    
    if not success:  # 不考虑rule['results']中的状态和testcase中的结果状态
        rule['results'] = [r for r in rule['results'] if r['key'] != '状态']
        if "结果状态" in testcase:
            del testcase["结果状态"]
            index = 2
            while f"结果状态{index}" in testcase:
                del testcase[f"结果状态{index}"]
                index += 1
    for c in rule['constraints'] + rule['results']:
        if c['key'] in other_keys:  # 排除项
            continue
        cvalue = c['value']
        if cvalue[0] in ["不", "非"]:
            cvalue = cvalue[1:]
        if c['operation'] != "is":
            cvalue = c['operation'] + cvalue
            if cvalue[0] in ["不", "非"]:
                cvalue = cvalue[1:]
        if c['key'] not in rule_keys:  # 一般key
            rule_keys.append(c['key'])
            rule_values[c['key']] = [cvalue]
        else:
            rule_values[c['key']].append(cvalue)
    for k, v in testcase.items():
        # 简化k和v
        # k包含“操作2”这种表达，去掉尾部数字，但不能去掉中间数组
        k = re.sub(r"\d+$", "", k)
        # k包含“结果操作”这种表达，去掉结果
        if k.startswith("结果") and k != "结果":
            k = k[2:]

        # v包含“非接受”这种表达
        if v.startswith("非") or v.startswith("不"):
            v = v[1:]

        if k in other_keys:
            continue
        if k not in testcase_keys:
            testcase_keys.append(k)
            testcase_values[k] = [v]
        else:
            testcase_values[k].append(v)
    
    
    testcase_values_val = []
    for k in testcase_keys:
        testcase_values_val.extend(testcase_values[k])
    rule_values_val = []
    for k in rule_values:
        rule_values_val.extend(rule_values[k])
    
    all_cover = [False for _ in range(len(rule_values_val))]
    index = 0
    for k in rule_keys:
        values = rule_values[k]
        for j, value in enumerate(values):
            for k1 in testcase_keys:
                if k1 == value:
                    all_cover[index] = True
                    break
                for v in testcase_values[k1]:
                    if v == value:
                        all_cover[index] = True
                        break
                if all_cover[index]:
                    break
            
            if not all_cover[index]:
                for k1 in testcase_keys:
                    if k1 == k and \
                        (
                            is_time_key(k1) and re.findall(r"\d+:\d+", value) != [] and any([re.findall(r"\d+:\d+", vv) != [] for vv in testcase_values[k1]])
                            or 
                            (is_price_key(k1) or is_num_key(k1)) and is_number(value) and any([contain_number(v) for v in testcase_values[k1]])
                        ):
                        all_cover[index] = True
                        break
            index += 1
    
    # all_cover = [False for _ in range(len(testcase_values_val))]
    # index = 0
    # for i, key in enumerate(testcase_keys):
    #     values = testcase_values[key]
    #     for j, value in enumerate(values):
    #         for k in rule_keys:
    #             if k == value:
    #                 all_cover[index] = True
    #                 break
    #             for v in rule_values[k]:
    #                 if v == value:
    #                     all_cover[index] = True
    #                     break
    #             if all_cover[index]:
    #                 break
            
    #         if not all_cover[index]:
    #             for k in rule_keys:
    #                 if k == key and \
    #                     (
    #                         is_time_key(k) and re.findall(r"\d+:\d+", value) != [] and any([re.findall(r"\d+:\d+", vv) != [] for vv in rule_values[k]])
    #                         or 
    #                         (is_price_key(k) or is_num_key(k)) and is_number(value) and any([contain_number(v) for v in rule_values[k]])
    #                     ):
    #                     all_cover[index] = True
    #                     break
    #         index += 1

    return len(all_cover) > 0 and sum(all_cover) / len(all_cover) > 0.99 or False


def relation_mining(rules, testcases):
    if isinstance(rules, str):
        rules = mydsl_to_rules(rules)
    if isinstance(rules, list):
        rules = transfer_new_rule_format_to_old(rules)
    else:  # dict
        rules = rules

    if len(testcases) > 0 and isinstance(testcases[0], list):
        testcases = [item for sublist in testcases for item in sublist]
    
    relation = {}  # req_id: [testcase_id]
    
    for rule_id, rule in tqdm(rules.items()):
        source_ids = rule['rule_class']
        rule['rule'] = rule_id
        for testcase in testcases:
            testcase_id = testcase['testid']
            # 统计所有key在rule和testcase中的取值
            # 判断是否有关联
            is_related = judge_conflict(rule, testcase)
            if is_related:
                for source_id in source_ids:
                    if source_id in relation:
                        relation[source_id].append(testcase_id)
                    else:
                        relation[source_id] = [testcase_id]
    
    # 去重，因为可能将同一个测试用例多次匹配到同一个规则下的不同R规则
    for source_id in relation:
        relation[source_id] = list(set(relation[source_id]))
    
    return relation



def generate_testcase(old_rule_file, old_testcase_file, upd_rule_file):
    dataset = old_rule_file.split("/")[-1].split("_")[0]
    old_testcases = json.load(open(old_testcase_file, "r", encoding="utf-8"))

    # 构建old_texts和old_testcases的关系
    old_texts, old_mv, old_sco = get_rules(old_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in old_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    # old_texts: [{'id': '10000', 'text': '纽约证券交易所拍卖市场买入和卖出规则（2015）', 'type': '1'}]
    kwargs = {"temperature": 0.7, "do_sample": True, "top_p": 0.9, "repetition_penalty": 1.3}
    fo = rule_formalization(old_texts[int(0.7*len(old_texts)):], tc_model, **kwargs)
    old_rules = to_r(fo, fix=True)
    old_rules = transfer_new_rule_format_to_old(mydsl_to_rules(old_rules))
    old_relation = relation_mining(old_rules, old_testcases)
    json.dump(old_relation, open(f"no_scenario/{dataset}_rule_testcase_relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Constructed rule-testcase relation.")

    # 变更识别
    new_texts, new_mv, new_sco = get_rules(upd_rule_file, classification_knowledge_file, sc_model, skip_sc=True if any([item in upd_rule_file for item in ["dataset1", "dataset2", "dataset6"]]) else False)
    fo = rule_formalization(new_texts, tc_model)
    new_rules = to_r(fo, fix=True)
    new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules))
    to_delete_rules, to_add_rules = [], []
    old_map, new_map = {}, {}
    for old_text in old_texts:
        # 找到old_text对应的所有rule
        old_text_id = old_text['id']
        old_rules_i = []
        for rule_id in old_rules:
            ids = old_rules[rule_id]["rule_class"]
            if old_text_id in ids:
                old_rules_i.append(rule_id)
        old_map[old_text_id] = old_rules_i
    for new_text in new_texts:
        # 找到new_text对应的所有rule
        new_text_id = new_text['id']
        new_rules_i = []
        for rule_id in new_rules:
            ids = new_rules[rule_id]["rule_class"]
            if new_text_id in ids:
                new_rules_i.append(rule_id)
        new_map[new_text_id] = new_rules_i

    for old_text_id in old_map:
        find_old = False
        for new_text_id in new_map:
            if len(old_map[old_text_id]) != len(new_map[new_text_id]):
                continue
            find = [False for _ in range(len(old_map[old_text_id]))]
            for i, old_rule_id in enumerate(old_map[old_text_id]):
                for new_rule_id in new_map[new_text_id]:
                    if old_rules[old_rule_id]["constraints"] == new_rules[new_rule_id]["constraints"] and old_rules[old_rule_id]["results"] == new_rules[new_rule_id]["results"]:
                        find[i] = True
                        break
            if all(find):
                find_old = True
                break
        if not find_old:
            for old_text in old_texts:
                if old_text['id'] == old_text_id:
                    to_delete_rules.append(old_text)
    

    for new_text_id in new_map:
        find_new = False
        for old_text_id in old_map:
            if len(old_map[old_text_id]) != len(new_map[new_text_id]):
                continue
            find = [False for _ in range(len(new_map[new_text_id]))]
            for i, new_rule_id in enumerate(new_map[new_text_id]):
                for old_rule_id in old_map[old_text_id]:
                    if old_rules[old_rule_id]["constraints"] == new_rules[new_rule_id]["constraints"] and old_rules[old_rule_id]["results"] == new_rules[new_rule_id]["results"]:
                        find[i] = True
                        break
            if all(find):
                find_new = True
                break
        if not find_new:
            for new_text in new_texts:
                if new_text['id'] == new_text_id:
                    to_add_rules.append(new_text)
    
    change_rules = []
    for to_delete_rule in to_delete_rules:
        if to_delete_rule['id'] not in change_rules:
            change_rules.append(to_delete_rule['id'])
    for to_add_rule in to_add_rules:
        if to_add_rule['id'] not in change_rules:
            change_rules.append(to_add_rule['id'])
    new_change_rules = []
    for rule_id in change_rules:
        if not rule_id.startswith("72."):
            new_change_rules.append(rule_id)
    new_change_rules.append("72")
    change_rules = new_change_rules
    
    json.dump(change_rules, open(f"no_scenario/{dataset}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Identified changed rules.")

    # 测试用例更新/重用
    # 删掉已经被修改/删除的规则对应的测试用例
    for to_delete_rule in to_delete_rules:
        # assert to_delete_rule['id'] in old_relation
        if to_delete_rule['id'] not in old_relation:
            continue
        for testid in old_relation[to_delete_rule['id']]:
            for old_testcase in old_testcases:
                for old_testcase1 in old_testcase:
                    if old_testcase1['testid'] == testid:
                        old_testcase.remove(old_testcase1)
                        break
                if len(old_testcase) == 0:
                    old_testcases.remove(old_testcase)
    
    # 更新剩余测试用例的testid和rule
    rule_used = copy.deepcopy(new_map)
    for new_text_id in new_map:
        rule_used[new_text_id] = [False for _ in range(len(new_map[new_text_id]))]

    for old_testcase in old_testcases:
        for new_text_id in new_map:
            for i, new_rule_id in enumerate(new_map[new_text_id]):
                if rule_used[new_text_id][i]:
                    continue
                new_rule = new_rules[new_rule_id]
                find = [False for _ in range(len(old_testcase))]
                # 观察old_testcase中的每个测试用例是否属于new_map[new_text_id][i]，如果是，则匹配成功
                for j, old_testcase1 in enumerate(old_testcase):
                    is_related = judge_conflict(new_rule, old_testcase1)
                    if is_related:
                        find[j] = True
                if all(find):
                    for old_testcase1 in old_testcase:
                        old_ruleid_len = len(old_testcase1['rule'])
                        old_testcase1['rule'] = new_map[new_text_id][i]
                        old_testcase1['testid'] = new_map[new_text_id][i] + old_testcase1['testid'][old_ruleid_len:]
                    rule_used[new_text_id][i] = True

    # 新增测试用例
    fo = rule_formalization(new_texts, tc_model)
    r = to_r(fo, fix=True)
    new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(r))
    to_add_r = {}
    for to_add_rule in to_add_rules:
        to_add_rule_id = to_add_rule['id']
        for rule_id in new_rules:
            if rule_id.startswith(to_add_rule_id) and (rule_id == to_add_rule_id or rule_id[len(to_add_rule_id)] == '.'):
                to_add_r[rule_id] = new_rules[rule_id]

    new_testcases = process_r3_to_testcase(rules_to_mydsl(transfer_old_rule_format_to_new(to_add_r)))
    old_testcases.extend(new_testcases)
    print("Updated testcases.")
    json.dump(old_testcases, open(f"no_scenario/{dataset}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)






if __name__ == "__main__":
    for i in range(1, 7):
        ini_file = f"dataset{i}_ini_rule.txt" if f"dataset{i}_ini_rule.txt" in os.listdir("data") else f"dataset{i}_ini_rule.pdf"
        upd_file = f"dataset{i}_upd_rule.txt" if f"dataset{i}_upd_rule.txt" in os.listdir("data") else f"dataset{i}_upd_rule.pdf"
        print(f"Processing {upd_file}...")
        generate_testcase(f"data/{ini_file}", f"data/{ini_file.split('.')[0][:-5]}_testcase.json", f"data/{upd_file}")
        print(f"{upd_file} finished.")