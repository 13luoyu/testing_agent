import json

res = [[] for _ in range(6)]
rec = [[] for _ in range(6)]
f1 = [[] for _ in range(6)]

for i in range(1, 7):
    result = json.load(open(f"ours_result/dataset{i}_rule_testcase_relation.json", "r", encoding="utf-8"))
    # {
    #     'rule_id': ['testcase_id', ...],
    #     ...
    # }

    for rule_id in result:
        testcase_list = result[rule_id]
        for testid in testcase_list:
            if len(testid) == len(rule_id) or testid.startswith(rule_id) and testid[len(rule_id)] in [".", "_"]:
                res[i-1].append(1)
            else:
                res[i-1].append(0)
    tc = json.load(open(f"data/dataset{i}_ini_testcase.json", "r", encoding="utf-8"))
    tc = [ti for t in tc for ti in t]
    for testcase in tc:
        testid = testcase['testid']
        find = False
        for key in result:
            if testid in result[key]:
                find = True
                rec[i-1].append(1)
                break
        if not find:
            rec[i-1].append(0)
    
    res[i-1] = sum(res[i-1]) / len(res[i-1]) if len(res[i-1]) > 0 else 0
    rec[i-1] = sum(rec[i-1]) / len(rec[i-1]) if len(rec[i-1]) > 0 else 0
    f1[i-1] = (5 * res[i-1] + rec[i-1]) / 6 if (res[i-1] + rec[i-1]) > 0 else 0

json.dump(f1, open("log/rule_testcase_relation_acc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)