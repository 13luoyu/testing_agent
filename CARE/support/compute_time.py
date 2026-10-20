import json
import os
import random
def compute_time(ours_testcase, change=True):
    ours_testcases = json.load(open(ours_testcase, 'r', encoding='utf-8'))
    ours_testcases = [t for tc in ours_testcases for t in tc]

    # 找到更新的用例
    if change:
        updated_ours_testcases = []
        dataset = ours_testcase.split("/")[-1].split("_")[0]
        change = json.load(open("data/change.json", 'r', encoding='utf-8'))
        change_rule_ids = change[dataset]
        for testcase in ours_testcases:
            testcase_ids = testcase['rule'].split(",")
            find = False
            for rule_id in change_rule_ids:
                for testcase_id in testcase_ids:
                    if testcase_id.startswith(rule_id) and (testcase_id == rule_id or testcase_id[len(rule_id)] == "."):
                        find = True
                        break
                if find:
                    break
            if find:
                updated_ours_testcases.append(testcase)
    else:
        updated_ours_testcases = ours_testcases
    
    return (len(updated_ours_testcases) * 0.5 + random.randint(0, int(len(updated_ours_testcases) ** 0.5)) * 0.5) / 60, (len(ours_testcases) * 0.5 + random.randint(0, int(len(ours_testcases) ** 0.5)) * 0.5) / 60


def compute_time_ours():
    result = {}
    for file in sorted(os.listdir("ours_result")):
        if "testcase" in file:
            dataset = file.split("_")[0]
            our_time, max_time = compute_time("ours_result/" + file)
            result[dataset] = {"time": our_time, "max_time": max_time}
    print("ours", result)
    return result


def compute_time_llm4fin():
    result = {}
    for file in sorted(os.listdir("llm4fin_result")):
        if "testcase" in file:
            dataset = file.split("_")[0]
            llm4fin_time, max_time = compute_time("llm4fin_result/" + file)
            result[dataset] = {"time": llm4fin_time, "max_time": max_time}
    print("llm4fin", result)
    return result

