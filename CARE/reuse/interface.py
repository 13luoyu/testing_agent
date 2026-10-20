import copy

import wget
import os
import json
import traceback
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from reuse.process_nl_to_sci import nl_to_sci
from reuse.process_sci_to_sco import sequence_classification
from reuse.process_sco_to_fi import select_rules
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r
from reuse.process_r1_to_r2 import process_r1_to_r2
from process_r2_to_r3 import process_r2_to_r3
from process_r3_to_testcase import process_r3_to_testcase
from transfer.mydsl_to_rules import mydsl_to_rules, transfer_new_rule_format_to_old, transfer_old_rule_format_to_new
from transfer.rules_to_mydsl import rules_to_mydsl
from reuse.generate_linked_scenario import generate_linked_scenario
from reuse.rule_testcase_relation_mining import relation_mining, judge_conflict

app = Flask(__name__)
CORS(app, support_credentials=True)
# 上传目录
app.config['UPLOAD_FOLDER'] = './download_files'
classification_knowledge = json.load(open("../reuse/domain_knowledge/classification_knowledge.json"))
other_knowledge = json.load(open("../reuse/domain_knowledge/knowledge.json"))
sc_model_path = "../model/trained/mengzi_rule_filtering"
tc_model_path = "../model/trained/glm4_lora"
os.makedirs('./download_files', exist_ok=True)

log = open("interface.log", "w", encoding="utf-8")
def writelog(s):
    log.write(s + "\n")
    log.flush()


def Rrule_transfer(r):
    defines = {}
    rules = []
    rule = {}
    for line in r.split("\n"):
        line = line.strip()
        if line == "":
            continue
        if line.find("define") == 0:
            defines[line.split(" ")[1]] = line.split(" ")[3]
            continue
        if line.find("rule") == 0:
            if rule != {}:
                rules.append(rule)
                rule = {}
            rule['rule'] = line.split(" ")[1]
        elif line.find("sourceId") == 0:
            rule['sourceId'] = line.split(" ")[1]
        elif line.find("focus:") == 0:
            rule['focus'] = line.split(" ")[1]
        elif line.find("before:") == 0:
            print(line)
            rule['before'] = " ".join(line.split(" ")[1:]).split(",")
        elif line.find("after:") == 0:
            rule['after'] = " ".join(line.split(" ")[1:]).split(",")
        else:
            if "text" in rule:
                rule['text'] = rule['text'] + line + "\n"
            else:
                rule['text'] = line + "\n"
    if rule != {}:
        rules.append(rule)
    if defines != {}:
        data = {
            "define": defines,
            "rules": rules
        }
    else:
        data = rules
    return data

def Rrule_back(data):
    s = ""
    if isinstance(data, list):
        rules = data
        defines = {}
    else:
        rules = data['rules']
        defines = data['define']
    for key in list(defines.keys()):
        s += f"define {key} = {defines[key]}\n"
    if len(s)>0:
        s += "\n"
    for rule in rules:
        if "rule" in rule:
            s += f"rule {rule['rule']}\n"
        if "sourceId" in rule:
            s += f"sourceId {rule['sourceId']}\n"
        if "focus" in rule:
            s += f"focus: {rule['focus']}\n"
        if "before" in rule:
            s += f"before: {','.join(rule['before'])}\n"
        if "after" in rule:
            s += f"after: {','.join(rule['after'])}\n"
        if "text" in rule:
            for t in rule['text'].split("\n"):
                s += f"\t{t}\n"
        s += "\n"
    return s



@app.route('/')
def default():
    return 'CARE'

