import copy
from transfer.mydsl_to_rules import mydsl_to_rules, transfer_new_rule_format_to_old
import json
import re
from reuse.process_nl_to_sci import nl_to_sci
from reuse.process_sci_to_sco import sequence_classification
from reuse.process_sco_to_fi import select_rules
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r
from reuse.process_r1_to_r2 import process_r1_to_r2
from reuse.process_r2_to_r3 import process_r2_to_r3
from reuse.process_r3_to_testcase import is_time_key, is_num_key, is_price_key
import argparse
import random
import os
from sentence_transformers import SentenceTransformer
# model = SentenceTransformer('/home/asus/testcase-reuse/model/pretrained/paraphrase-multilingual-MiniLM-L12-v2')
model = None
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm


def is_id(str):
    # 判断一句话是否是id开头
    str = str.split(" ")[0].strip()
    if str == "":
        return False
    if str[0]=="第" and "条" in str:
        return True
    if str.isdigit():
        return True
    if "." not in str:
        return False
    ids = str.split(".")
    for id in ids:
        if not id.isdigit():
            return False
    return True

def get_rules(file, classification_knowledge_file, sc_model, skip_sc=True):
    # 寻找文件中的可测试规则
    classification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    if file.endswith(".txt"):
        input_data = open(file, "r", encoding="utf-8").read()
        first_line = input_data.strip().split("\n")[0]
        hybrid = is_id(first_line)
        sci, market_variety = nl_to_sci(nl_data=input_data, knowledge=classification_knowledge, hybrid=hybrid)
    else:
        sci, market_variety = nl_to_sci(nl_file=file, knowledge=classification_knowledge)
    if skip_sc:
        sco = sci
        for item in sco:
            item['type'] = "1"
    else:
        sco = sequence_classification(sci, sc_model)
    fi = select_rules(sco)
    return fi, market_variety, sco

def get_scenario(fi, market_variety, tc_model_path, classification_knowledge_file, other_knowledge_file, sco, api_key=None):
    """依据规则生成r3。第一个返回值是的r3，是字符串格式"""
    classification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    other_knowledge = json.load(open(other_knowledge_file, "r", encoding="utf-8"))

    fo = rule_formalization(fi, tc_model_path, api_key=api_key)
    r1 = to_r(fo, fix=True)
    r2 = process_r1_to_r2(r1, sco, market_variety, classification_knowledge)
    r3, _, _ = process_r2_to_r3(r2, other_knowledge)
    return r3


def cos_similarity(word1, word2, s = 1.0):
    word_embeddings = model.encode([word1, word2])
    similarity_matrix = cosine_similarity([word_embeddings[0]], [word_embeddings[1]])
    similarity = similarity_matrix[0][0]
    return similarity >= s




