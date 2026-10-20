import copy
import json
from transfer.mydsl_to_rules import mydsl_to_rules
from transfer.rules_to_mydsl import rules_to_mydsl
from reuse.process_r1_to_r2 import judge_two_rules_conflict, compose_two_rules
import re

def get_rule_constraint_type(rule):
    """
    获取规则的约束类型
    example:
    时间: 时间 is 每个交易日的9:00-15:00,
    数量: 数量 is 10万元或者其整数倍, 数量 不超过 100万元
    价格: 0.001元
    """
    for condition in rule['conditions'] + rule['consequences']:
        if "时间" in condition[0]:
            if re.search(r"\d{1,2}:\d{1,2}-\d{1,2}:\d{1,2}", condition[2]):
                return "时间"
        if "数量" in condition[0]:
            if ("整数倍" in condition[2] or any([key_word == condition[1] for key_word in ["不低于", "达到", "以上", "不高于", "以下", "不超过", "以内", "低于", "未达到", "不足", "小于", "高于", "超过", "优于", "大于"]])) and re.search(r"\d+", condition[2]):
                return "数量"
        if "价格" in condition[0]:
            if re.search(r"\d+", condition[2]):
                return "价格"
    return ""

def compose_rules(rules):
    """
    时间、数量、价格，如果不冲突则组合
    要求被组合的键必须是数值型约束
    """
    for i, rule1 in enumerate(rules):
        for j, rule2 in enumerate(rules):
            if j <= i:  # rule2必须是rule1后面的规则
                continue
            if judge_two_rules_conflict(rule1, rule2):  # rule1和rule2不能冲突
                continue
            rulei_constraint_type = get_rule_constraint_type(rule1)
            rulej_constraint_type = get_rule_constraint_type(rule2)
            if rulei_constraint_type == rulej_constraint_type and rulej_constraint_type != "":
                rule1 = compose_two_rules(rule1, rule2, reverse=False)
                del rules[j]

    return rules




def op_match(trigger, operation, op_part):
    if "撤销" in trigger and "撤销" in operation:
        trigger1 = trigger.replace("撤销", "")
        operation1 = operation.replace("撤销", "")
        if operation1 == "":
            if trigger1 in op_part:
                return True
        else:
            if operation1 in trigger1 or trigger1 in operation1:
                return True
        # if trigger.replace("撤销", "") in operation.replace("撤销", "") or operation.replace("撤销", "") in trigger.replace("撤销", ""):
        #     return True
    elif "撤销" in trigger or "撤销" in operation:
        return False
    elif trigger in operation or operation in trigger:
        return True
    elif "提交" in operation and trigger in op_part:
        return True
    else:
        return False

def compose_state_machine(rules, knowledge):
    """
    结合状态机隐式关系挖掘
    """
    state_machines = knowledge['stateMachine']
    new_rules = []
    for rule in rules:
        operation, operation_part, state = "", "", ""
        # 提取then中的操作、操作部分，if中的状态
        for condition in rule['consequences']:
            if condition[0] == "操作" and operation == "":
                operation = condition[2]
            if condition[0] == "操作部分" and operation_part == "":
                operation_part = condition[2]
            if operation != "" and operation_part != "":
                break
        for condition in rule['conditions']:
            if condition[0] == "状态" and state == "":
                state = condition[2]
            if state != "":
                break
        if operation == "":
            new_rules.append(rule)
            continue
        
        index = 1
        # 观察规则能否和状态机结合
        for state_machine in state_machines:
            state_name = state_machine['state_name']
            transition = state_machine['transition']
            for t in transition:
                fail = False
                trigger = t['trigger']
                if "失败" in trigger:
                    fail = True
                    trigger = trigger[:-2]
                if op_match(trigger, operation, operation_part):
                    compose = False
                    if fail:
                        # 这里是失败,所以操作也必须包含"不"，比如不接受这样
                        if "不" in operation:
                            compose = True
                    else:
                        # 这里是成功,所以操作不能包含"不"
                        if "不" not in operation:
                            compose = True
                    # 如果已有状态，判断状态是否匹配，不匹配直接跳过
                    if state != "" and state != t['from']:
                        compose = False
                    if not compose:
                        continue
                    # 添加状态机
                    new_rule = copy.deepcopy(rule)
                    new_rule['rule'] = rule['rule'] + "." + str(index)
                    index += 1
                    if state == "":
                        new_rule['conditions'].append(["状态", "is", t['from']])
                    new_rule['consequences'].append(["状态", "is", t['to']])
                    new_rules.append(new_rule)
        if index == 1:
            new_rules.append(rule)
    rules = new_rules
    return rules


def judge_conflict(rule1, rule2):
    conflict_keys = ["交易市场","交易品种","交易方式","交易方向"]
    conflict = False
    def not_in(key):
        for ki in conflict_keys:
            if ki in key:
                return False
        return True
    
    for c1 in rule1['conditions'] + rule1['consequences']:
        if c1[0] not in conflict_keys and not_in(c1[0]):
            continue
        else:
            if "品种" in c1[0] or "方式" in c1[0]:
                conflict_keys.append(f"{c1[2]}")
        for c2 in rule2['conditions'] + rule2['consequences']:
            if c1[0] == c2[0]:
                if c1[2]!=c2[2]:
                    # print(c1[0], c1[2], c2[2])
                    conflict = True
                break
        if conflict:
            break
    return conflict

