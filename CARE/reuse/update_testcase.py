import copy
import json
import os
import argparse
from reuse.rule_testcase_relation_mining import relation_mining, get_rules, get_scenario, judge_conflict
from reuse.process_r3_to_testcase import process_r3_to_testcase
from transfer.mydsl_to_rules import mydsl_to_rules, transfer_new_rule_format_to_old, transfer_old_rule_format_to_new
from transfer.rules_to_mydsl import rules_to_mydsl
from reuse.generate_linked_scenario import generate_linked_scenario

api_key = json.load(open("../api_key.json", "r", encoding="utf-8"))


def update_testcase(old_file, old_testcases, new_file, sc_model_path, tc_model_path, classification_knowledge_file, other_knowledge_file, skip_sc = True):
    """
    给定旧文件，新文件，以及旧文件生成的测试用例（测试用例集）
    1、首先，寻找文件中的可测试的规则，发现新旧文件的不同
    2、然后，使用新文件生成测试用例
    3、最后，在测试用例集中删掉已经被修改/删除的规则对应的测试用例，添加新的测试用例进来
    """
    os.makedirs("cache", exist_ok=True)
    old_testcases = json.load(open(old_testcases, "r", encoding="utf-8"))

    # 获得新旧文件的规则和场景
    old_texts, old_mv, old_sco = get_rules(old_file, classification_knowledge_file, sc_model_path, skip_sc)
    old_rules = get_scenario(old_texts, old_mv, tc_model_path, classification_knowledge_file, other_knowledge_file, old_sco, api_key=api_key)
    old_rules = transfer_new_rule_format_to_old(mydsl_to_rules(old_rules))
    json.dump(old_rules, open("cache/old_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    new_texts, new_mv, new_sco = get_rules(new_file, classification_knowledge_file, sc_model_path, skip_sc)
    new_rules = get_scenario(new_texts, new_mv, tc_model_path, classification_knowledge_file, other_knowledge_file, new_sco, api_key=api_key)
    new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules))
    json.dump(new_rules, open("cache/new_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    old_rules = json.load(open("cache/old_scenario.json", "r", encoding="utf-8"))
    old_rules_str = rules_to_mydsl(transfer_old_rule_format_to_new(old_rules))
    new_rules = json.load(open("cache/new_scenario.json", "r", encoding="utf-8"))
    """
    "texts":
    [
        {"id": "rule_id", "text": "****", "label": ""}
    ]

    defines:
    {'交易市场': ['深圳证券交易所'], '交易品种': ['融资融券交易']}

    vars:
    {
        "rule_id": {'交易方式': [], '操作': [], '交易品种': [], '申报数量': [], '交易市场': [], '交易方向': []}
    }

    rules:
    {
        "rule_id": {'rule_class': ['3.3.8'], 'focus': ['订单连续性操作'], 'constraints': [{'key': '交易方式', 'value': '竞价交易', 'operation': 'is'}, {'key': '操作', 'value': '买入', 'operation': 'is'}, {'key': '交易品种', 'value': '股票', 'operation': 'is'}, {'key': '申报数量', 'value': ['%', '100', '==', '0'], 'operation': 'compute'}, {'key': '交易市场', 'operation': 'is', 'value': '深圳证券交易所'}, {'key': '交易方向', 'operation': 'is', 'value': '买入'}], 'results': [{'key': '结果', 'value': '成功', 'operation': 'is', 'else': '不成功'}], 'before': [], 'after': []}
    }
    """

    old_relation = relation_mining(old_rules, old_testcases)
    json.dump(old_relation, open("cache/old_rule_testcase_relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    # print(sorted(old_relation.keys(), key=lambda x: int(x)))


    # 寻找新旧文件的不同
    # to_delete_rules, to_add_rules = [], []
    # for old_text in old_texts:
    #     find = False
    #     for new_text in new_texts:
    #         if old_text['text'] == new_text['text']:
    #             find = True
    #             break
    #     if not find:
    #         to_delete_rules.append(old_text)
    # for new_text in new_texts:
    #     find = False
    #     for old_text in old_texts:
    #         if old_text['text'] == new_text['text']:
    #             find = True
    #             break
    #     if not find:
    #         to_add_rules.append(new_text)
    
    # 寻找新旧文件的不同
    to_delete_rules, to_add_rules = [], []
    old_map, new_map = {}, {}
    # old_map: {'4.5.7': ['4.5.7.1.1', '4.5.7.1.2'], '5.2.3': ['5.2.3.1.1', '5.2.3.1.2']}，即原文规则对应的所有R规则
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
    print(f"更改的规则数：{len(to_delete_rules)}")

    all_to_delete_linked_scenario = []
    linked_scenario = generate_linked_scenario(old_rules_str)
    for to_delete_rule in to_delete_rules:
        for linked_scenario1 in linked_scenario:
            for rule in linked_scenario1:
                if linked_scenario1 not in all_to_delete_linked_scenario and any([tc.startswith(to_delete_rule['id']) and (tc == to_delete_rule['id'] or tc[len(to_delete_rule['id'])] == ".") for tc in rule['rule'].split(",")]):
                    all_to_delete_linked_scenario.append(linked_scenario1)
                    break
    print(f"受影响的需求场景数：{len(all_to_delete_linked_scenario)}")

    to_del_index = []
    for to_delete_rule in to_delete_rules:
        id = to_delete_rule['id']
        if id not in old_relation:
            to_del_index.append(to_delete_rule)
    for to_delete_rule in to_del_index:
        to_delete_rules.remove(to_delete_rule)

    all_to_delete_testcases = []
    for to_delete_rule in to_delete_rules:
        for tcs in old_relation[to_delete_rule['id']]:
            if tcs not in all_to_delete_testcases and any([tc.startswith(to_delete_rule['id']) and (tc == to_delete_rule['id'] or tc[len(to_delete_rule['id'])] == ".") for tc in tcs.split(",")]):
                all_to_delete_testcases.append(tcs)
    print(f"受影响的测试用例数：{len(all_to_delete_testcases)}")

    
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


    # 如果只有删除没有新增，就不需要重新生成全部的测试场景
    # 只需要找到与被删除规则关联的所有规则，对它们重新生成测试场景和用例即可
    if len(to_delete_rules) > 0 and len(to_add_rules) == 0:
        related_testcase_idss = []
        for to_delete_rule in to_delete_rules:
            related_testcase_idss.extend(old_relation[to_delete_rule['id']])
        related_testcase_idss = list(set(related_testcase_idss))
        # 找到包含这些测试用例的所有规则
        related_rule_ids = []
        for rule_id in old_relation:
            if rule_id in [r['id'] for r in to_delete_rules]:
                continue
            for testid in old_relation[rule_id]:
                if testid in related_testcase_idss:
                    related_rule_ids.append(rule_id)
                    break
        related_rule_ids = list(set(related_rule_ids))
        # 重新生成测试用例
        related_rules = []
        for rule_id in related_rule_ids:
            for old_text in old_texts:
                if rule_id == old_text['id']:
                    related_rules.append(old_text)
                    break
        new_rules = get_scenario(related_rules, old_mv, tc_model_path, classification_knowledge_file, other_knowledge_file, old_sco)
        new_testcases = process_r3_to_testcase(new_rules)
        old_testcases.extend(new_testcases)

        # 生成需求场景
        for scenario in all_to_delete_linked_scenario:
            if scenario in linked_scenario:
                linked_scenario.remove(scenario)
        new_linked_scenario = generate_linked_scenario(new_rules)
        for scenario in new_linked_scenario:
            if scenario not in linked_scenario:
                linked_scenario.append(scenario)

    # 否则，需要重新生成全部的测试场景，然后从中选出新增的规则对应的场景生成测试用例
    elif len(to_add_rules) > 0:
        new_rules = get_scenario(new_texts, new_mv, tc_model_path, classification_knowledge_file, other_knowledge_file, new_sco)
        new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules))
        new_scenarios = {}
        for to_add_rule in to_add_rules:
            to_add_rule_id = to_add_rule['id']
            for new_rule_id in new_rules:
                new_rule_id_parts = new_rule_id.split(",")
                for id in new_rule_id_parts:
                    if id.startswith(to_add_rule_id) and (id == to_add_rule_id or id[len(to_add_rule_id)] == "."):
                        new_scenarios[new_rule_id] = new_rules[new_rule_id]
                        break
        
        new_testcases = process_r3_to_testcase(rules_to_mydsl(transfer_old_rule_format_to_new(new_scenarios)))
        old_testcases.extend(new_testcases)
        
        # for scenario in all_to_delete_linked_scenario:
        #     if scenario in linked_scenario:
        #         linked_scenario.remove(scenario)
        # new_linked_scenario = generate_linked_scenario(rules_to_mydsl(transfer_old_rule_format_to_new(new_scenarios)))
        # for scenario in new_linked_scenario:
        #     if scenario not in linked_scenario:
        #         linked_scenario.append(scenario)
        linked_scenario = generate_linked_scenario(rules_to_mydsl(transfer_old_rule_format_to_new(new_rules)))

    return old_testcases, change_rules, linked_scenario, old_relation





if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old_file", type=str, default="./demo/深圳证券交易所交易规则（2021年3月修订）.pdf")
    parser.add_argument("--old_testcases", type=str, default="./demo/testcase.json")
    parser.add_argument("--new_file", type=str, default="./demo/深圳证券交易所交易规则（2023年修订）.pdf")
    parser.add_argument("--new_testcases", type=str, default="./outputs/new_testcase.json")
    parser.add_argument("--change", type=str, default="./outputs/change.json")
    parser.add_argument("--new_scenario", type=str, default="./outputs/new_scenario.json")
    parser.add_argument("--sc_model_path", type=str, default="../model/trained/mengzi_rule_filtering")
    parser.add_argument("--tc_model_path", type=str, default="../model/trained/glm4_lora")
    parser.add_argument("--classification_knowledge_file", type=str, default="../reuse/domain_knowledge/classification_knowledge.json")
    parser.add_argument("--other_knowledge_file", type=str, default="../reuse/domain_knowledge/knowledge.json")
    parser.add_argument("--skip_sc", type=bool, default=True)
    args = parser.parse_args()

    if not os.path.exists(args.old_file):
        raise FileNotFoundError(f"文件 {args.old_file} 不存在")
    if not os.path.exists(args.old_testcases):
        raise FileNotFoundError(f"文件 {args.old_testcases} 不存在")
    if not os.path.exists(args.new_file):
        raise FileNotFoundError(f"文件 {args.new_file} 不存在")
    for output_path in [args.new_testcases, args.change, args.new_scenario]:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    new_testcases, change, linked_scenario, old_relation = update_testcase(args.old_file, args.old_testcases, args.new_file, args.sc_model_path, args.tc_model_path, args.classification_knowledge_file, args.other_knowledge_file, args.skip_sc)
    json.dump(new_testcases, open(args.new_testcases, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(change, open(args.change, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(linked_scenario, open(args.new_scenario, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
