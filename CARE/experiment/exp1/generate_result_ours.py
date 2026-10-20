import json
import os
import time
from reuse.update_testcase import update_testcase


if __name__ == "__main__":
    for i in range(1, 7):
        # if i != 3:
        #     continue
        ini_file = f"dataset{i}_ini_rule.txt" if f"dataset{i}_ini_rule.txt" in os.listdir("data") else f"dataset{i}_ini_rule.pdf"
        upd_file = f"dataset{i}_upd_rule.txt" if f"dataset{i}_upd_rule.txt" in os.listdir("data") else f"dataset{i}_upd_rule.pdf"
        print(f"Processing {upd_file}...")
        begin_time = time.time()
        new_testcases, change, new_scenario, rule_testcase_relation = update_testcase(f"data/{ini_file}", f"data/{ini_file.split('.')[0][:-5]}_testcase.json", f"data/{upd_file}", "../../model/trained/mengzi_rule_filtering", "../../model/trained/glm4_lora_exp", "../../reuse/domain_knowledge/classification_knowledge.json", "../../reuse/domain_knowledge/knowledge.json", skip_sc = True if any(item in ini_file for item in ["dataset1", "dataset2", "dataset6"]) else False)

        json.dump(new_testcases, open(f"ours_result/{ini_file.split('.')[0][:-9]}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(change, open(f"ours_result/{ini_file.split('_')[0]}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(new_scenario, open(f"ours_result/{ini_file.split('_')[0]}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(rule_testcase_relation, open(f"ours_result/{ini_file.split('_')[0]}_rule_testcase_relation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        print(f"{upd_file} finished in {time.time()-begin_time} seconds")
