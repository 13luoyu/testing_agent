import matplotlib.pyplot as plt
import json
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

data_ours = {
    'requirement_generation': 95.82, 
    'scenario_synthesis': 95.48, 
    'rule_case_association': 0, 
    'change_identification': 0, 
    'change_impact_analysis': 0, 
    'testcase_generation': 0
}

data_all_llm = {
    'requirement_generation': 95.82, 
    'scenario_synthesis': 63.36, 
    'rule_case_association': 56.17, 
    'change_identification': 52.14, 
    'change_impact_analysis': 34.29, 
    'testcase_generation': 0
}

data_no_reflect = {
    'requirement_generation': 82.58, 
    'scenario_synthesis': 81.93, 
    'rule_case_association': 87.22, 
    'change_identification': 67.59, 
    'change_impact_analysis': 63.24, 
    'testcase_generation': 64.12
}


a, b, c, d = [], [], [], []
for i in range(1, 7):
    result = json.load(open(f"../exp1/log/rule_testcase_relation_acc.json", "r", encoding="utf-8"))
    a.append(result[i-1])
    result = json.load(open(f"log/ours_chain_dataset{i}.json", "r", encoding="utf-8"))
    b.append(result["sce_f1"])
    c.append(result["req_f1"])
    result = json.load(open(f"log/ours_dataset{i}.json", "r", encoding="utf-8"))
    d.append(result[f"dataset{i}"]["f1_testcase"])
data_ours["rule_case_association"] = np.mean([ai * 100 for ai in a])
data_ours["change_identification"] = np.mean([bi * 100 for bi in b])
data_ours["change_impact_analysis"] = np.mean([ci * 100 for ci in c])
data_ours["testcase_generation"] = np.mean([di * 100 for di in d])

a, b, c, d = [], [], [], []
for i in range(1, 7):
    result = json.load(open(f"log/all_llm_dataset{i}.json", "r", encoding="utf-8"))
    d.append(result[f"dataset{i}"]["f1_testcase"])
data_all_llm["testcase_generation"] = np.mean([di * 100 for di in d])




plt.figure(figsize=(8, 4))
# 画3个折线图
colors = ["#ff0e0e", '#1f77b4', '#2ca02c']
x = [1, 2, 3, 4, 5, 6]
linewidth, markersize = 3, 12
plt.plot(x, [data_ours["requirement_generation"], data_ours["scenario_synthesis"], data_ours["rule_case_association"], data_ours["change_identification"], data_ours["change_impact_analysis"], data_ours["testcase_generation"]], marker='o', color=colors[0], linewidth=linewidth, markersize=markersize, label='CARE')
plt.plot(x, [data_no_reflect["requirement_generation"], data_no_reflect["scenario_synthesis"], data_no_reflect["rule_case_association"], data_no_reflect["change_identification"], data_no_reflect["change_impact_analysis"], data_no_reflect["testcase_generation"]], marker='^', color=colors[2], linewidth=linewidth, markersize=markersize, label='w/o Self-Reflection')
plt.plot(x, [data_all_llm["requirement_generation"], data_all_llm["scenario_synthesis"], data_all_llm["rule_case_association"], data_all_llm["change_identification"], data_all_llm["change_impact_analysis"], data_all_llm["testcase_generation"]], marker='s', color=colors[1], linewidth=linewidth, markersize=markersize, label='w/o Algorithms')
plt.xticks([1,2,3,4,5,6], ["Req.", "Sce.", "Gra.", "C.R.", "A.S.", "U.TS."], fontsize=20)
plt.yticks(fontsize=20)
plt.ylabel('Average F1 (%)', fontsize=20)

plt.legend(fontsize=16, loc="lower left", frameon=True, edgecolor='black', framealpha=0.7)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig("fig/exp2_comp.pdf", dpi=300)
plt.savefig("fig/exp2_comp.png", dpi=300)