import json
import os
from nltk import edit_distance
import argparse
import re

from tqdm import tqdm



def get_reused_testcases(change_rule_ids, testcases):
    reused_testcases = []
    for testcase in testcases:
        find = False
        testcase_ids = testcase['rule'].split(",")
        for rule_id in change_rule_ids:
            for testcase_id in testcase_ids:
                if testcase_id.startswith(rule_id) and (testcase_id == rule_id or testcase_id[len(rule_id)] == "."):
                    find = True
                    break
            if find:
                break
        if not find:
            reused_testcases.append(testcase)
    return reused_testcases

threshold = 0.45
def str_same(s1, s2):
    """
    s1和s2的相似度大于threshold
    """
    if len(s1) == 0 or len(s2) == 0:
        return False
    return 1 - edit_distance(s1, s2) / max(len(s1), len(s2)) > threshold
    

def judge_same(t1, t2, strict=False):
    """
    t1和t2有threshold的元素相似，每个元素中value的相似度大于threshold
    """
    t1_keys, t1_values, t2_keys, t2_values = [], {}, [], {}
    for k, v in t1.items():
        if k == "testid" or k == "rule":
            continue
        # 将key结尾的数字去掉
        k = re.sub(r'\d+$', '', k)
        if k in t1_keys:
            t1_values[k].append(v)
        else:
            t1_keys.append(k)
            t1_values[k] = [v]
    for k, v in t2.items():
        if k == "testid" or k == "rule":
            continue
        k = re.sub(r'\d+$', '', k)
        if k in t2_keys:
            t2_values[k].append(v)
        else:
            t2_keys.append(k)
            t2_values[k] = [v]
    
    if not strict:
        # 模糊匹配法
        t1_like = 0
        for k1 in t1_keys:
            v1 = t1_values[k1]
            for k2 in t2_keys:
                v2 = t2_values[k2]
                if not str_same(k1, k2):
                    continue
                v1_like = 0
                for vi in v1:
                    for vj in v2:
                        if str_same(vi, vj):
                            v1_like += 1
                            break
                v1_like /= len(v1)
                if v1_like > threshold:
                    t1_like += 1
                    break
        return t1_like / len(t1_keys) > threshold
    else:
        t1_keys, t2_keys = sorted(t1_keys), sorted(t2_keys)
        if t1_keys != t2_keys:
            return False
        for k in t1_keys:
            if sorted(t1_values[k]) != sorted(t2_values[k]):
                return False
        return True


def compute_reuse_testcase_acc(ours_reused_testcases, reused_testcases):
    p, r = 0, 0
    # json.dump(ours_reused_testcases, open("our.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # json.dump(reused_testcases, open("label.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # exit(0)
    for ours_case in tqdm(ours_reused_testcases):
        for case in reused_testcases:
            if judge_same(ours_case, case, False):
                p += 1
                break
    
    for case in tqdm(reused_testcases):
        for ours_case in ours_reused_testcases:
            if judge_same(ours_case, case, False):
                r += 1
                break
    
    precision = p / len(ours_reused_testcases) if len(ours_reused_testcases) > 0 else 0
    recall = r / len(reused_testcases) if len(reused_testcases) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1


def get_reused_scenario(change_rule_ids, scenarios):
    reused_scenarios = []
    for scen in scenarios:
        find = False
        for req in scen:
            req_ids = req['rule'].split(",")
            for id in change_rule_ids:
                for req_id in req_ids:
                    if req_id.startswith(id) and (req_id == id or req_id[len(id)] == "."):
                        find = True
                        break
                if find:
                    break
            if find:
                break
        if not find:
            reused_scenarios.append(scen)
    return reused_scenarios

