import copy
import pprint
import json
from transfer.knowledge_tree import get_constrainted_values, get_constrainted_all_subvalues, get_constraint_to_add, encode_tree
from transfer.mydsl_to_rules import mydsl_to_rules
from transfer.rules_to_mydsl import rules_to_mydsl
import cn2an

def judge_two_rules_conflict(rule1, rule2):
    """
    判断两条规则是否冲突. 冲突条件为条件结果冲突, 即两条规则的条件结果中有相同的属性，但对应的值不相同
    """
    rule1_cons, rule2_cons = {}, {}
    # example:
    # rule1_cons['操作'] = ['申报', '买入']
    # ...
    for condition in rule1['conditions']:
        if condition[0] not in rule1_cons:
            rule1_cons[condition[0]] = [condition[2]]
        elif condition[2] not in rule1_cons[condition[0]]:
            rule1_cons[condition[0]].append(condition[2])
    for consequence in rule1['consequences']:
        if consequence[0] not in rule1_cons:
            rule1_cons[consequence[0]] = [consequence[2]]
        elif consequence[2] not in rule1_cons[consequence[0]]:
            rule1_cons[consequence[0]].append(consequence[2])
    for condition in rule2['conditions']:
        if condition[0] not in rule2_cons:
            rule2_cons[condition[0]] = [condition[2]]
        elif condition[2] not in rule2_cons[condition[0]]:
            rule2_cons[condition[0]].append(condition[2])
    for consequence in rule2['consequences']:
        if consequence[0] not in rule2_cons:
            rule2_cons[consequence[0]] = [consequence[2]]
        elif consequence[2] not in rule2_cons[consequence[0]]:
            rule2_cons[consequence[0]].append(consequence[2])
    
    for key in rule1_cons:
        if key in rule2_cons:
            if set(rule1_cons[key]) != set(rule2_cons[key]):  # 如果两条规则的条件结果中有相同的属性，但对应的值不相同，则为冲突
                return True
    return False



def compose_two_rules(rule1, rule2, reverse=False):
    """
    将rule2合并到rule1中, 依次合并并去重条件、结果、sourceId, 并将id按字典序连接
    """
    rule1['conditions'] += copy.deepcopy(rule2['conditions'])
    rule1['consequences'] += copy.deepcopy(rule2['consequences'])
    rule1['conditions'] = list(list(ti) for ti in set([tuple(condition) for condition in rule1['conditions']]))
    rule1['consequences'] = list(list(ti) for ti in set([tuple(consequence) for consequence in rule1['consequences']]))
    if reverse:
        rule1['rule'] = rule2['rule'] + "," + rule1['rule']
    else:
        rule1['rule'] = rule1['rule'] + "," + rule2['rule']
    rule1['sourceId'] += copy.deepcopy(rule2['sourceId'])
    rule1['sourceId'] = list(set(rule1['sourceId']))
    return rule1


