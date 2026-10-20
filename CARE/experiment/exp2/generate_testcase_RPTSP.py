import os
import torch
import json
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_distances
from sentence_transformers import SentenceTransformer
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r
from reuse.process_r3_to_testcase import process_r3_to_testcase
from reuse.rule_testcase_relation_mining import get_rules



sc_model = "../../model/trained/mengzi_rule_filtering"
f_r1_model = "../../model/trained/glm4_lora_exp"
classification_knowledge_file = "../../reuse/domain_knowledge/classification_knowledge.json"

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

def K_means_similarity(old_texts, new_texts):
    distance_threshold = 0.25
    model = SentenceTransformer("../../model/pretrained/paraphrase-multilingual-MiniLM-L12-v2")
    
    old_rules = [item['text'] for item in old_texts]
    old_rule_embeddings = model.encode(old_rules, normalize_embeddings=True)
    
    k = len(old_rules)
    kmeans = KMeans(n_clusters=k, random_state=33)
    labels = kmeans.fit_predict(old_rule_embeddings)
    
    new_rules = [item['text'] for item in new_texts]
    new_result = []  # 如果为True则表示新规则与旧规则相似，否则不相似

    for rule in new_rules:
        # 新规则向量
        rule_embedding = model.encode([rule], normalize_embeddings=True)

        # 找到所属簇
        cluster_id = kmeans.predict(rule_embedding)[0]
        cluster_center = kmeans.cluster_centers_[cluster_id]

        # 计算与簇中心的距离
        center_distance = cosine_distances(rule_embedding, cluster_center.reshape(1, -1))[0][0]

        # 在该簇中找到最相似的旧规则
        cluster_indices = np.where(kmeans.labels_ == cluster_id)[0]
        cluster_embeddings = old_rule_embeddings[cluster_indices]
        if len(cluster_embeddings) == 0:
            new_result.append(False)
            continue
        distances = cosine_distances(rule_embedding, cluster_embeddings)[0]
        min_distance = distances.min()
        closest_rule = old_rules[cluster_indices[distances.argmin()]]

        new_result.append(min_distance < distance_threshold)

    old_result = []  # 如果为True则表示旧规则与新规则相似，否则不相似
    new_rule_embeddings = model.encode(new_rules, normalize_embeddings=True)
    k = len(new_rules)
    kmeans = KMeans(n_clusters=k, random_state=33)
    labels = kmeans.fit_predict(new_rule_embeddings)

    for rule in old_rules:
        # 旧规则向量
        rule_embedding = model.encode([rule], normalize_embeddings=True)

        # 找到所属簇
        cluster_id = kmeans.predict(rule_embedding)[0]
        cluster_center = kmeans.cluster_centers_[cluster_id]

        # 计算与簇中心的距离
        center_distance = cosine_distances(rule_embedding, cluster_center.reshape(1, -1))[0][0]

        # 在该簇中找到最相似的新规则
        cluster_indices = np.where(kmeans.labels_ == cluster_id)[0]
        cluster_embeddings = new_rule_embeddings[cluster_indices]
        if len(cluster_embeddings) == 0:
            old_result.append(False)
            continue
        distances = cosine_distances(rule_embedding, cluster_embeddings)[0]
        min_distance = distances.min()
        closest_rule = new_rules[cluster_indices[distances.argmin()]]

        old_result.append(min_distance < distance_threshold)
    
    add_rules, del_rules = [], []
    for i, val in enumerate(new_result):
        if not val:
            add_rules.append(new_texts[i])
    for i, val in enumerate(old_result):
        if not val:
            del_rules.append(old_texts[i])
    return del_rules, add_rules



def update_testcases(testcases, delete_rules, add_rules, relation):
    updated_testcases = testcases.copy()
    delete_rule_ids = [r['id'] for r in delete_rules]
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




def generate_testcase_RPTSP():
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
        delete_rules, add_rules = K_means_similarity(ini_rules, upd_rules)
        updated_testcases = update_testcases(ini_testcase, delete_rules, add_rules, relation)
        # json.dump(delete_rules, open(f"RPTSP/dataset{i}_delete_rules.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        # json.dump(add_rules, open(f"RPTSP/dataset{i}_add_rules.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        json.dump(updated_testcases, open(f"RPTSP/dataset{i}_updated_testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)


if __name__ == "__main__":
    generate_testcase_RPTSP()