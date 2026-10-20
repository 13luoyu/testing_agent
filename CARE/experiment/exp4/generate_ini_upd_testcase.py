from reuse.generate_test_case import generate_test_case
import os
import json


def generate_testcase_for_data(model):
    model_name = model.split('/')[-1].split('_')[0]
    for file in sorted(os.listdir(f"data/{model_name}_data")):
        if "rule" not in file:
            continue
        if "dataset6" not in file and "dataset7" not in file and "dataset9" not in file and "dataset11" not in file:
            continue

        print(f"开始处理 {file}")
        generate_test_case("../../model/trained/mengzi_rule_filtering", model, "../../reuse/domain_knowledge/classification_knowledge.json", "../../reuse/domain_knowledge/knowledge.json", "cache/setting.json", f"data/{model_name}_data/{file}", "cache/sci.json", "cache/sco.json", "cache/fi.json", "cache/fo.json", "cache/r1.mydsl", "cache/r2.mydsl", "cache/r3.mydsl", "cache/testcase.json")

        testcases = json.load(open("cache/testcase.json", "r", encoding="utf-8"))
        json.dump(testcases, open(f"data/{model_name}_data/{file.split('.')[0][:-5]}_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        fi = json.load(open("cache/fi.json", "r", encoding="utf-8"))
        testcases = [t for tc in testcases for t in tc]

        linked_scenario = json.load(open("cache/linked_scenario.json", "r", encoding="utf-8"))
        json.dump(linked_scenario, open(f"data/{model_name}_data/{file.split('.')[0][:-5]}_linked_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)

        print(f"{model_name}处理完成{file}，包含{len(fi)}条规则，{len(testcases)}条测试用例")



if __name__ == "__main__":
    # generate_testcase_for_data("../../model/trained/glm4_lora_exp")
    # generate_testcase_for_data("../../model/trained/llama3-instruct_lora_exp")
    generate_testcase_for_data("../../model/trained/internlm2_lora_exp")

    # generate_testcase_for_data("../../model/trained/qwen2-instruct_lora_exp")
    # generate_testcase_for_data("../../model/trained/llama3.2-instruct-1b_lora_exp")
    # generate_testcase_for_data("../../model/trained/llama3.2-instruct-3b_lora_exp")
    
    # generate_testcase_for_data("../../model/trained/chatglm3_lora_exp")  # transformers  4.43.1 -> 4.40.0
    # generate_testcase_for_data("../../model/trained/qwen1.5_lora_exp")