def judge_conflict(rule, testcase, s=None):
    """
    判断testcase是不是rule下的测试用例。
    首先看看rule和testcase的value是否能够匹配，要求必须完全相同
    """
    rule, testcase = copy.deepcopy(rule), copy.deepcopy(testcase)
    success = True
    if "结果" not in testcase or testcase['结果'] in ["不成功", "失败"]:
        success = False
    other_keys = ['测试关注点', 'testid', 'rule', '结果']
    rule_keys, rule_values = [], {}
    testcase_keys, testcase_values = [], {}
    
    if not success:  # 不考虑rule['results']中的状态和testcase中的结果状态
        rule['results'] = [r for r in rule['results'] if r['key'] != '状态']
        if "结果状态" in testcase:
            del testcase["结果状态"]
            index = 2
            while f"结果状态{index}" in testcase:
                del testcase[f"结果状态{index}"]
                index += 1
    for c in rule['constraints'] + rule['results']:
        if c['key'] in other_keys:  # 排除项
            continue
        cvalue = c['value']
        if cvalue[0] in ["不", "非"]:
            cvalue = cvalue[1:]
        if c['operation'] != "is":
            cvalue = c['operation'] + cvalue
            if cvalue[0] in ["不", "非"]:
                cvalue = cvalue[1:]
        if c['key'] not in rule_keys:  # 一般key
            rule_keys.append(c['key'])
            rule_values[c['key']] = [cvalue]
        else:
            rule_values[c['key']].append(cvalue)
    for k, v in testcase.items():
        # 简化k和v
        # k包含“操作2”这种表达，去掉尾部数字，但不能去掉中间数组
        k = re.sub(r"\d+$", "", k)
        # k包含“结果操作”这种表达，去掉结果
        if k.startswith("结果") and k != "结果":
            k = k[2:]

        # v包含“非接受”这种表达
        if v.startswith("非") or v.startswith("不"):
            v = v[1:]

        if k in other_keys:
            continue
        if k not in testcase_keys:
            testcase_keys.append(k)
            testcase_values[k] = [v]
        else:
            testcase_values[k].append(v)
    
    
    testcase_values_val = []
    for k in testcase_keys:
        testcase_values_val.extend(testcase_values[k])
    rule_values_val = []
    for k in rule_values:
        rule_values_val.extend(rule_values[k])
    all_cover = [False for _ in range(len(testcase_values_val))]
    index = 0
    for i, key in enumerate(testcase_keys):
        values = testcase_values[key]
        for j, value in enumerate(values):
            for k in rule_keys:
                if s != None and cos_similarity(k, value, s) or k == value:
                    all_cover[index] = True
                    break
                for v in rule_values[k]:
                    if s != None and cos_similarity(v, value, s) or v == value:
                        all_cover[index] = True
                        break
                if all_cover[index]:
                    break
            
            if not all_cover[index]:
                for k in rule_keys:
                    if k == key and \
                        (
                            is_time_key(k) and re.findall(r"\d+:\d+", value) != [] and any([re.findall(r"\d+:\d+", vv) != [] for vv in rule_values[k]])
                            or 
                            (is_price_key(k) or is_num_key(k)) and is_number(value) and any([contain_number(v) for v in rule_values[k]])
                        ):
                        all_cover[index] = True
                        break
            index += 1

    return len(all_cover) > 0 and sum(all_cover) / len(all_cover) > 0.99 or False




def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def contain_number(s):
    return re.findall(r"\d+\.\d+|\d+", s) != []

