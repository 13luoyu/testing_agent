import json
import os
import time
from reuse.update_testcase import update_testcase
import argparse

# nohup python generate_result_ours.py >log/run_generate_result_ours.log &

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str)
    args = parser.parse_args()
    models = [args.model]
    # models = []
    # models.extend(["../../model/trained/glm4_lora_exp"])
    # models.extend(["../../model/trained/llama3-instruct_lora_exp"])
    # models.extend(["../../model/trained/qwen2-instruct_lora_exp"])
    # models.extend(["../../model/trained/llama3.2-instruct-1b_lora_exp"])
    # models.extend(["../../model/trained/llama3.2-instruct-3b_lora_exp"])
    # models.extend(["../../model/trained/chatglm3_lora_exp"])
    # models.extend(["../../model/trained/qwen1.5_lora_exp"])
    for model in models:
        model_name = model.split('/')[-1].split('_')[0]
        all_files = [file for file in sorted(os.listdir(f"data/{model_name}_data")) if "rule" in file]
        for i in range(0, len(all_files), 2):
            ini_file = all_files[i]
            upd_file = all_files[i+1]
            if "dataset1_" not in ini_file and "dataset2_" not in ini_file and "dataset6_" not in ini_file and "dataset7_" not in ini_file and "dataset9_" not in ini_file and "dataset11_" not in ini_file and (("llama3-" in model or "qwen2" in model) and "11" in ini_file or "qwen1" in model and "6" in ini_file):
                continue
            print(f"Processing {upd_file}...")
            begin_time = time.time()
            new_testcases, change, new_scenario, _ = update_testcase(f"data/{model_name}_data/{ini_file}", f"data/{model_name}_data/{ini_file.split('.')[0][:-5]}_testcase.json", f"data/{model_name}_data/{upd_file}", "../../model/trained/mengzi_rule_filtering", model, "../../reuse/domain_knowledge/classification_knowledge.json", "../../reuse/domain_knowledge/knowledge.json", False)

            json.dump(new_testcases, open(f"ours_result/{model_name}/{ini_file.split('.')[0][:-9]}_upd_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
            json.dump(change, open(f"ours_result/{model_name}/{ini_file.split('_')[0]}_change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
            json.dump(new_scenario, open(f"ours_result/{model_name}/{ini_file.split('_')[0]}_upd_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
            print(f"{upd_file} {model_name} finished in {time.time()-begin_time} seconds")
