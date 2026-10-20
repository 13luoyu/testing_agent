from reuse.process_r3_to_testcase import process_r3_to_testcase
from transfer.mydsl_to_rules import transfer_old_rule_format_to_new
from transfer.rules_to_mydsl import rules_to_mydsl
from reuse.generate_linked_scenario import generate_linked_scenario
from reuse.rule_testcase_relation_mining import *





def update_testcase(old_file, old_testcases, new_file, sc_model_path, tc_model_path, classification_knowledge_file, other_knowledge_file, skip_sc = False):
    """
    给定旧文件，新文件，以及旧文件生成的测试用例（测试用例集）
    1、首先，寻找文件中的可测试的规则，发现新旧文件的不同
    2、然后，使用新文件生成测试用例
    3、最后，在测试用例集中删掉已经被修改/删除的规则对应的测试用例，添加新的测试用例进来
    """
    classification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    other_knowledge = json.load(open(other_knowledge_file, "r", encoding="utf-8"))
    old_testcases = json.load(open(old_testcases, "r", encoding="utf-8"))

    # 获得新旧文件的规则和场景
    old_texts, old_mv, old_sco = get_rules(old_file, classification_knowledge_file, sc_model_path, skip_sc)
    kwargs = {"temperature": 0.7, "do_sample": True, "top_p": 0.9, "repetition_penalty": 1.3}
    r = 0.5
    fo = rule_formalization(old_texts[:int(r*len(old_texts))], tc_model_path, **kwargs) + rule_formalization(old_texts[int(r*len(old_texts)):], tc_model_path)
    r1 = to_r(fo, fix=True)
    r2 = process_r1_to_r2(r1, old_sco, old_mv, classification_knowledge)
    old_rules, _, _ = process_r2_to_r3(r2, other_knowledge)
    old_rules = transfer_new_rule_format_to_old(mydsl_to_rules(old_rules))
    json.dump(old_rules, open("cache/old_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    new_texts, new_mv, new_sco = get_rules(new_file, classification_knowledge_file, sc_model_path, skip_sc)
    fo = rule_formalization(new_texts[:int(r*len(new_texts))], tc_model_path, **kwargs) + rule_formalization(new_texts[int(r*len(new_texts)):], tc_model_path)
    r1 = to_r(fo, fix=True)
    r2 = process_r1_to_r2(r1, new_sco, new_mv, classification_knowledge)
    new_rules, _, _ = process_r2_to_r3(r2, other_knowledge)
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
            find = False
            for old_testcase in old_testcases:
                for old_testcase1 in old_testcase:
                    if old_testcase1['testid'] == testid:
                        old_testcase.remove(old_testcase1)
                        find = True
                        break
                if len(old_testcase) == 0:
                    old_testcases.remove(old_testcase)
                if find:
                    break

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


    # 添加新的测试用例进来
    classification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    other_knowledge = json.load(open(other_knowledge_file, "r", encoding="utf-8"))
    fo = rule_formalization(new_texts[:int(r*len(new_texts))], tc_model_path, **kwargs) + rule_formalization(new_texts[int(r*len(new_texts)):], tc_model_path)
    r1 = to_r(fo, fix=True)
    r2 = process_r1_to_r2(r1, new_sco, new_mv, classification_knowledge)
    new_rules, _, _ = process_r2_to_r3(r2, other_knowledge)
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
    linked_scenario = generate_linked_scenario(rules_to_mydsl(transfer_old_rule_format_to_new(new_rules)))

    return old_testcases, change_rules, linked_scenario








def generate_testcase_no_change_impact_analysis():
    for i in range(1, 7):
        ini_file = f"dataset{i}_ini_rule.txt" if f"dataset{i}_ini_rule.txt" in os.listdir("data") else f"dataset{i}_ini_rule.pdf"
        upd_file = f"dataset{i}_upd_rule.txt" if f"dataset{i}_upd_rule.txt" in os.listdir("data") else f"dataset{i}_upd_rule.pdf"
        print(f"Processing {upd_file}...")

        new_testcases, change, new_scenario = update_testcase(f"data/{ini_file}", f"data/{ini_file.split('.')[0][:-5]}_testcase.json", f"data/{upd_file}", "../../model/trained/mengzi_rule_filtering", "../../model/trained/glm4_lora_exp", "../../reuse/domain_knowledge/classification_knowledge.json", "../../reuse/domain_knowledge/knowledge.json", skip_sc = True if any(item in ini_file for item in ["dataset1", "dataset2", "dataset6"]) else False)

        json.dump(new_testcases, open(f"no_change_impact_analysis/{ini_file.split('.')[0][:-9]}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(change, open(f"no_change_impact_analysis/{ini_file.split('_')[0]}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(new_scenario, open(f"no_change_impact_analysis/{ini_file.split('_')[0]}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)












if __name__ == "__main__":
    generate_testcase_no_change_impact_analysis()