import json
import random
random.seed(33)

k = 0.1

for i in range(1, 6):
    ini = json.load(open(f"dataset{i}_ini_linked_scenario.json", "r", encoding="utf-8"))
    upd = json.load(open(f"dataset{i}_upd_linked_scenario.json", "r", encoding="utf-8"))


    # 随机删除0.05
    num = len(upd)
    del_num = int(num * k)
    del_indices = random.sample(range(num), del_num)
    upd_after_del = []
    del_rule_id = []
    for idx, item in enumerate(upd):
        if idx in del_indices:
            for t in item:
                del_rule_id.append(t['rule'])
        else:
            upd_after_del.append(item)

    # 随机加入0.05
    add_num = del_num
    add_indices = random.sample(range(len(ini)), add_num)
    upd_after_add = upd_after_del.copy()
    add_rule_id = []
    for idx in add_indices:
        upd_after_add.append(ini[idx])
        for t in ini[idx]:
            add_rule_id.append(t['rule'])

    with open(f"dataset{i}_upd_linked_scenario.json", "w", encoding="utf-8") as f:
        json.dump(upd_after_add, f, ensure_ascii=False, indent=4)
    

    ini = json.load(open(f"dataset{i}_ini_testcase.json", "r", encoding="utf-8"))
    upd = json.load(open(f"dataset{i}_upd_testcase.json", "r", encoding="utf-8"))
    upd_after_del = []
    for item in upd:
        conflict = False
        for t in item:
            if t['rule'] in del_rule_id:
                conflict = True
                break
        if not conflict:
            upd_after_del.append(item)
    
    upd_after_add = upd_after_del.copy()
    for item in ini:
        for t in item:
            if t['rule'] in add_rule_id:
                upd_after_add.append(item)
                break
    
    with open(f"dataset{i}_upd_testcase.json", "w", encoding="utf-8") as f:
        json.dump(upd_after_add, f, ensure_ascii=False, indent=4)