def get_ori_id(rule_id, id_example):
    ids = []
    for id in rule_id.split(','):
        if "_" in id_example:
            ids.append(id.split("_")[0])
        elif "第" in id and "条" in id_example:
            ids.append(id.split(".")[0])
        else:
            point_count = id_example.count(".")
            ids.append(".".join(id.split(".")[:point_count+1]))
    return ids

def relation_mining(rules, id_example):
    """
    隐式关系挖掘
    对于所有规则两两观察是否有一条规则在consequences有状态，另一条规则在conditions有状态，且二者相等，有的话就关联。
    """
    for rule in rules:
        rule['before'] = []
        rule['after'] = []
    
    for i, rule1 in enumerate(rules):
        from_state1, to_state1 = "", ""
        for condition in rule1['conditions']:
            if condition[0] == "状态":
                from_state1 = condition[2]
        for consequence in rule1['consequences']:
            if consequence[0] == "状态":
                to_state1 = consequence[2]
        if from_state1 == "" and to_state1 == "":
            continue
        for j, rule2 in enumerate(rules):
            if j <= i:
                continue
            from_state2, to_state2 = "", ""
            for condition in rule2['conditions']:
                if condition[0] == "状态":
                    from_state2 = condition[2]
            for consequence in rule2['consequences']:
                if consequence[0] == "状态":
                    to_state2 = consequence[2]
            if from_state2 == "" and to_state2 == "":
                continue

            if from_state1 == to_state2 or ("撤销" not in from_state1 and "撤销" not in to_state2 and (from_state1 in to_state2 or to_state2 in from_state1)) or ("撤销" in from_state1 and "撤销" in to_state2 and (from_state1.replace("撤销", "") in to_state2.replace("撤销", "") or to_state2.replace("撤销", "") in from_state1.replace("撤销", ""))):  # 状态相同
                if judge_conflict(rule1, rule2):
                    continue
                # rule2 -> rule1
                find = False
                for a in rule2['after']:
                    if a in rule1['rule']:
                        find = True
                        break
                if not find:
                    rule2['after'].append(rule1['rule'])
                    rule1['before'].append(rule2['rule'])
            if from_state2 == to_state1 or ("撤销" not in from_state2 and "撤销" not in to_state1 and (from_state2 in to_state1 or to_state1 in from_state2)) or ("撤销" in from_state2 and "撤销" in to_state1 and (from_state2.replace("撤销", "") in to_state1.replace("撤销", "") or to_state1.replace("撤销", "") in from_state2.replace("撤销", ""))):
                if judge_conflict(rule1, rule2):
                    continue
                # rule1 -> rule2
                find = False
                for a in rule1['after']:
                    if a in rule2['rule']:
                        find = True
                        break
                if not find:
                    rule1['after'].append(rule2['rule'])
                    rule2['before'].append(rule1['rule'])
    relation = {}
    for rule in rules:
        for before_after in [rule['before'], rule['after']]:
            ori_ids = get_ori_id(rule['rule'], id_example)
            for ori_id in ori_ids:
                if ori_id not in relation:
                    relation[ori_id] = []
                for rule_id1 in before_after:
                    ori_id1s = get_ori_id(rule_id1, id_example)
                    for ori_id1 in ori_id1s:
                        if ori_id1 not in relation[ori_id]:
                            relation[ori_id].append(ori_id1)
    
    relation_count = int(sum([len(relation[rule_id]) for rule_id in list(relation.keys())]) / 2.0)
    return rules, relation_count, relation



def process_r2_to_r3(r2, knowledge):
    """
    规则关系挖掘函数, 包含:
    1. 时间、数量、价格，如果不冲突则组合
    2. 结合状态机
    3. 隐式关系挖掘
    """
    rules = mydsl_to_rules(r2)
    # rules[i] = {
    #     'conditions': [['债券品种', 'is', '债券现券']],
    #     'consequences': [['约束', 'is', '当日回转交易']],
    #     'rule': '3.1.8.1',
    #     'sourceId': ['3.1.8']
    # }

    # 1. 时间、数量、价格，如果不冲突则组合
    rules = compose_rules(rules)

    # 2. 结合状态机
    rules = compose_state_machine(rules, knowledge)

    # 3. 隐式关系挖掘
    if len(rules) > 0:
        id_example = rules[0]['sourceId'][0]
        rules, relation_count, relation = relation_mining(rules, id_example)
    else:
        rules, relation_count, relation = rules, 0, {}

    r3 = rules_to_mydsl(rules)
    return r3, relation_count, relation


if __name__ == "__main__":
    with open("cache/r2.mydsl", "r", encoding="utf-8") as f:
        r2 = f.read()
    knowledge = json.load(open("../reuse/domain_knowledge/knowledge.json", "r", encoding="utf-8"))
    r3, relation_count, relation = process_r2_to_r3(r2, knowledge)
    with open("cache/r3.mydsl", "w", encoding="utf-8") as f:
        f.write(r3)
    json.dump(relation, open("cache/relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print(f"挖掘到的隐式关系数: {relation_count}")