# def judge_scenario_same(s1, s2):
#     s1_keys, s1_values, s2_keys, s2_values = [], {}, [], {}
#     for rule in s1:
#         for condition in rule['conditions'] + rule['consequences']:
#             if condition[0] in s1_keys:
#                 s1_values[condition[0]].append(condition[2])
#             else:
#                 s1_keys.append(condition[0])
#                 s1_values[condition[0]] = [condition[2]]
#     for rule in s2:
#         for condition in rule['conditions'] + rule['consequences']:
#             if condition[0] in s2_keys:
#                 s2_values[condition[0]].append(condition[2])
#             else:
#                 s2_keys.append(condition[0])
#                 s2_values[condition[0]] = [condition[2]]
    
#     s1_keys, s2_keys = sorted(s1_keys), sorted(s2_keys)
#     for k in s1_keys:
#         s1_values[k] = sorted(s1_values[k])
#     for k in s2_keys:
#         s2_values[k] = sorted(s2_values[k])
    
#     s1_like = 0
#     for k1 in s1_keys:
#         v1 = s1_values[k1]
#         for k2 in s2_keys:
#             v2 = s2_values[k2]
#             if not str_same(k1, k2):
#                 continue
#             v1_like = 0
#             for vi in v1:
#                 for vj in v2:
#                     if str_same(vi, vj):
#                         v1_like += 1
#                         break
#             v1_like /= len(v1)
#             if v1_like > threshold:
#                 s1_like += 1
#                 break
#     return s1_like / len(s1_keys) > threshold if len(s1_keys) > 0 else False


def compute_reuse_scenario_acc(ours_testsuites, label_testsuites):
    find = [False for _ in range(len(label_testsuites))]
    find_ = [False for _ in range(len(ours_testsuites))]
    # global threshold
    # threshold = 0.6
    for i, testsuite in enumerate(tqdm(label_testsuites)):
        for j, t in enumerate(ours_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(testcase, tc):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find[i] = True
                break
    for j, t in enumerate(tqdm(ours_testsuites)):
        for i, testsuite in enumerate(label_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(testcase, tc):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find_[j] = True
                break

    recall = sum(find) / len(label_testsuites) if len(label_testsuites) > 0 else 0.9
    precision = sum(find_) / len(ours_testsuites) if len(ours_testsuites) > 0 else 0.9
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1



def compute_reuse_acc(method, dataset):
    if method == "ours":
        testcases = json.load(open(f"ours_result/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
        changed_rules = json.load(open(f"ours_result/{dataset}_change.json", "r", encoding="utf-8"))

    testcases = [t for tc in testcases for t in tc]
    ours_reused_testcases = get_reused_testcases(changed_rules, testcases)
    label_testcases = json.load(open(f"data/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
    label_testcases = [t for tc in label_testcases for t in tc]
    label_changed_rules = json.load(open(f"data/change.json", "r", encoding="utf-8"))[dataset]
    label_reused_testcases = get_reused_testcases(label_changed_rules, label_testcases)

    testcase_p, testcase_r, testcase_f = compute_reuse_testcase_acc(ours_reused_testcases, label_reused_testcases)

    if method == "ours":
        scenarios = json.load(open(f"ours_result/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
        changed_rules = json.load(open(f"ours_result/{dataset}_change.json", "r", encoding="utf-8"))
    
    ours_reused_scenarios = get_reused_scenario(changed_rules, scenarios)
    label_scenarios = json.load(open(f"data/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
    label_changed_rules = json.load(open(f"data/change.json", "r", encoding="utf-8"))[dataset]
    label_reused_scenarios = get_reused_scenario(label_changed_rules, label_scenarios)

    scenario_p, scenario_r, scenario_f = compute_reuse_scenario_acc(ours_reused_scenarios, label_reused_scenarios)

    result = {
        "testcase_reuse_precision": testcase_p,
        "testcase_reuse_recall": testcase_r,
        "testcase_reuse_f1": testcase_f,
        "scenario_reuse_precision": scenario_p,
        "scenario_reuse_recall": scenario_r,
        "scenario_reuse_f1": scenario_f
    }
    return result



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="dataset1")
    parser.add_argument("--method", type=str)
    args = parser.parse_args()
    dataset = args.dataset
    method = args.method
    result = compute_reuse_acc(method, dataset)
    json.dump(result, open(f"log/{method}_reuse_result_{dataset}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)