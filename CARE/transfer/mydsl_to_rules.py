
# 读文件
import json


def mydsl_to_rules(s):
    """读文件并解析, 将环境常量写入defines, 规则写入rules"""

    rules = list()
    # rules = [
    #     {
    #         "rule": "3.3.8.1",
    #         "sourceId": ["1.1.1", "1.1.2"],
    #         "conditions": [["交易方式", "is", "竞买成交"], ...],
    #         "consequences": [["交易结果", "is", "已申报"], ...],
    #         "before": ["1.1.1", "1.1.2"],
    #         "after": ["1.1.1", "1.1.2"]
    #     }
    # ]


    lines = s.split("\n")
    for line in lines:
        l = line.strip().split(" ")
        
        # 跳过空行
        if len(l) == 0:
            continue
        
        if l[0] == "rule":
            rule_id = l[1]
            rule = {"rule": "", "sourceId": [], "conditions": [], "consequences": []}
            rule["rule"] = rule_id
        
        elif l[0] == 'sourceId':
            sourceId = l[1].split(',')
            rule['sourceId'] = sourceId
        
        elif l[0] == "before:":
            rule['before'] = l[1].split(',')
        elif l[0] == "after:":
            rule['after'] = l[1].split(',')
        
        elif l[0] == "if":
            conditions = []
            i = 1
            while i < len(l):
                next_and = i + 1
                while next_and < len(l) and l[next_and] != "and":
                    next_and += 1
                condition = l[i:next_and]
                conditions.append(condition)
                i = next_and + 1
            rule['conditions'] = conditions
        
        elif l[0] == "then":
            i = 1
            consequences = []
            while i < len(l):
                next_and = i + 1
                while next_and < len(l) and l[next_and] != "and":
                    next_and += 1
                consequence = l[i:next_and]
                consequences.append(consequence)
                i = next_and + 1
            rule['consequences'] = consequences
            rules.append(rule)
        
        elif "or relation" in line:
            rules[-1]['or relation'] = line.split(":")[-1].split(",")

    return rules




def transfer_new_rule_format_to_old(rules):
    """
    rules = [
        {
            "rule": "3.3.8.1",
            "sourceId": "1.1.1, 1.1.2",
            "conditions": [["交易方式", "is", "竞买成交"], ...],
            "consequences": [["交易结果", "is", "已申报"], ...],
            "before": ["1.1.1", "1.1.2"],
            "after": ["1.1.1", "1.1.2"]
        }
    ]

    return:
    rules = {
        "4.1.1.1": {
            "constraints": [
                {"key": "交易方式", "operation": "is", "value": "竞买成交"}
            ],
            "results": [
                {"else": "未申报", "key": "交易结果", "value": "已申报"
                }
            ],
            "rule_class": ["4.1.1"],
            "before": ["1.1.1", "1.1.2"],
            "after": ["1.1.1", "1.1.2"]
        }
    }
    """
    new_rules = {}
    for rule in rules:
        rule_id = rule['rule']
        new_rules[rule_id] = {}
        if "before" in rule:
            new_rules[rule_id]['before'] = rule['before']
        if "after" in rule:
            new_rules[rule_id]['after'] = rule['after']
        new_rules[rule_id]['rule_class'] = rule['sourceId']
        new_rules[rule_id]['constraints'] = []
        new_rules[rule_id]['results'] = []
        for condition in rule['conditions']:
            new_rules[rule_id]['constraints'].append({
                'key': condition[0],
                'operation': condition[1],
                'value': condition[2]
            })
        for consequence in rule['consequences']:
            new_rules[rule_id]['results'].append({
                'key': consequence[0],
                'value': consequence[2],
                'operation': consequence[1],
            })
    return new_rules

def transfer_old_rule_format_to_new(rules):
    new_rules = []
    for rule_id, rule in rules.items():
        new_rule = {
            "rule": rule_id,
            "sourceId": rule['rule_class'],
            "conditions": [],
            "consequences": []
        }
        for constraint in rule['constraints']:
            new_rule['conditions'].append([constraint['key'], constraint['operation'], constraint['value']])
        for result in rule['results']:
            new_rule['consequences'].append([result['key'], result['operation'], result['value']])
        if "before" in rule:
            new_rule['before'] = rule['before']
        if "after" in rule:
            new_rule['after'] = rule['after']
        new_rules.append(new_rule)
    return new_rules






if __name__ == "__main__":
    r = open("../ours/cache/r1.mydsl", "r", encoding="utf-8").read()
    rules = mydsl_to_rules(r)
    print(rules)