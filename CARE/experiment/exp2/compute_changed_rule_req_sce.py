import json
from experiment.exp1.compute_bsc import judge_same
import argparse

# 为什么要统计哪些rule/req/sce是add的，哪些是del的
# 已有信息：真实变更的rule/req/sce，我们的变更的rule/req/sce
# 目标：计算precision、recall、f1
# 方法：找到被del的项，找到add的项，看看del的项在ours中是不是不存在，看看add的项在ours中是不是存在
# precision = 我们正确的变更数/我们的变更总数
# recall = 我们正确的变更数/真实变更总数

def compute_rule_acc(method, dataset):
    label = json.load(open("data/change.json", "r", encoding="utf-8"))[dataset]
    if method in ["ours", "no_requirement", "no_scenario", "no_change_impact_analysis"]:
        expect = json.load(open(f"{method}/{dataset}_change.json", "r", encoding="utf-8"))
    else:
        expect = json.load(open(f"{method}/change.json", "r", encoding="utf-8"))[dataset]


    precision_count, recall_count = 0, 0
    for l in label:
        for e in expect:
            if l == e:
                recall_count += 1
                break
    
    for e in expect:
        for l in label:
            if e == l:
                precision_count += 1
                break

    precision = precision_count / len(expect) if len(expect) > 0 else 0
    recall = recall_count / len(label) if len(label) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return precision, recall, f1

def requirement_same(r1, r2):
    r1_values, r2_values = [], []
    for item in r1['conditions']:
        if item[2] not in r1_values:
            r1_values.append(item[2])
    for item in r1['consequences']:
        if item[2] not in r1_values:
            r1_values.append(item[2])
    for item in r2['conditions']:
        if item[2] not in r2_values:
            r2_values.append(item[2])
    for item in r2['consequences']:
        if item[2] not in r2_values:
            r2_values.append(item[2])

    if len(r1_values) != len(r2_values):
        return False
    cover = [False for _ in range(len(r1_values))]
    for i, v1 in enumerate(r1_values):
        for v2 in r2_values:
            if judge_same(v1, v2):
                cover[i] = True
                break
    return sum(cover) / len(cover) >= 0.8


def select_changed_requirements(reqs, changed_rule_ids):
    selected_reqs = []
    for req in reqs:
        add = False
        for req_id in req['rule'].split(","):
            for id in changed_rule_ids:
                if req_id.startswith(id) and (req_id == id or req_id[len(id)] == "."):
                    selected_reqs.append(req)
                    add = True
                    break
            if add:
                break
    return selected_reqs


def compute_req_acc(method, dataset):
    label = json.load(open(f"data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
    changed_label_ids = json.load(open(f"data/change.json", "r", encoding="utf-8"))[dataset]

    expect = json.load(open(f"{method}/{dataset}_upd_scenario.json", "r", encoding="utf-8"))
    changed_rule_ids = json.load(open(f"{method}/{dataset}_change.json", "r", encoding="utf-8"))
    
    expect = [e for ei in expect for e in ei]
    expect = select_changed_requirements(expect, changed_rule_ids)  # select changed reqs based on changed rule
    label = [l for li in label for l in li]
    label = select_changed_requirements(label, changed_label_ids)
    
    precision_cover, recall_cover = [0 for _ in range(len(expect))], [0 for _ in range(len(label))]

    for i, e in enumerate(expect):
        for l in label:
            if requirement_same(e, l):
                precision_cover[i] = 1
                break
    for i, l in enumerate(label):
        for e in expect:
            if requirement_same(e, l):
                recall_cover[i] = 1
                break


    precision = sum(precision_cover) / len(expect)
    recall = sum(recall_cover) / len(recall_cover)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1


def select_changed_scenario(expect, changed_rule_ids):
    selected_scenario = []
    for scenario in expect:
        contain_changed_req = False
        for r in scenario:
            add = False
            for id in r['rule'].split(","):
                for rule_id in changed_rule_ids:
                    if id.startswith(rule_id) and (id == rule_id or id[len(rule_id)] == "."):
                        contain_changed_req = True
                        add = True
                        break
                if add:
                    break
            if contain_changed_req:
                break
        if contain_changed_req:
            selected_scenario.append(scenario)
    return selected_scenario

def scenario_same(s1, s2):
    if len(s1) != len(s2):
        return False
    cover = [False for _ in range(len(s1))]
    for i, r1 in enumerate(s1):
        for r2 in s2:
            if requirement_same(r1, r2):
                cover[i] = True
                break
    return all(cover)


def compute_sce_acc(method, dataset):
    label = json.load(open(f"data/{dataset}_upd_linked_scenario.json", "r", encoding="utf-8"))
    changed_label_ids = json.load(open(f"data/change.json", "r", encoding="utf-8"))[dataset]

    expect = json.load(open(f"{method}/{dataset}_upd_scenario.json", "r", encoding="utf-8"))
    changed_rule_ids = json.load(open(f"{method}/{dataset}_change.json", "r", encoding="utf-8"))
    
    expect = select_changed_scenario(expect, changed_rule_ids)  # select changed reqs based on changed rule
    label = select_changed_scenario(label, changed_label_ids)
    precision_cover, recall_cover = [0 for _ in range(len(expect))], [0 for _ in range(len(label))]
    
    for i, e in enumerate(expect):
        for l in label:
            if scenario_same(e, l):
                precision_cover[i] = 1
                break
    for i, l in enumerate(label):
        for e in expect:
            if scenario_same(e, l):
                recall_cover[i] = 1
                break

    precision_cover = [p if p != -1 else 0 for p in precision_cover]
    precision = sum(precision_cover) / len(expect)
    recall = sum(recall_cover) / len(recall_cover)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", type=str)
    parser.add_argument("--dataset", type=str)
    args = parser.parse_args()
    dataset, method = args.dataset, args.method
    rule_precision, rule_recall, rule_f1 = compute_rule_acc(method, dataset)
    if method in ["ours", "no_change_impact_analysis"]:
        req_precision, req_recall, req_f1 = compute_req_acc(method, dataset)
        sce_precision, sce_recall, sce_f1 = compute_sce_acc(method, dataset)
        json.dump({
            "rule_pre": rule_precision,
            "rule_rec": rule_recall,
            "rule_f1": rule_f1,
            "req_pre": req_precision,
            "req_rec": req_recall,
            "req_f1": req_f1,
            "sce_pre": sce_precision,
            "sce_rec": sce_recall,
            "sce_f1": sce_f1
        }, open(f"log/{method}_chain_{dataset}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    else:
        json.dump({
            "rule_pre": rule_precision,
            "rule_rec": rule_recall,
            "rule_f1": rule_f1
        }, open(f"log/{method}_chain_{dataset}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)