import os
import torch
import json
import pickle
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r
from reuse.process_r3_to_testcase import process_r3_to_testcase
from reuse.rule_testcase_relation_mining import get_rules
from experiment.exp2.ESIM_model import ESIM
from experiment.exp2.ESIM_dataset import embedding_and_get_dataloader


# 1. 构建需求-用例关系，因为ESIM假设已经构建
# 2. 变更识别，使用ESIM模型
# 3. 用例更新，生成变更的测试用例


sc_model = "../../model/trained/mengzi_rule_filtering"
f_r1_model = "../../model/trained/glm4_lora_exp"
classification_knowledge_file = "../../reuse/domain_knowledge/classification_knowledge.json"
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
checkpoint = torch.load("../../model/pretrained/ESIM/best.pth.tar")
vocab_size = checkpoint["model"]["_word_embedding.weight"].size(0)
embedding_dim = checkpoint["model"]['_word_embedding.weight'].size(1)
hidden_size = checkpoint["model"]["_projection.0.weight"].size(0)
num_classes = checkpoint["model"]["_classification.4.weight"].size(0)
model = ESIM(vocab_size, embedding_dim, hidden_size, num_classes=num_classes, device=device)
model.load_state_dict(checkpoint["model"])
model.to(device)
model.eval()




def construct_relation(rules, testcases, idx):
    # rules: [{"id": "R1", "text": "需求1描述"}, ...]
    # testcases: [{"rule": "R1", "testid": "T1", ...}, ...]
    relation = {}
    for rule in rules:
        rule_id = rule['id']
        relation[rule_id] = []
        for testcase in testcases:
            test_rule_id = testcase['rule']
            if idx == 1 or idx == 6:
                test_rule_id = test_rule_id.split(".")[0]
            elif idx == 2:
                test_rule_id = ".".join(test_rule_id.split(".")[:2])
            elif idx == 4 or idx == 5:
                test_rule_id = ".".join(test_rule_id.split(".")[:3])
            elif idx == 3:
                test_rule_id = ".".join(test_rule_id.split(".")[:-2])
            if test_rule_id == rule_id:
                relation[rule_id].append(testcase['testid'])
    return relation


def change_identification(rules1, rules2):
    delete_rules = []
    add_rules = []
    batch_size = 32
    res = judge_same_ESIM(rules1, rules2, batch_size)

    for i, r1 in enumerate(rules1):
        found = False
        for j, r2 in enumerate(rules2):
            if res[i * len(rules2) + j] == 0:
                found = True
                break
        if not found:
            delete_rules.append(r1)
    for j, r2 in enumerate(rules2):
        found = False
        for i, r1 in enumerate(rules1):
            if res[i * len(rules2) + j] == 0:
                found = True
                break
        if not found:
            add_rules.append(r2)
    return delete_rules, add_rules


def update_testcases(testcases, delete_rules, add_rules, relation):
    updated_testcases = testcases.copy()
    delete_rule_ids = [r['id'] for r in delete_rules]
    add_rule_ids = [r['id'] for r in add_rules]
    for drid in delete_rule_ids:
        if drid in relation:
            for tid in relation[drid]:
                updated_testcases = [tc for tc in updated_testcases if tc['testid'] != tid]
    tcs = generate_tc(add_rules)
    tcs = [t for tc in tcs for t in tc]
    updated_testcases.extend(tcs)

    return updated_testcases


def generate_tc(rules):
    fo = rule_formalization(rules, f_r1_model)
    r1 = to_r(fo, fix=True)
    testcase = process_r3_to_testcase(r1, generate_data=True)
    return testcase




def judge_same_ESIM(rules1, rules2, batch_size):
    """
    要使用ESIM模型真是太麻烦了，我真的吐了
    1. clone它的项目
    2. 运行scripts/fetch_data.py，下载snli数据集和glove词向量，之所以下载snli是因为它的开源模型在这个数据集上训练的
    3. 运行scripts/preprocessing/preprocess_snli.py，生成词表worddict.pkl
    4. 加载模型，在全局变量中做了
    5. 加载数据生成dataloader
    6. 推理
    7. 刚发现这个模型是英文的，真是醉了，还要先翻译成英文
    """
    worddict = pickle.load(open("worddict.pkl", "rb"))
    dataloader = embedding_and_get_dataloader(worddict, rules1, rules2, batch_size)
    results = []
    with torch.no_grad():
        for batch in dataloader:
            # Move input and output data to the GPU if one is used.
            premises = batch["premise"].to(device)
            premises_lengths = batch["premise_length"].to(device)
            hypotheses = batch["hypothesis"].to(device)
            hypotheses_lengths = batch["hypothesis_length"].to(device)

            _, probs = model(premises,
                             premises_lengths,
                             hypotheses,
                             hypotheses_lengths)
            preds = torch.argmax(probs, dim=1).cpu().numpy()
            results.extend(preds.tolist())
    print(results)
    return results  # 0: entailment(蕴涵), 1: neutral(中性), 2: contradiction(冲突)






def generate_testcase_ESIM():
    for i in range(1, 7):
        ini_rule_file = f"data/dataset{i}_ini_rule.txt"
        upd_rule_file = f"data/dataset{i}_upd_rule.txt"
        if not os.path.exists(ini_rule_file):
            ini_rule_file = f"data/dataset{i}_ini_rule.pdf"
        if not os.path.exists(upd_rule_file):
            upd_rule_file = f"data/dataset{i}_upd_rule.pdf"
        ini_testcase = json.load(open(f"data/dataset{i}_ini_testcase.json", "r", encoding="utf-8"))
        ini_testcase = [ti for t in ini_testcase for ti in t]

        ini_rules, _, _ = get_rules(ini_rule_file, classification_knowledge_file, sc_model, skip_sc=True if i in [1,2,6] else False)
        upd_rules, _, _ = get_rules(upd_rule_file, classification_knowledge_file, sc_model, skip_sc=True if i in [1,2,6] else False)
        relation = construct_relation(ini_rules, ini_testcase, i)
        delete_rules, add_rules = change_identification(ini_rules, upd_rules)
        # json.dump(delete_rules, open(f"ESIM/dataset{i}_delete_rules.json", "w", encoding="utf-8"), indent=4, ensure_ascii=False)
        # json.dump(add_rules, open(f"ESIM/dataset{i}_add_rules.json", "w", encoding="utf-8"), indent=4, ensure_ascii=False)
        updated_testcases = update_testcases(ini_testcase, delete_rules, add_rules, relation)
        json.dump(updated_testcases, open(f"ESIM/dataset{i}_upd_testcase_ESIM.json", "w", encoding="utf-8"), indent=4, ensure_ascii=False)



if __name__ == "__main__":
    generate_testcase_ESIM()