def compose_nested_rules(rules, sco, setting, knowledge):
    """
    组合嵌套规则. 嵌套规则对应的标签为"引用"
    例如, 若rules[i].conditions中包含['引用', 'is', '第j条'], 则将第j条规则的conditions和consequences添加到rules[i]中, 并删除第j条规则
    注意: 只能处理单层嵌套
    """
    to_delete_idx = []  # 待删除的规则在rules中的索引
    to_add_rules = []  # 待添加的规则
    for i, rule in enumerate(rules):
        if i in to_delete_idx:  # 规则rules[i]已经和其他规则合并
            continue

        new_rules = [copy.deepcopy(rule)]
        for k, condition in enumerate(rule['conditions']+rule['consequences']):
            if condition[0] == "引用":
                if "《" in condition[2] and "》" in condition[2]:  # 引用其他文档的规则，如《上市公司收购管理办法》第十六条规定、《上市公司收购管理办法》以及其他有关上市公司收购及股份权益变动的有关规定、《上市公司收购管理办法》第六十三条列举情形之一
                    ...  # 暂不处理

                elif ("第" in condition[2] or "前" in condition[2]) and ("款" in condition[2] or "项" in condition[2]):  # 引用本文档一条规则的部分规定，如除符合本条第一款规定的条件外、不受本条前两款规定的限制、不适用前两款规定、不受本条第二款、第三款规定的限制、但第3.3.4条第三项至第五项市价申报类型除外（全部都是除外的情况）
                    ...  # 由模型进行处理，最后生成的规则不会出现这种情况

                elif "第" in condition[2] and "条" in condition[2]:  # 引用本文档一条规则的完整规定
                    # 在rules中寻找引用的规则进行合并. 分成3种情况考虑: 1. 引用1条规则; 2. 引用2条以上规则, 且规则间不共存; 3. 引用2条以上规则, 且规则间共存
                    if condition[2].count("第") == 1:  # 情况1. 引用1条规则
                        if "第" in rule['rule'] and "条" in rule['rule']:  # rule: '第一条'
                            ref_rule_idx = "第" + condition[2].split("第")[1].split("条")[0] + "条"
                        else:  # rule: '3.1.5'
                            ref_rule_idx = condition[2].split("第")[1].split("条")[0]
                        find = False
                        for j, ref_rule in enumerate(rules):
                            if ref_rule_idx in ref_rule['rule'] and ref_rule['rule'].startswith(ref_rule_idx):
                                find = True
                                # 合并规则，
                                for new_rule in new_rules:
                                    compose_two_rules(new_rule, ref_rule, reverse=i>j)
                                # 添加到待删除列表
                                to_delete_idx.append(j)
                                break
                        if not find:
                            # 从领域知识中寻找
                            # 加载原文，然后看领域知识的关键字是否在原文中出现，对领域知识层层查找，一直找到叶子节点
                            text = ""
                            for scoi in sco:
                                if scoi['id'] == ref_rule_idx:
                                    text = scoi['text']
                                    break
                            c = get_constraint_to_add(text, setting, knowledge)
                            if len(c) > 0:
                                c_key, c_value = list(c.keys())[0], c[list(c.keys())[0]]
                                c = [c_key, "is", ",".join(c_value)]
                                if k >= len(rule['conditions']):
                                    for new_rule in new_rules:
                                        new_rule['consequences'].append(c)
                                else:
                                    for new_rule in new_rules:
                                        new_rule['conditions'].append(c)
                            # 领域知识中也找不到，不处理
                    else:  # condition[2].count("第") >= 2, 情况2、3. 引用2条以上规则
                        ref_rule_idxs = []
                        s = condition[2]
                        s_index = 0
                        while "第" in s[s_index:]:
                            if "第" in rule['rule'] and "条" in rule['rule']:  # rule: '第一条'
                                ref_rule_idx = "第" + condition[2].split("第")[1].split("条")[0] + "条"
                            else:  # rule: '3.1.5'
                                ref_rule_idx = condition[2].split("第")[1].split("条")[0]
                            ref_rule_idxs.append(ref_rule_idx)
                            s_index = s.index("第", s_index) + 1

                        # 判断规则间是否共存
                        conflict = False
                        for rule1_idx in ref_rule_idxs:
                            for rule2_idx in ref_rule_idxs:
                                if rule1_idx == rule2_idx:
                                    continue
                                if judge_two_rules_conflict(rule1_idx, rule2_idx):
                                    conflict = True
                                    break
                            if conflict:
                                break
                        if conflict:  # 情况2. 引用2条以上规则, 且规则间不共存
                            # 每个引用规则分别和new_rules的每个规则结合，生成新规则
                            new_rules_2 = []
                            for ref_rule_idx in ref_rule_idxs:
                                find = False
                                for j, ref_rule in enumerate(rules):
                                    if ref_rule_idx in ref_rule['rule'] and ref_rule['rule'].startswith(ref_rule_idx):  # 找到ref_rule
                                        find = True
                                        for new_rule in new_rules:  # 与new_rules中的每个规则结合
                                            new_rule_2 = copy.deepcopy(new_rule)
                                            compose_two_rules(new_rule_2, ref_rule, reverse=i>j)
                                            new_rules_2.append(new_rule_2)
                                        break
                                if not find:
                                    # 从领域知识中寻找
                                    text = ""
                                    for scoi in sco:
                                        if scoi['id'] == ref_rule_idx:
                                            text = scoi['text']
                                            break
                                    c = get_constraint_to_add(text, setting, knowledge)
                                    if len(c) > 0:
                                        c_key, c_value = list(c.keys())[0], c[list(c.keys())[0]]
                                        c = [c_key, "is", ",".join(c_value)]
                                        if k >= len(rule['conditions']):
                                            for new_rule in new_rules:
                                                new_rule_2 = copy.deepcopy(new_rule)
                                                new_rule_2['consequences'].append(c)
                                                new_rules_2.append(new_rule_2)
                                        else:
                                            for new_rule in new_rules:
                                                new_rule_2 = copy.deepcopy(new_rule)
                                                new_rule_2['conditions'].append(c)
                                                new_rules_2.append(new_rule_2)
                            new_rules = new_rules_2
                        else:  # 情况3. 引用2条以上规则, 且规则间共存
                            # 每个引用规则添加到new_rules的每个规则上，总规则数不变
                            for new_rule in new_rules:
                                for ref_rule_idx in ref_rule_idxs:
                                    find = False
                                    for j, ref_rule in enumerate(rules):
                                        if ref_rule_idx in ref_rule['rule'] and ref_rule['rule'].startswith(ref_rule_idx):
                                            find = True
                                            compose_two_rules(new_rule, ref_rule, reverse=i>j)
                                            break
                                    if not find:
                                        # 从领域知识中寻找
                                        text = ""
                                        for scoi in sco:
                                            if scoi['id'] == ref_rule_idx:
                                                text = scoi['text']
                                                break
                                        c = get_constraint_to_add(text, setting, knowledge)
                                        if len(c) > 0:
                                            c_key, c_value = list(c.keys())[0], c[list(c.keys())[0]]
                                            c = [c_key, "is", ",".join(c_value)]
                                            if k >= len(rule['conditions']):
                                                new_rule['consequences'].append(c)
                                            else:
                                                new_rule['conditions'].append(c)
        for new_rule in new_rules:
            for condi in range(len(new_rule['conditions']))[::-1]:
                if new_rule['conditions'][condi][0] == "引用":
                    new_rule['conditions'].pop(condi)
            for consi in range(len(new_rule['consequences']))[::-1]:
                if new_rule['consequences'][consi][0] == "引用":
                    new_rule['consequences'].pop(consi)
        to_add_rules += new_rules
        to_delete_idx.append(i)
    
    rules = to_add_rules
    return rules


