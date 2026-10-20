import os
import json
import random

# 将所有的数据按照9：1分成训练集和测试集
def integrate_file(in_file: str, train_file: str, validate_file: str):
    all_rules = json.load(open(in_file, "r", encoding="utf-8"))
    random.shuffle(all_rules)
    rule_num = len(all_rules)
    train_data, validate_data = all_rules[:int(rule_num/10*9)], all_rules[int(rule_num/10*9):]
    print(f"划分标注：训练集有数据{len(train_data)}条，验证集有数据{len(validate_data)}条。")
    json.dump(train_data, open(train_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(validate_data, open(validate_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)


if __name__ == "__main__":
    integrate_file("../data/data_for_LLM_decoder/formalization_data.json", "../data/data_for_LLM_decoder/formalization_train_data.json", "../data/data_for_LLM_decoder/formalization_validate_data.json")