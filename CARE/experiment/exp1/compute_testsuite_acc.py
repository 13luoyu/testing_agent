import json
import math
import os
from nltk import edit_distance
import re
import argparse
from tqdm import tqdm


def eval_change(ours_change, label_change, dataset):
    """
    计算我们识别变更的准确率
    """
    ours_change = json.load(open(ours_change, 'r', encoding='utf-8'))
    label_change = json.load(open(label_change, 'r', encoding='utf-8'))

    # 计算我们识别的变更中有多少是正确的
    accuracy = len(set(ours_change) & set(label_change[dataset]))
    if len(ours_change) == 0:
        accuracy = 1
    else:
        accuracy /= len(label_change[dataset])
    return accuracy









threshold = 0.99
def eval_changed_testsuite(ours_testsuite, label_testsuite, strict=False):
    ours_testsuites = json.load(open(ours_testsuite, 'r', encoding='utf-8'))
    label_testsuites = json.load(open(label_testsuite, 'r', encoding='utf-8'))

    # 找到更新的suite
    updated_ours_testsuites, updated_label_testsuites = [], []
    dataset = ours_testsuite.split("/")[-1].split("_")[0]
    change = json.load(open("data/change.json", 'r', encoding='utf-8'))
    change_rule_ids = change[dataset]
    
    for testsuite in ours_testsuites:
        find = False
        for testcase in testsuite:
            testcase_ids = testcase['rule'].split(",")
            for rule_id in change_rule_ids:
                for testcase_id in testcase_ids:
                    if testcase_id.startswith(rule_id) and (testcase_id == rule_id or testcase_id[len(rule_id)] == "."):
                        find = True
                        break
                if find:
                    break
            if find:
                break
        if find:
            updated_ours_testsuites.append(testsuite)
    
    for testsuite in label_testsuites:
        find = False
        for testcase in testsuite:
            testcase_ids = testcase['rule'].split(",")
            for rule_id in change_rule_ids:
                for testcase_id in testcase_ids:
                    if testcase_id.startswith(rule_id) and (testcase_id == rule_id or testcase_id[len(rule_id)] == "."):
                        find = True
                        break
                if find:
                    break
            if find:
                break
        if find:
            updated_label_testsuites.append(testsuite)

    # 计算准确率
    find = [False for _ in range(len(updated_label_testsuites))]
    find_ = [False for _ in range(len(updated_ours_testsuites))]
    for i, testsuite in enumerate(updated_label_testsuites):
        for j, t in enumerate(updated_ours_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(i, j, testcase, tc, strict):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find[i] = True
                break

    for j, t in enumerate(updated_ours_testsuites):
        for i, testsuite in enumerate(updated_label_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(i, j, testcase, tc, strict):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find_[j] = True
                break
    
    recall = sum(find)
    recall /= len(updated_label_testsuites)
    precision = sum(find_)
    precision = precision / len(updated_ours_testsuites) if len(updated_ours_testsuites) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1










def str_same(s1, s2, threshold):
    """
    s1和s2的相似度大于threshold
    """
    if len(s1) == 0 or len(s2) == 0:
        return False
    return 1 - edit_distance(s1, s2) / max(len(s1), len(s2)) > threshold

def judge_same(cnt1, cnt2, t1, t2, strict=False):
    """
    t1和t2有threshold的元素相似，每个元素中value的相似度大于threshold
    """
    t1_keys, t1_values, t2_keys, t2_values = [], {}, [], {}
    if isinstance(t1, str):
        print(t1)
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
                if not str_same(k1, k2, threshold):
                    continue
                v1_like = 0
                for vi in v1:
                    for vj in v2:
                        if str_same(vi, vj, threshold):
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

def eval_testsuite(ours_testsuite, label_testsuite, strict=False):
    """
    计算我们生成测试用例和标签测试用例的准确性
    """
    ours_testsuites = json.load(open(ours_testsuite, 'r', encoding='utf-8'))
    label_testsuites = json.load(open(label_testsuite, 'r', encoding='utf-8'))

    # 计算我们生成的测试套件中有多少是正确的
    # ours_testcases = List[List[Dict]], 其中每一个List[Dict]是一个test suite
    if "llm4fin" in ours_testsuite:
        global threshold
        threshold = 0.45
    find = [False for _ in range(len(label_testsuites))]
    find_ = [False for _ in range(len(ours_testsuites))]
    for i, testsuite in enumerate(tqdm(label_testsuites)):
        for j, t in enumerate(ours_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(i, j, testcase, tc, strict):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find[i] = True
                break
    if "llm4fin" in ours_testsuite:
        threshold = 0.49
    for j, t in enumerate(tqdm(ours_testsuites)):
        for i, testsuite in enumerate(label_testsuites):
            if len(testsuite) != len(t):
                continue
            label_case_find = [False for _ in range(len(testsuite))]
            ours_case_find = [False for _ in range(len(t))]
            for k, testcase in enumerate(testsuite):
                for l, tc in enumerate(t):
                    if judge_same(i, j, testcase, tc, strict):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find_[j] = True
                break

    recall = sum(find) / len(label_testsuites)
    precision = sum(find_) / len(ours_testsuites)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1



def eval_ours_result(d):
    """
    计算制定数据集的change accuracy和testcase accuracy
    """
    result = {}
    for file in sorted(os.listdir("ours_result")):
        if d not in file:
            continue
        if "change" in file:
            dataset = file.split("_")[0]
            acc_change = eval_change(f"ours_result/{file}", "data/change.json", dataset)
            if dataset in result:
                result[dataset]["change"] = acc_change
            else:
                result[dataset] = {"change": acc_change}
            print(f"{dataset} change acc: {acc_change}")
        elif "testcase" in file:
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"ours_result/{file}", f"data/{dataset}_upd_testcase.json")
            precision_changed_testcase, recall_changed_testcase, f1_changed_testcase = eval_changed_testsuite(f"ours_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["precision_changed_testcase"] = precision_changed_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['recall_changed_testcase'] = recall_changed_testcase
            result[dataset]['f1_testcase'] = f1_testcase
            result[dataset]['f1_changed_testcase'] = f1_changed_testcase

    print(f"ours在{d}上的结果，change acc: {result[d]['change']}, testcase precision: {result[d]['precision_testcase']}, changed testcase precision: {result[d]['precision_changed_testcase']}, testcase recall: {result[d]['recall_testcase']}, changed testcase recall: {result[d]['recall_changed_testcase']}, testcase f1: {result[d]['f1_testcase']}, changed testcase f1: {result[d]['f1_changed_testcase']}")
    json.dump(result, open(f"log/ours_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)

def eval_gemini_result(d):
    result = {}
    for file in sorted(os.listdir("gemini_result")):
        if "change" in file:
            gemini_change = json.load(open(f"gemini_result/{file}", 'r', encoding='utf-8'))
            label_change = json.load(open("data/change.json", 'r', encoding='utf-8'))
            dataset = d
            find = 0
            for rule_id in label_change[dataset]:
                for id in gemini_change[dataset]:
                    if rule_id == id:
                        find += 1
                        break
            if dataset in result:
                result[dataset]["change"] = find / len(label_change[dataset])
            else:
                result[dataset] = {"change": find / len(label_change[dataset])}
            print(f"{dataset} change acc: {find / len(label_change[dataset])}")
        elif "testcase" in file:
            if d not in file:
                continue
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"gemini_result/{file}", f"data/{dataset}_upd_testcase.json")
            precision_changed_testcase, recall_changed_testcase, f1_changed_testcase = eval_changed_testsuite(f"gemini_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["precision_changed_testcase"] = precision_changed_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['recall_changed_testcase'] = recall_changed_testcase
            result[dataset]['f1_testcase'] = f1_testcase
            result[dataset]['f1_changed_testcase'] = f1_changed_testcase

    print(f"gemini在{d}上的结果，change acc: {result[d]['change']}, testcase precision: {result[d]['precision_testcase']}, changed testcase precision: {result[d]['precision_changed_testcase']}, testcase recall: {result[d]['recall_testcase']}, changed testcase recall: {result[d]['recall_changed_testcase']}, testcase f1: {result[d]['f1_testcase']}, changed testcase f1: {result[d]['f1_changed_testcase']}")
    json.dump(result, open(f"log/gemini_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)

def eval_expert_result(d):
    result = {}
    for file in sorted(os.listdir("expert_result")):
        if "change" in file:
            expert_change = json.load(open(f"expert_result/{file}", 'r', encoding='utf-8'))
            label_change = json.load(open("data/change.json", 'r', encoding='utf-8'))
            dataset = d
            find = 0
            for rule_id in label_change[dataset]:
                for id in expert_change[dataset]:
                    if rule_id == id:
                        find += 1
                        break
            if dataset in result:
                result[dataset]["change"] = find / len(label_change[dataset])
            else:
                result[dataset] = {"change": find / len(label_change[dataset])}
            print(f"{dataset} change acc: {find / len(label_change[dataset])}")
        elif "testcase" in file:
            if d not in file:
                continue
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"expert_result/{file}", f"data/{dataset}_upd_testcase.json")
            precision_changed_testcase, recall_changed_testcase, f1_changed_testcase = eval_changed_testsuite(f"expert_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["precision_changed_testcase"] = precision_changed_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['recall_changed_testcase'] = recall_changed_testcase
            result[dataset]['f1_testcase'] = f1_testcase
            result[dataset]['f1_changed_testcase'] = f1_changed_testcase

    print(f"expert在{d}上的结果，change acc: {result[d]['change']}, testcase precision: {result[d]['precision_testcase']}, changed testcase precision: {result[d]['precision_changed_testcase']}, testcase recall: {result[d]['recall_testcase']}, changed testcase recall: {result[d]['recall_changed_testcase']}, testcase f1: {result[d]['f1_testcase']}, changed testcase f1: {result[d]['f1_changed_testcase']}")
    json.dump(result, open(f"log/expert_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)

def eval_llm4fin_result(d):
    result = {}
    for file in sorted(os.listdir("llm4fin_result")):
        if "testcase" in file:
            if d not in file:
                continue
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"llm4fin_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['f1_testcase'] = f1_testcase

    print(f"llm4fin在{d}上的结果，testcase precision: {result[d]['precision_testcase']}, testcase recall: {result[d]['recall_testcase']}, testcase f1: {result[d]['f1_testcase']}")
    json.dump(result, open(f"log/llm4fin_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)


def eval_gpt_result(d):
    result = {}
    for file in sorted(os.listdir("gpt_result")):
        if "change" in file:
            gpt_change = json.load(open(f"gpt_result/{file}", 'r', encoding='utf-8'))
            label_change = json.load(open("data/change.json", 'r', encoding='utf-8'))
            dataset = d
            find = 0
            for rule_id in label_change[dataset]:
                for id in gpt_change[dataset]:
                    if rule_id == id:
                        find += 1
                        break
            if dataset in result:
                result[dataset]["change"] = find / len(label_change[dataset])
            else:
                result[dataset] = {"change": find / len(label_change[dataset])}
            print(f"{dataset} change acc: {find / len(label_change[dataset])}")
        elif "testcase" in file:
            if d not in file:
                continue
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"gpt_result/{file}", f"data/{dataset}_upd_testcase.json")
            precision_changed_testcase, recall_changed_testcase, f1_changed_testcase = eval_changed_testsuite(f"gpt_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["precision_changed_testcase"] = precision_changed_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['recall_changed_testcase'] = recall_changed_testcase
            result[dataset]['f1_testcase'] = f1_testcase
            result[dataset]['f1_changed_testcase'] = f1_changed_testcase

    print(f"gpt在{d}上的结果，change acc: {result[d]['change']}, testcase precision: {result[d]['precision_testcase']}, changed testcase precision: {result[d]['precision_changed_testcase']}, testcase recall: {result[d]['recall_testcase']}, changed testcase recall: {result[d]['recall_changed_testcase']}, testcase f1: {result[d]['f1_testcase']}, changed testcase f1: {result[d]['f1_changed_testcase']}")
    json.dump(result, open(f"log/gpt_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)


def eval_grok_result(d):
    result = {}
    for file in sorted(os.listdir("grok_result")):
        if "change" in file:
            grok_change = json.load(open(f"grok_result/{file}", 'r', encoding='utf-8'))
            label_change = json.load(open("data/change.json", 'r', encoding='utf-8'))
            dataset = d
            find = 0
            for rule_id in label_change[dataset]:
                for id in grok_change[dataset]:
                    if rule_id == id:
                        find += 1
                        break
            if dataset in result:
                result[dataset]["change"] = find / len(label_change[dataset])
            else:
                result[dataset] = {"change": find / len(label_change[dataset])}
            print(f"{dataset} change acc: {find / len(label_change[dataset])}")
        elif "testcase" in file:
            if d not in file:
                continue
            dataset = file.split("_")[0]
            precision_testcase, recall_testcase, f1_testcase = eval_testsuite(f"grok_result/{file}", f"data/{dataset}_upd_testcase.json")
            precision_changed_testcase, recall_changed_testcase, f1_changed_testcase = eval_changed_testsuite(f"grok_result/{file}", f"data/{dataset}_upd_testcase.json")
            if dataset not in result:
                result[dataset] = {}
            result[dataset]["precision_testcase"] = precision_testcase
            result[dataset]["precision_changed_testcase"] = precision_changed_testcase
            result[dataset]["recall_testcase"] = recall_testcase
            result[dataset]['recall_changed_testcase'] = recall_changed_testcase
            result[dataset]['f1_testcase'] = f1_testcase
            result[dataset]['f1_changed_testcase'] = f1_changed_testcase

    print(f"grok在{d}上的结果，change acc: {result[d]['change']}, testcase precision: {result[d]['precision_testcase']}, changed testcase precision: {result[d]['precision_changed_testcase']}, testcase recall: {result[d]['recall_testcase']}, changed testcase recall: {result[d]['recall_changed_testcase']}, testcase f1: {result[d]['f1_testcase']}, changed testcase f1: {result[d]['f1_changed_testcase']}")
    json.dump(result, open(f"log/grok_ts_result_{d}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=4)




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="dataset1")
    parser.add_argument("--method", type=str, default="ours")
    args = parser.parse_args()
    dataset = args.dataset
    method = args.method
    if method == "ours":
        eval_ours_result(dataset)
    elif method == "gemini":
        eval_gemini_result(dataset)
    elif method == "gpt":
        eval_gpt_result(dataset)
    elif method == "grok":
        eval_grok_result(dataset)
    elif method == "expert":
        eval_expert_result(dataset)
    elif method == "llm4fin":
        eval_llm4fin_result(dataset)