@app.route("/requirement_generation", methods=["POST"])
def requirement_generation():
    writelog(f"# requirement_generation, params: {request.json}")
    try:
        params = request.json
        fileType, fileData = params['fileType'], params['fileData']
        if fileType == "0":
            # 下载
            filepath = wget.download(fileData, app.config['UPLOAD_FOLDER'])
            filepath = filepath.replace("//", "/")
            os.rename(filepath, filepath.split("?")[0])
            filepath = filepath.split("?")[0]
            filepath = filepath.replace("//", "/")
            # 处理
            if not filepath.endswith(".pdf"):
                writelog(f"??? 文件格式错误，仅支持pdf文件，文件路径：{filepath}")
                return jsonify({"code": 400, "msg": "文件格式错误，仅支持pdf文件"})
            sci_data, market_variety = nl_to_sci(nl_file=filepath, knowledge=classification_knowledge)
        elif fileType == "1":
            sci_data, market_variety = nl_to_sci(nl_data=fileData, knowledge=classification_knowledge)
        else:
            writelog(f"??? 文件类型错误，仅支持0和1，文件类型：{fileType}")
            return jsonify({"code": 400, "msg": "文件类型错误，仅支持0和1"})
        
        writelog(f"### market_variety：{market_variety}")
        writelog(f"### sci_data：{sci_data}")

        # 规则筛选
        sco_data = sequence_classification(sci_data, sc_model_path)
        writelog(f"### sco_data：{sco_data}")
        sco = copy.deepcopy(sco_data)

        fi = select_rules(sco_data)

        # 结构化需求生成
        fo = rule_formalization(fi, tc_model_path)
        writelog(f"### fo：{fo}")
        # fo[i]: {"id": ..., "text": ..., "type": ..., "prediction": ...}

        r1 = to_r(fo, fix=True)
        writelog(f"### r1：{r1}")
        r1_json = Rrule_transfer(r1)
        rules = []
        for item in fo:
            rule = {
                "id": item['id'],
                "text": item['text']
            }
            rules.append(rule)

        return jsonify({"code": 200, "msg": "需求生成成功", "data": {"rules": rules, "requirements": r1_json, "sco": sco, "market_variety": market_variety}})
    except Exception as e:
        writelog(f"??? 需求生成失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "需求生成失败，异常信息：" + traceback.format_exc()})
    


@app.route("/scenario_generation", methods=["POST"])
def scenario_generation():
    writelog(f"# scenario_generation, params: {request.json}")
    try:
        params = request.json
        r1_json = params["requirements"]
        sco = params["sco"]
        market_variety = params["market_variety"]
        r1 = Rrule_back(r1_json)
        writelog(f"### requirements：{r1}")
        writelog(f"### sco：{sco}")
        writelog(f"### market_variety：{market_variety}")

        r2 = process_r1_to_r2(r1, sco, market_variety, classification_knowledge)
        writelog(f"### r2：{r2}")

        r3, _, _ = process_r2_to_r3(r2, other_knowledge)
        writelog(f"### r3：{r3}")
        r3_json = Rrule_transfer(r3)
        return jsonify({"code": 200, "msg": "场景生成成功", "data": {"scenarios": r3_json}})
        # linked_scenario = generate_linked_scenario(r3)
        # writelog(f"### linked_scenario：{linked_scenario}")

        # return jsonify({"code": 200, "msg": "场景生成成功", "data": {"scenarios": r3, "scenarios_json": linked_scenario}})
    
    except Exception as e:
        writelog(f"??? 场景生成失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "场景生成失败，异常信息：" + traceback.format_exc()})


@app.route("/testcase_align", methods=["POST"])
def testcase_align():
    writelog(f"# testcase_align, params: {request.json}")
    try:
        params = request.json
        old_rules_json = params["scenarios"]
        old_testcases = params["testcases"]
        old_rules_str = Rrule_back(old_rules_json)
        writelog(f"### old_rules_str：{old_rules_str}")

        old_rules = transfer_new_rule_format_to_old(mydsl_to_rules(old_rules_str))

        old_relation = relation_mining(old_rules, old_testcases)
        writelog(f"### old_relation：{old_relation}")

        return jsonify({"code": 200, "msg": "测试用例对齐成功", "data": {"relation": old_relation}})
    
    except Exception as e:
        writelog(f"??? 测试用例对齐失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "测试用例对齐失败，异常信息：" + traceback.format_exc()})



@app.route("/change_identify", methods=["POST"])
def change_identify():
    writelog(f"# change_identify, params: {request.json}")
    try:
        params = request.json
        old_texts = params["old_texts"]
        new_texts = params["new_texts"]

        old_rules_json, new_rules_json = params["old_scenarios"], params["new_scenarios"]
        old_rules_str = Rrule_back(old_rules_json)
        new_rules_str = Rrule_back(new_rules_json)
        old_rules = transfer_new_rule_format_to_old(mydsl_to_rules(old_rules_str))
        new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules_str))

        to_delete_rules, to_add_rules = [], []
        old_map, new_map = {}, {}

        for old_text in old_texts:
            # 找到old_text对应的所有rule
            old_text_id = old_text['id']
            old_rules_i = []
            for rule_id in old_rules:
                ids = old_rules[rule_id]["rule_class"]
                if old_text_id in ids:
                    old_rules_i.append(rule_id)
            old_map[old_text_id] = old_rules_i
        for new_text in new_texts:
            # 找到new_text对应的所有rule
            new_text_id = new_text['id']
            new_rules_i = []
            for rule_id in new_rules:
                ids = new_rules[rule_id]["rule_class"]
                if new_text_id in ids:
                    new_rules_i.append(rule_id)
            new_map[new_text_id] = new_rules_i

        for old_text_id in old_map:
            find_old = False
            for new_text_id in new_map:
                if len(old_map[old_text_id]) != len(new_map[new_text_id]):
                    continue
                find = [False for _ in range(len(old_map[old_text_id]))]
                for i, old_rule_id in enumerate(old_map[old_text_id]):
                    for new_rule_id in new_map[new_text_id]:
                        if old_rules[old_rule_id]["constraints"] == new_rules[new_rule_id]["constraints"] and old_rules[old_rule_id]["results"] == new_rules[new_rule_id]["results"]:
                            find[i] = True
                            break
                if all(find):
                    find_old = True
                    break
            if not find_old:
                for old_text in old_texts:
                    if old_text['id'] == old_text_id:
                        to_delete_rules.append(old_text)
        

        for new_text_id in new_map:
            find_new = False
            for old_text_id in old_map:
                if len(old_map[old_text_id]) != len(new_map[new_text_id]):
                    continue
                find = [False for _ in range(len(new_map[new_text_id]))]
                for i, new_rule_id in enumerate(new_map[new_text_id]):
                    for old_rule_id in old_map[old_text_id]:
                        if old_rules[old_rule_id]["constraints"] == new_rules[new_rule_id]["constraints"] and old_rules[old_rule_id]["results"] == new_rules[new_rule_id]["results"]:
                            find[i] = True
                            break
                if all(find):
                    find_new = True
                    break
            if not find_new:
                for new_text in new_texts:
                    if new_text['id'] == new_text_id:
                        to_add_rules.append(new_text)
        
        return jsonify({"code": 200, "msg": "变更规则识别成功", "data": {"to_delete_rules": to_delete_rules, "to_add_rules": to_add_rules, "new_map": new_map}})
    
    except Exception as e:
        writelog(f"??? 变更规则识别失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "变更规则识别失败，异常信息：" + traceback.format_exc()})



@app.route("/impact_analysis", methods=["POST"])
def impact_analysis():
    writelog(f"# impact_analysis, params: {request.json}")
    try:
        params = request.json
        old_rules_json = params["old_scenarios"]
        old_rules_str = Rrule_back(old_rules_json)
        to_delete_rules = params["to_delete_rules"]
        old_relation = params["old_relation"]

        all_to_delete_linked_scenario = []
        linked_scenario = generate_linked_scenario(old_rules_str)
        for to_delete_rule in to_delete_rules:
            for linked_scenario1 in linked_scenario:
                for rule in linked_scenario1:
                    if linked_scenario1 not in all_to_delete_linked_scenario and any([tc.startswith(to_delete_rule['id']) and (tc == to_delete_rule['id'] or tc[len(to_delete_rule['id'])] == ".") for tc in rule['rule'].split(",")]):
                        all_to_delete_linked_scenario.append(linked_scenario1)
                        break
        writelog(f"受影响的需求场景数：{len(all_to_delete_linked_scenario)}")
        
        to_del_index = []
        for to_delete_rule in to_delete_rules:
            id = to_delete_rule['id']
            if id not in old_relation:
                to_del_index.append(to_delete_rule)
        for to_delete_rule in to_del_index:
            to_delete_rules.remove(to_delete_rule)

        all_to_delete_testcases = []
        for to_delete_rule in to_delete_rules:
            for tcs in old_relation[to_delete_rule['id']]:
                if tcs not in all_to_delete_testcases and any([tc.startswith(to_delete_rule['id']) and (tc == to_delete_rule['id'] or tc[len(to_delete_rule['id'])] == ".") for tc in tcs.split(",")]):
                    all_to_delete_testcases.append(tcs)
        writelog(f"受影响的测试用例数：{len(all_to_delete_testcases)}")

        to_delete_scenario = []
        for a in all_to_delete_linked_scenario:
            for b in a:
                if b['rule'] not in to_delete_scenario:
                    to_delete_scenario.append(b['rule'])

        return jsonify({"code": 200, "msg": "变更影响分析成功", "data": {"to_delete_scenarios": to_delete_scenario, "to_delete_testcases": all_to_delete_testcases}})
    
    except Exception as e:
        writelog(f"??? 变更影响分析失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "变更影响分析失败，异常信息：" + traceback.format_exc()})
    

@app.route("/testcase_update", methods=["POST"])
def testcase_update():
    writelog(f"# testcase_update, params: {request.json}")
    try:
        params = request.json
        
        new_texts = params["new_texts"]
        new_rules_json = params["new_scenarios"]
        new_rules_str = Rrule_back(new_rules_json)
        new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules_str))
        to_delete_rules = params["to_delete_rules"]
        to_add_rules = params["to_add_rules"]
        old_relation = params["old_relation"]
        old_testcases = params["old_testcases"]
        new_map = params["new_map"]
        new_sco = params["new_sco"]
        new_mv = params["new_market_variety"]

        # 删掉已经被修改/删除的规则对应的测试用例
        for to_delete_rule in to_delete_rules:
            # assert to_delete_rule['id'] in old_relation
            if to_delete_rule['id'] not in old_relation:
                continue
            for testid in old_relation[to_delete_rule['id']]:
                for old_testcase in old_testcases:
                    for old_testcase1 in old_testcase:
                        if old_testcase1['testid'] == testid:
                            old_testcase.remove(old_testcase1)
                            break
                    if len(old_testcase) == 0:
                        old_testcases.remove(old_testcase)

        # 更新剩余测试用例的testid和rule
        rule_used = copy.deepcopy(new_map)
        for new_text_id in new_map:
            rule_used[new_text_id] = [False for _ in range(len(new_map[new_text_id]))]

        for old_testcase in old_testcases:
            for new_text_id in new_map:
                for i, new_rule_id in enumerate(new_map[new_text_id]):
                    if rule_used[new_text_id][i]:
                        continue
                    new_rule = new_rules[new_rule_id]
                    find = [False for _ in range(len(old_testcase))]
                    # 观察old_testcase中的每个测试用例是否属于new_map[new_text_id][i]，如果是，则匹配成功
                    for j, old_testcase1 in enumerate(old_testcase):
                        is_related = judge_conflict(new_rule, old_testcase1)
                        if is_related:
                            find[j] = True
                    if all(find):
                        for old_testcase1 in old_testcase:
                            old_ruleid_len = len(old_testcase1['rule'])
                            old_testcase1['rule'] = new_map[new_text_id][i]
                            old_testcase1['testid'] = new_map[new_text_id][i] + old_testcase1['testid'][old_ruleid_len:]
                        rule_used[new_text_id][i] = True


        fo = rule_formalization(new_texts, tc_model_path)
        r1 = to_r(fo, fix=True)
        r2 = process_r1_to_r2(r1, new_sco, new_mv, classification_knowledge)
        r3, _, _ = process_r2_to_r3(r2, other_knowledge)
        new_rules = r3


        new_rules = transfer_new_rule_format_to_old(mydsl_to_rules(new_rules))
        new_scenarios = {}
        for to_add_rule in to_add_rules:
            to_add_rule_id = to_add_rule['id']
            for new_rule_id in new_rules:
                new_rule_id_parts = new_rule_id.split(",")
                for id in new_rule_id_parts:
                    if id.startswith(to_add_rule_id) and (id == to_add_rule_id or id[len(to_add_rule_id)] == "."):
                        new_scenarios[new_rule_id] = new_rules[new_rule_id]
                        break
        
        new_testcases = process_r3_to_testcase(rules_to_mydsl(transfer_old_rule_format_to_new(new_scenarios)))
        old_testcases.extend(new_testcases)
        
        return jsonify({"code": 200, "msg": "测试用例更新成功", "data": {"testcases": old_testcases}})
    except Exception as e:
        writelog(f"??? 测试用例更新失败，异常信息：{traceback.format_exc()}")
        return jsonify({"code": 500, "msg": "测试用例更新失败，异常信息：" + traceback.format_exc()})



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9092)