def concretize_other(rules, setting, knowledge):
    """
    补全 “其他”...
    例如：采用交易方式1...交易方式2...其他交易方式...
    如果在领域知识中找不到，就不处理
    """
    market, variety = setting.get("market", ""), setting.get("variety", "")
    if f"交易市场:{market}" in knowledge:
        knowledge = knowledge[f"交易市场:{market}"]
    else:
        return rules
    if f"交易品种:{variety}" in knowledge:
        knowledge = knowledge[f"交易品种:{variety}"]
    elif f"业务:{variety}" in knowledge:
        knowledge = knowledge[f"业务:{variety}"]
    else:
        return rules
    
    new_rules = []
    for i, rule in enumerate(rules):
        new_rulesi = []
        for k, condition in enumerate(rule['conditions'] + rule['consequences']):
            # print(condition)
            if "其他" in condition[2]:
                base_key = condition[0]
                key = condition[2].split("其他")[-1]
                values = get_constrainted_values(knowledge, setting, key)
                if len(values) == 0:
                    continue

                # 寻找sourceId相同的之前的规则，去掉他们的取值
                for j in range(i)[::-1]:
                    if rule['sourceId'] == rules[j]['sourceId']:
                        for condition2 in rules[j]['conditions'] + rules[j]['consequences']:
                            if condition2[0] == base_key and condition2[2] in values:
                                values.remove(condition2[2])
                # 新增规则
                for value in values:
                    new_rule = copy.deepcopy(rule)
                    if k >= len(rule['conditions']):
                        new_rule['consequences'][k-len(rule['conditions'])][2] = value
                    else:
                        new_rule['conditions'][k][2] = value
                    new_rulesi.append(new_rule)
        if len(new_rulesi) == 0:
            new_rulesi.append(copy.deepcopy(rule))
        new_rules += new_rulesi
    rules = new_rules
    return rules




