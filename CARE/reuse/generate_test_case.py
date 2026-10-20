from reuse.process_nl_to_sci import nl_to_sci
from reuse.process_sci_to_sco import sequence_classification
from reuse.process_sco_to_fi import select_rules
from reuse.process_fi_to_fo import rule_formalization
from reuse.process_fo_to_r import to_r
from reuse.process_r1_to_r2 import process_r1_to_r2
from reuse.process_r2_to_r3 import process_r2_to_r3
from reuse.process_r3_to_testcase import process_r3_to_testcase
from reuse.rule_testcase_relation_mining import is_id
import json
import time
from reuse.generate_linked_scenario import generate_linked_scenario



def generate_test_case(sc_model, f_r1_model, classification_knowledge_file, knowledge_file, setting_file, nl_file, sci_file, sco_file, fi_file, fo_file, r1_file, r2_file, r3_file, testcase_file, skip_sc=False):
    start_time = time.time()
    mid_time = time.time()

    classification_knowledge = json.load(open(classification_knowledge_file, "r", encoding="utf-8"))
    knowledge = json.load(open(knowledge_file, "r", encoding="utf-8"))
    # convert natural language to sequence classification input
    if ".pdf" in nl_file:
        sci, market_variety = nl_to_sci(classification_knowledge, nl_file=nl_file)
    else:
        input_data = open(nl_file, "r", encoding="utf-8").read()
        first_line = input_data.strip().split("\n")[0]
        hybrid = is_id(first_line)
        sci, market_variety = nl_to_sci(classification_knowledge, nl_data=input_data, hybrid=hybrid)
    json.dump(sci, open(sci_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(market_variety, open(setting_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Load input file/data finished, time cost: ", time.time()-mid_time)
    mid_time = time.time()

    # sequence classification
    sci = json.load(open(sci_file, "r", encoding="utf-8"))
    if skip_sc:
        sco = sci
        for s in sco:
            s["type"] = "1"
    else:
        sco = sequence_classification(sci, sc_model)
    json.dump(sco, open(sco_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Sequence classification finished, time cost: ", time.time()-mid_time)
    mid_time = time.time()

    # select testable rules
    sco = json.load(open(sco_file, "r", encoding="utf-8"))
    fi = select_rules(sco)
    json.dump(fi, open(fi_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Select testable rules finished, time cost: ", time.time()-mid_time)
    mid_time = time.time()

    # token classification
    fi = json.load(open(fi_file, "r", encoding="utf-8"))
    fo = rule_formalization(fi, f_r1_model)
    json.dump(fo, open(fo_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Token classification finished, time cost: ", time.time()-mid_time)
    mid_time = time.time()

    # r1 generation
    fo = json.load(open(fo_file, "r", encoding="utf-8"))
    r1 = to_r(fo, fix=True)
    with open(r1_file, "w", encoding="utf-8") as f:
        f.write(r1)
    mid_time = time.time()

    # r2 generation
    r1 = open(r1_file, "r", encoding="utf-8").read()
    sco = json.load(open(sco_file, "r", encoding="utf-8"))
    setting = json.load(open(setting_file, "r", encoding="utf-8"))
    r2 = process_r1_to_r2(r1, sco, setting, classification_knowledge)
    with open(r2_file, "w", encoding="utf-8") as f:
        f.write(r2)
    print("R2 generation finished, time cost: ", time.time()-mid_time)
    mid_time = time.time()

    # r3 generation
    r2 = open(r2_file, "r", encoding="utf-8").read()
    r3, _, _ = process_r2_to_r3(r2, knowledge)
    with open(r3_file, "w", encoding="utf-8") as f:
        f.write(r3)
    print("R3 generation finished, time cost: ", time.time()-mid_time)
    linked_scenario = generate_linked_scenario(r3)
    json.dump(linked_scenario, open("cache/linked_scenario.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    mid_time = time.time()

    # testcase generation
    r3 = open(r3_file, "r", encoding="utf-8").read()
    testcase = process_r3_to_testcase(r3, generate_data=True)
    json.dump(testcase, open(testcase_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("Testcase generation finished, time cost: ", time.time()-mid_time)

    print("Total time cost: ", time.time()-start_time)




if __name__ == "__main__":
    nl_file="cache/深圳证券交易所交易规则（2021年3月修订）.pdf"
    # nl_file = "cache/input.txt"
    sci_file="cache/sci.json"
    sco_file="cache/sco.json"
    fi_file="cache/fi.json"
    fo_file="cache/fo.json"
    r1_file="cache/r1.mydsl"
    r2_file="cache/r2.mydsl"
    r3_file="cache/r3.mydsl"
    testcase_file = "cache/testcase.json"
    knowledge_file="../reuse/domain_knowledge/knowledge.json"
    classification_knowledge_file="../reuse/domain_knowledge/classification_knowledge.json"
    setting_file="cache/setting.json"

    sc_model="../model/trained/mengzi_rule_filtering"
    f_r1_model="../model/trained/glm4_lora"
    generate_test_case(sc_model, f_r1_model, classification_knowledge_file, knowledge_file, setting_file, nl_file, sci_file, sco_file, fi_file, fo_file, r1_file, r2_file, r3_file, testcase_file)
