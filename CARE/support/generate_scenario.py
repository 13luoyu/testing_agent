import os
import json

keys = ["交易市场", "交易品种", "股票品种", "基金品种", "债券品种", "权证品种", "存托凭证品种", "交易方式", "交易方向", "交易类型", "事件", "操作", "操作主体", "操作对象", "操作部分", "状态", "时间", "数量", "价格"]

def generate_scenario(cases: list[list[dict]]):

    scenario = []

    for case in cases:
        # 将测试用例中的rule、testid、结果去掉，同时将操作、操作2、操作3等合并为操作
        case_keys = list(case.keys())
        case_keys = [key for key in case_keys if key not in ["rule", "testid", "结果"]]
        new_case = {}
        for key in case_keys:
            origin_key = key
            if key[-1].isdigit():
                while key and key[-1].isdigit():
                    key = key[:-1]
            if key not in new_case:
                new_case[key] = []
            new_case[key].append(case[origin_key])
        case = new_case
        case_keys = list(case.keys())
        for key in case_keys:
            case[key] = sorted(case[key])
            case[key] = ",".join(case[key])
        
        # 将测试用例按顺序写成str
        visit = [False for _ in case_keys]
        s = ""
        for key in keys:
            if key in case_keys:
                visit[case_keys.index(key)] = True
                s += f"{key}:{case[key]};"
            key = "结果" + key
            if key in case_keys:
                visit[case_keys.index(key)] = True
                s += f"{key}:{case[key]};"
        for i, v in enumerate(visit):
            if not v:
                key, value = case_keys[i], case[case_keys[i]]
                s += f"{key}:{value};"
                if key.startswith("结果"):
                    key = key[2:]
                if key not in keys:
                    keys.append(key)
        
        scenario.append(s[:-1])
    scenario = list(set(scenario))
    
    return "\n".join(scenario)

def transfer_to_case(cases):
    new_cases = []
    cases = [ci for c in cases for ci in c]
    for case in cases:
        new_case = {}
        new_case['rule'] = case['rule']
        for c in case['conditions']:
            key, value = c[0], c[2]
            if c[1] != "is":
                value = c[1] + value
            if "申报" in key and "数量" in key:
                key = "申报数量"
            if key in new_case:
                i = 2
                while f"{key}{i}" in new_case:
                    i += 1
                key = f"{key}{i}"
            new_case[key] = value
        for c in case['consequences']:
            key, value = "结果" + c[0], c[2]
            if c[1] != "is":
                value = c[1] + value
            if "申报" in key and "数量" in key:
                key = "申报数量"
            if key in new_case:
                i = 2
                while f"{key}{i}" in new_case:
                    i += 1
                key = f"{key}{i}"
            new_case[key] = value
        new_cases.append(new_case)
    return new_cases


if __name__ == "__main__":
    change = json.load(open("../experiment/exp1/data/change.json"))

    for file in sorted(os.listdir("../experiment/exp1/data")):
        if "upd_linked_scenario" not in file:
            continue
        cases = json.load(open("../experiment/exp1/data/" + file, "r", encoding="utf-8"))
        cases = transfer_to_case(cases)
        scenario = generate_scenario(cases)
        dataset = file.split("_")[0]
        with open(f"../experiment/exp1/scenario/{dataset}_scenario.txt", "w", encoding="utf-8") as f:
            f.write(scenario)
        
        changed_cases = []
        for changed_rule_id in change[dataset]:
            for case in cases:
                case_rule_ids = case['rule'].split(",")
                for id in case_rule_ids:
                    if id.startswith(changed_rule_id) and (len(id) == len(changed_rule_id) or id[len(changed_rule_id)] == "."):
                        changed_cases.append(case)
                        break
        changed_scenario = generate_scenario(changed_cases)
        with open(f"../experiment/exp1/scenario/{dataset}_changed_scenario.txt", "w", encoding="utf-8") as f:
            f.write(changed_scenario)