def concretize_time(rules, setting, knowledge):
    new_rules = []
    for i, rule1 in enumerate(rules):
        for condition in rule1['conditions'] + rule1['consequences']:
            if condition[0] == "时间":
                time_key = condition[2]
                if "阶段" in time_key:
                    time_key = time_key[:time_key.find("阶段")]
                elif "时间" in time_key:
                    time_key = time_key[:time_key.find("时间")]
                else:
                    continue
                
                for j, rule2 in enumerate(rules):
                    if i == j:
                        continue
                    solve = False
                    for condition2 in rule2['conditions'] + rule2['consequences']:
                        if time_key in condition2[0]:
                            condition[2] = condition2[2]
                            solve = True
                            break
                    if solve:
                        break
        new_rules.append(rule1)
    rules = new_rules
    return rules


def complete_rule_fields(rules, setting, knowledge, concretize):
    elements = get_constrainted_values(knowledge, {}, "单独可测试规则要素")
    for element in elements:
        new_rules = []
        if element == "交易方向":
            # 寻找交易操作
            for rule in rules:
                find_op = False
                for condition in rule['conditions'] + rule['consequences']:
                    if condition[0] in ["操作", "操作部分", "操作主体"]:  # 认购(买)、申购(买)、赎回(卖)、竞买(卖)、应价(买)
                        if "买入" in condition[2] or "认购" in condition[2] or "申购" in condition[2] or "应价" in condition[2]:
                            if condition in rule['conditions']:
                                find_op = True
                                rule['conditions'].append(["交易方向", "is", "买入"])
                            else:
                                find_op = True
                                rule['consequences'].append(["交易方向", "is", "买入"])
                        if "卖出" in condition[2] or "赎回" in condition[2] or "竞买" in condition[2]:
                            if condition in rule['conditions']:
                                find_op = True
                                rule['conditions'].append(["交易方向", "is", "卖出"])
                            else:
                                find_op = True
                                rule['consequences'].append(["交易方向", "is", "卖出"])
                            break
                if not find_op:  # 没有操作，将买入、卖出都加上
                    new_rule = copy.deepcopy(rule)
                    new_rule['conditions'].append(["交易方向", "is", "买入"])
                    new_rule['rule'] = new_rule['rule'] + ".1"
                    new_rules.append(new_rule)
                    new_rule = copy.deepcopy(rule)
                    new_rule['conditions'].append(["交易方向", "is", "卖出"])
                    new_rule['rule'] = new_rule['rule'] + ".2"
                    new_rules.append(new_rule)
                else:
                    new_rules.append(rule)
            rules = new_rules
        
        
        elif element == "交易市场":
            if "market" in setting:
                market = setting['market']
            else:
                break
            for rule in rules:
                find_market = False
                for condition in rule['conditions'] + rule['consequences']:
                    if condition[0] == "交易市场":
                        find_market = True
                        break
                if not find_market:
                    rule['conditions'].append(["交易市场", "is", market])
                new_rules.append(rule)
            rules = new_rules
        
        
        elif element == "交易品种":
            # 如果没有交易品种（业务），则增加 交易品种 is variety
            # 如果有交易品种（业务）且为variety，则不变
            # 如果有交易品种（业务）但不为variety，或有**品种且为variety，则根据是不是子品种进行处理
            if "variety" in setting:
                variety = setting['variety']
            else:
                break
            sub_varieties = get_constrainted_values(knowledge, setting, f"{variety}品种")  # 子品种
            
            for rule in rules:
                find_variety = False
                key_correct, value_correct = False, False
                for condition in rule['conditions'] + rule['consequences']:
                    if "品种" in condition[0] or "业务" == condition[0]:
                        find_variety = True
                        if condition[0] in ["交易品种", "业务"]:
                            key_correct = True
                        if condition[2] == variety:
                            value_correct = True
                        break
                # 什么品种/业务都没发现
                if not find_variety:
                    if concretize:
                        idx = 1
                        for sub_variety in sub_varieties:
                            new_rule = copy.deepcopy(rule)
                            new_rule['conditions'].append(["交易品种", "is", variety])
                            new_rule['conditions'].append([f"{variety}品种", "is", sub_variety])
                            new_rule['rule'] = f"{new_rule['rule']}.{idx}"
                            new_rules.append(new_rule)
                            idx += 1
                    else:
                        rule['conditions'].append(["交易品种", "is", variety])
                        new_rules.append(rule)
                # 有品种/业务
                else:
                    if key_correct and value_correct:
                        new_rules.append(rule)
                    else:
                        find_subvariety = False
                        
                        for sub_variety in sub_varieties:
                            if condition[2] == sub_variety:
                                find_subvariety = True
                                rule['conditions'].append(["交易品种", "is", variety])
                                new_rules.append(rule)
                                break
                        if not find_subvariety:
                            new_rules.append(rule)
            rules = new_rules
        
        
        elif element == "交易方式":
            sub_vals = get_constrainted_all_subvalues(knowledge, setting)
            if len(sub_vals) == 0:
                continue
            sub_vals_simple = get_constrainted_values(knowledge, setting, "交易方式")
            for rule in rules:
                count = [0 for _ in range(len(sub_vals))]
                for condition in rule['conditions'] + rule['consequences']:
                    for i, vals in enumerate(sub_vals):
                        for vi in vals:
                            k, v = vi.split(":")
                            if v == condition[2]:
                                count[i] += 1
                                break
                # 选出出现次数最多的交易方式
                max_count = max(count)
                max_idx = [i for i, c in enumerate(count) if c == max_count]
                if concretize:
                    max_vals = [sub_vals[i] for i in max_idx] if max_count > 0 else [[f'交易方式:{c}'] for c in sub_vals_simple]
                else:
                    max_vals = [[f'交易方式:{c}'] for c in sub_vals_simple]
                idx = 1
                for vals in max_vals:
                    new_rule = copy.deepcopy(rule)
                    for vi in vals:
                        k, v = vi.split(":")
                        if v in [c[2] for c in rule['conditions'] + rule['consequences']]:
                            continue
                        new_rule['conditions'].append([k, "is", v])
                    new_rule['rule'] = f"{new_rule['rule']}.{idx}"
                    new_rules.append(new_rule)
                    idx += 1
                if idx == 1:
                    new_rules.append(rule)

            rules = new_rules

    return rules


