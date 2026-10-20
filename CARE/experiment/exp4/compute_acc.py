from experiment.exp1.compute_testsuite_acc import eval_testsuite
from experiment.exp1.compute_reuse import get_reused_scenario
import os
import json
import argparse
from nltk import edit_distance
import re
from tqdm import tqdm

# nohup python compute_acc.py >log/run_compute_acc.log &

threshold = 0.99
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

def compute_reuse_scenario_acc(ours_testsuites, label_testsuites):
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
                    if judge_same(i, j, testcase, tc):
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
                    if judge_same(i, j, testcase, tc):
                        label_case_find[k] = True
                        ours_case_find[l] = True
            if all(label_case_find) and all(ours_case_find):
                find_[j] = True
                break

    recall = sum(find) / len(label_testsuites) if len(label_testsuites) > 0 else 0
    precision = sum(find_) / len(ours_testsuites) if len(ours_testsuites) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1


def eval_ours_result(model, dataset, content):
    if content == "reuse":
        label_changed_rules = json.load(open(f"data/{model}_data/change.json", "r", encoding="utf-8"))[dataset]
        label_testsuites = json.load(open(f"data/{model}_data/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
        label_reused_testsuites = get_reused_scenario(label_changed_rules, label_testsuites)

        ours_changed_rules = json.load(open(f"data/{model}_data/change.json", "r", encoding="utf-8"))[dataset]
        ours_testsuites = json.load(open(f"ours_result/{model}/{dataset}_upd_testcase.json", "r", encoding="utf-8"))
        ours_reused_testsuites = get_reused_scenario(ours_changed_rules, ours_testsuites)

        ts_reuse_p, ts_reuse_r, ts_reuse_f = compute_reuse_scenario_acc(ours_reused_testsuites, label_reused_testsuites)
        rs = json.load(open(f"log/{model}_result_{dataset}.json", "r", encoding="utf-8")) if os.path.exists(f"log/{model}_result_{dataset}.json") else {}
        rs.update({"ts_reuse_p": ts_reuse_p, "ts_reuse_r": ts_reuse_r, "ts_reuse_f": ts_reuse_f})
        json.dump(rs, open(f"log/{model}_result_{dataset}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

        print({"model": model, "dataset": dataset, "ts_reuse_p": ts_reuse_p, "ts_reuse_r": ts_reuse_r, "ts_reuse_f": ts_reuse_f})

    else:
        ts_p, ts_r, ts_f = eval_testsuite(f"ours_result/{model}/{dataset}_upd_testcase.json", f"data/{model}_data/{dataset}_upd_testcase.json")

        rs = json.load(open(f"log/{model}_result_{dataset}.json", "r", encoding="utf-8")) if os.path.exists(f"log/{model}_result_{dataset}.json") else {}
        rs.update({"ts_p": ts_p, "ts_r": ts_r, "ts_f": ts_f})
        json.dump(rs, open(f"log/{model}_result_{dataset}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        print({"model": model, "dataset": dataset, "ts_p": ts_p, "ts_r": ts_r, "ts_f": ts_f})





if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="glm4")
    parser.add_argument("--dataset", type=str, default="dataset1")
    parser.add_argument("--content", choices=["reuse", "acc"])
    args = parser.parse_args()
    model = args.model
    dataset = args.dataset
    content = args.content

    eval_ours_result(model, dataset, content)