def relation_mining(scenarios, testcases, s=None):
    """
    发现scenario和testcase之间的对应关系

    scenario: 
    rule 2.2.1.1.1.1.1
    sourceId 2.2.1
    focus: 订单连续性操作
    before: ['3.2.3.1.1.1.1.1']
    after: ['3.2.3.1.1.1.3.1', '3.2.3.1.1.1.3.2', '3.2.3.1.1.1.4.1', '3.2.3.1.1.1.4.2', '4.2.5.2.1.1.1.1', '4.2.5.2.1.1.1.2', '4.2.5.2.1.1.3.1', '4.2.5.2.1.1.3.2']
        if 操作人 is '主做市商' and 交易品种 is '基准做市品种' and 操作部分 is '持续做市业务' and 交易市场 is '深圳证券交易所' and 交易方式 is '匹配成交' and 交易方向 is '买入' and 操作 is '申报' and 状态 is '未申报'
        then 结果 is '成功' and 状态 is '未成交'
    
    testcases:
    [
        [
            {
                "rule": "2.2.1.1.1.1.1",
                "测试关注点": "订单连续性操作",
                "testid": "2.2.1.1.1.1.1_1",
                "操作人": "主做市商",
                "交易品种": "基准做市品种",
                "操作部分": "持续做市业务",
                "交易市场": "深圳证券交易所",
                "交易方式": "匹配成交",
                "交易方向": "买入",
                "操作": "申报",
                "状态": "未申报",
                "结果状态": "未成交",
                "结果": "成功"
            },
            ...
        ],
        ...
    ]

    return: relation
    {
        'rule_id': ['testcase_id', ...],
        ...
    }
    """
    if isinstance(scenarios, str):
        rules = mydsl_to_rules(scenarios)
        scenarios = rules
    if isinstance(scenarios, list):
        rules = transfer_new_rule_format_to_old(scenarios)
    else:  # dict
        rules = scenarios
    # rules = {
    #   '4.1.1.1': {'constraints': [
    #                   {'key': '交易方式', 'operation': 'is', 'value': '竞买成交'},
    #                   {'key': '操作', 'operation': 'is', 'value': '竞买预约申报'},
    #                   {'key': '中标方式', 'operation': 'is', 'value': '单一主体中标'}
    #               ],
    #            'results': [{'else': '未申报', 'key': '交易结果', 'value': '已申报'}], 
    #            'focus': ['订单连续性操作'],
    #            'rule_class': '4.1.1'},
    # }
    
    if len(testcases) > 0 and isinstance(testcases[0], list):
        testcases = [item for sublist in testcases for item in sublist]
    
    relation = {}  # scenario_id: [testcase_id]
    
    
    
    
    for rule_id, rule in tqdm(rules.items()):
        source_ids = rule['rule_class']
        rule['rule'] = rule_id
        for testcase in testcases:
            testcase_id = testcase['testid']
            # 统计所有key在rule和testcase中的取值
            # 判断是否有关联
            is_related = judge_conflict(rule, testcase, s)
            if is_related:
                for source_id in source_ids:
                    if source_id in relation:
                        relation[source_id].append(testcase_id)
                    else:
                        relation[source_id] = [testcase_id]
    
    # 去重，因为可能将同一个测试用例多次匹配到同一个规则下的不同R规则
    for source_id in relation:
        relation[source_id] = list(set(relation[source_id]))
    
    return relation




def main(sc_model_path, tc_model_path, rule_file, testcase_file, output_file, classification_knowledge_file, other_knowledge_file):
    """
    给定文件和对应的测试用例，记录文件中的规则和测试用例的对应关系
    """
    if not os.path.exists(rule_file):
        raise FileNotFoundError(f"文件 {rule_file} 不存在")
    if not os.path.exists(testcase_file):
        raise FileNotFoundError(f"文件 {testcase_file} 不存在")
    
    # 生成测试场景
    tci, market_variety, sco = get_rules(rule_file, classification_knowledge_file, sc_model_path)
    # scenarios是一个字符串
    scenarios = get_scenario(tci, market_variety, tc_model_path, classification_knowledge_file, other_knowledge_file, sco)
    with open("cache/r3.mydsl", "w", encoding="utf-8") as f:
        f.write(scenarios)
    
    # scenarios = open("cache/r3.mydsl", "r", encoding="utf-8").read()
    testcases = json.load(open(testcase_file, "r", encoding="utf-8"))
    # 找到规则和测试用例的关系
    relation = relation_mining(scenarios, testcases)

    json.dump(relation, open(output_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)






if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule_file", type=str, default="./cache/深圳证券交易所交易规则（2021年3月修订）.pdf")
    parser.add_argument("--testcase_file", type=str, default="./cache/testcase.json")
    parser.add_argument("--tc_model_path", type=str, default="../model/trained/glm4_lora")
    parser.add_argument("--sc_model_path", type=str, default="../model/trained/mengzi_rule_filtering")
    parser.add_argument("--output_file", type=str, default="./cache/old_rule_testcase_relation.json")
    parser.add_argument("--classification_knowledge_file", type=str, default="../reuse/domain_knowledge/classification_knowledge.json")
    parser.add_argument("--other_knowledge_file", type=str, default="../reuse/domain_knowledge/knowledge.json")
    args = parser.parse_args()

    main(args.sc_model_path, args.tc_model_path, args.rule_file, args.testcase_file, args.output_file, args.classification_knowledge_file, args.other_knowledge_file)