def process_r1_to_r2(r1, sco, setting, knowledge, concretize=False, return_rules=False):
    """主要任务包括：
    1、嵌套规则处理
    2、“其他”抽象具体化
    3、“时间”抽象具体化
    4、补全单规则相关字段

    r1是字符串规则
    sco需要用到规则的text以及id，用以进行嵌套规则处理
    setting是交易所和品种的设置
    knowledge是领域知识
    concretize控制补全是只补全单规则相关字段还是所有对应的子字段,一般默认False
    return_rules控制返回的是字符串规则还是规则列表,在生成模型训练数据的时候使用,其他情况默认False
    """
    if return_rules:
        rules = r1
    else:
        rules = mydsl_to_rules(r1)
    # rules[i] = {
    #     'conditions': [['债券品种', 'is', '债券现券']],
    #     'consequences': [['约束', 'is', '当日回转交易']],
    #     'rule': '3.1.8.1',
    #     'sourceId': ['3.1.8']
    # }

    # 1、嵌套规则处理
    rules = compose_nested_rules(rules, sco, setting, knowledge)

    # 2、“其他”抽象具体化
    rules = concretize_other(rules, setting, knowledge)

    # 3、“时间”抽象具体化
    rules = concretize_time(rules, setting, knowledge)

    # 4、补全单规则相关字段
    rules = complete_rule_fields(rules, setting, knowledge, concretize)
    if return_rules:
        return rules
    else:
        r2 = rules_to_mydsl(rules)
        return r2


if __name__ == "__main__":
    r1 = open("cache/r1.mydsl", "r", encoding="utf-8").read()
    sco = json.load(open("cache/sco.json", "r", encoding="utf-8"))
    setting = json.load(open("cache/setting.json", "r", encoding="utf-8"))
    knowledge = json.load(open("../reuse/domain_knowledge/classification_knowledge.json", "r", encoding="utf-8"))
    r2 = process_r1_to_r2(r1, sco, setting, knowledge)
    with open("cache/r2.mydsl", "w", encoding="utf-8") as f:
        f.write(r2)