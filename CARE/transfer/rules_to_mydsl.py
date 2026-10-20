from transfer.mydsl_to_rules import mydsl_to_rules
from tqdm import tqdm
# 本函数的作用是，将内部数据格式rules写成R规则
def rules_to_mydsl(rules):
    # rules = [
    #     {
    #         "rule": "3.3.8.1",
    #         "sourceId": ["3.3.8", ...],
    #         "conditions": [["交易方式", "is", "竞买成交"], ...],
    #         "consequences": [["交易结果", "is", "已申报"], ...],
    #         "before": ['3.2.4.1.1.2.1', '3.2.4.1.2.2.1', ...],
    #         "after": ['3.3.1.2.2.1', '3.3.1.3.2.1', ...]
    #     },...
    # ]

    r = ""
    for rule in rules:
        r += f"rule {rule['rule']}\n"
        if "sourceId" in rule:
            r += f"sourceId {','.join(rule['sourceId'])}\n"
        if "before" in rule and rule['before'] != []:
            r += f"before: {','.join(rule['before'])}\n"
        if "after" in rule and rule['after'] != []:
            r += f"after: {','.join(rule['after'])}\n"
        r += "if "
        for condition in rule['conditions']:
            r += f"{' '.join(condition)} and "
        if len(rule['conditions']) == 0:
            r = r[:-1] + "\n"
        else:
            r = r[:-5] + "\n"
        r += "then "
        for consequence in rule['consequences']:
            r += f"{' '.join(consequence)} and "
        if len(rule['consequences']) == 0:
            r = r[:-1] + "\n"
        else:
            r = r[:-5] + "\n"
        if "or relation" in rule:
            r += f"or relation:{','.join(rule['or relation'])}\n"
        r += "\n"
    return r.strip()

if __name__ == "__main__":
    r = open("../ours/cache/r1.mydsl", "r", encoding="utf-8").read()
    rules = mydsl_to_rules(r)
    reversed_r = rules_to_mydsl(rules)
    print(f"r == reversed_r: {r == reversed_r}")