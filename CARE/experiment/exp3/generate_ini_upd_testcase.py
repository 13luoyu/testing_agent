from reuse.generate_test_case import generate_test_case
import os
import json


def generate_testcase_for_data():
    for file in sorted(os.listdir("data")):
        if "rule" not in file:
            continue

        print(f"开始处理 {file}")
        generate_test_case("qwen3_service_api", "../../model/trained/glm4_lora_exp", "../../reuse/domain_knowledge/classification_knowledge.json", "../../reuse/domain_knowledge/knowledge.json", "cache/setting.json", f"data/{file}", "cache/sci.json", "cache/sco.json", "cache/fi.json", "cache/fo.json", "cache/r1.mydsl", "cache/r2.mydsl", "cache/r3.mydsl", "cache/testcase.json", skip_sc=False)

        testcases = json.load(open("cache/testcase.json", "r", encoding="utf-8"))
        json.dump(testcases, open(f"data/{file.split('.')[0][:-5]}_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        linked_scenario = json.load(open("cache/linked_scenario.json", "r", encoding="utf-8"))
        json.dump(linked_scenario, open(f"data/{file.split('.')[0][:-5]}_linked_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        fi = json.load(open("cache/fi.json", "r", encoding="utf-8"))
        testcases = [t for tc in testcases for t in tc]

        print(f"处理完成{file}，包含{len(fi)}条规则，{len(linked_scenario)}个需求场景，{len(testcases)}条测试用例")





if __name__ == "__main__":
    generate_testcase_for_data()