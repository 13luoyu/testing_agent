import json
import os
from reuse.process_r3_to_testcase import is_num_key, is_price_key, is_time_key

def transfer_case_to_scenario(cases, labels):
    scenarios = []
    labels = [l for lb in labels for l in lb]

    for caselist in cases:
        sc = []
        for case in caselist:
            if "结果" not in case or case['结果'] != "成功":
                continue
            scenario = {"rule": "", "conditions": [], "consequences": []}
            for key in list(case.keys()):
                if key == "testid":
                    continue
                if key == "rule":
                    scenario["rule"] = case[key]
                elif "结果" in key:
                    if key == "结果":
                        continue
                    add = False
                    if is_time_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_time_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    elif is_num_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_num_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    elif is_price_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_price_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    else:
                        add = True
                        scenario['consequences'].append([key[2:], "is", case[key]])
                    if not add:
                        scenario['consequences'].append([key[2:], "is", case[key]])
                else:
                    add = False
                    if is_time_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_time_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    elif is_num_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_num_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    elif is_price_key(key):
                        for l in labels:
                            if l['rule'] != case['rule']:
                                continue
                            add = True
                            for c in l['consequences']:
                                if is_price_key(c[0]):
                                    if c not in scenario['consequences']:
                                        scenario['consequences'].append(c)
                    else:
                        add = True
                        scenario['conditions'].append([key, "is", case[key]])
                    if not add:
                        scenario['conditions'].append([key, "is", case[key]])
            sc.append(scenario)
        scenarios.append(sc)

    return scenarios


if __name__ == "__main__":

    for file in os.listdir("../experiment/exp1/grok_result"):
        if "testcase" not in file:
            continue
        dataset = file.split("_")[0]
        cases = json.load(open("../experiment/exp1/grok_result/" + file, "r", encoding="utf-8"))
        labels = json.load(open(f"../experiment/exp1/data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
        scenarios = transfer_case_to_scenario(cases, labels)
        json.dump(scenarios, open(f"../experiment/exp1/grok_result/{dataset}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    for file in os.listdir("../experiment/exp1/gemini_result"):
        if "testcase" not in file:
            continue
        dataset = file.split("_")[0]
        cases = json.load(open("../experiment/exp1/gemini_result/" + file, "r", encoding="utf-8"))
        labels = json.load(open(f"../experiment/exp1/data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
        scenarios = transfer_case_to_scenario(cases, labels)
        json.dump(scenarios, open(f"../experiment/exp1/gemini_result/{dataset}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    for file in os.listdir("../experiment/exp1/gpt_result"):
        if "testcase" not in file:
            continue
        dataset = file.split("_")[0]
        cases = json.load(open("../experiment/exp1/gpt_result/" + file, "r", encoding="utf-8"))
        labels = json.load(open(f"../experiment/exp1/data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
        scenarios = transfer_case_to_scenario(cases, labels)
        json.dump(scenarios, open(f"../experiment/exp1/gpt_result/{dataset}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    # for file in os.listdir("../experiment/exp2/llm4fin_result"):
    #     if "testcase" not in file:
    #         continue
    #     dataset = file.split("_")[0]
    #     cases = json.load(open("../experiment/exp2/llm4fin_result/" + file, "r", encoding="utf-8"))
    #     labels = json.load(open(f"../experiment/exp2/data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
    #     scenarios = transfer_case_to_scenario(cases, labels)
    #     json.dump(scenarios, open(f"../experiment/exp2/llm4fin_result/{dataset}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)