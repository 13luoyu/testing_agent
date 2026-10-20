# 依赖关系：
# 需求生成 -> 场景合成 -> 规则-用例关联
#                -> 变更识别          -> 变更影响分析 -> 变更用例生成


import matplotlib.pyplot as plt
import json
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

data1 = {
    "requirement_generation": [92, 94.1, 97.4, 98.2, 96.7, 96.5],
    "scenario_synthesis": [91.6, 97.2, 97.0, 98.0, 95.2, 93.9],
    "rule_case_association": 0,
    "change_identification": 0,
    "change_impact_analysis": 0,
    "testcase_generation": 0
}


a, b, c, d = [], [], [], []

result0 = json.load(open(f"../exp1/log/rule_testcase_relation_acc.json", "r", encoding="utf-8"))
for i in range(1, 7):
    a.append(result0[i-1])
    result = json.load(open(f"log/ours_chain_dataset{i}.json", "r", encoding="utf-8"))
    b.append(result["sce_f1"])
    c.append(result["req_f1"])
    result = json.load(open(f"log/ours_dataset{i}.json", "r", encoding="utf-8"))
    d.append(result[f"dataset{i}"]["f1_testcase"])


data1["rule_case_association"] = [ai * 100 for ai in a]
data1["change_identification"] = [bi * 100 for bi in b]
data1["change_impact_analysis"] = [ci * 100 for ci in c]
data1["testcase_generation"] = [di * 100 for di in d]

# data = {
#     "requirement_generation": np.median(data1["requirement_generation"]),
#     "scenario_synthesis": np.median(data1["scenario_synthesis"]),
#     "rule_case_association": np.median(data1["rule_case_association"]),
#     "change_identification": np.median(data1["change_identification"]),
#     "change_impact_analysis": np.median(data1["change_impact_analysis"]),
#     "testcase_generation": np.median(data1["testcase_generation"]),
# }

data = {
    "requirement_generation": np.mean(data1["requirement_generation"]),
    "scenario_synthesis": np.mean(data1["scenario_synthesis"]),
    "rule_case_association": np.mean(data1["rule_case_association"]),
    "change_identification": np.mean(data1["change_identification"]),
    "change_impact_analysis": np.mean(data1["change_impact_analysis"]),
    "testcase_generation": np.mean(data1["testcase_generation"]),
}



plt.figure(figsize=(8, 4))
colors = ['#AED6F1', "#E0FAD8", "#ff0e0e"] 
# 画箱线图
positions, plot_data = [], []
for i, key in enumerate(data1.keys()):
    positions.append(i + 1)
    plot_data.append(data1[key])
bp = plt.boxplot(
    plot_data,
    positions=positions,
    widths=0.6,
    patch_artist=True,
    boxprops=dict(facecolor='white', color='black'),
    medianprops=dict(color='black', linewidth=2),
    whiskerprops=dict(color='black'),
    capprops=dict(color='black'),
    flierprops=dict(marker='o', color='black', markersize=6)
)
for i, patch in enumerate(bp['boxes']):
    if i < 3:
        patch.set_facecolor(colors[0])
    else:
        patch.set_facecolor(colors[1])

# 画一个折线图，两条折线
x1 = [1, 2, 3, 5]
x2 = [1, 4, 5, 6]
y1 = [data["requirement_generation"], data["scenario_synthesis"], data["rule_case_association"], data["change_impact_analysis"]]
y2 = [data["requirement_generation"], data["change_identification"], data["change_impact_analysis"], data["testcase_generation"]]
plt.text(0.7, 97.4, round(data["requirement_generation"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
plt.text(1.7, 97.2, round(data["scenario_synthesis"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
plt.text(3.27, 97.9, round(data["rule_case_association"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
plt.text(4, 90, round(data["change_identification"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
plt.text(5, 89.9, round(data["change_impact_analysis"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
plt.text(6, 88, round(data["testcase_generation"], 1), fontsize=16, ha='center', va='bottom', color=colors[2])
# plt.plot(x2, y2, marker='s', color='r', linewidth=2, markersize=8)
# plt.plot(x1, y1, marker='o', color="b", linewidth=2, markersize=8)
# plt.plot(x2[1:], y2[1:], marker='s', color='r', linewidth=2, markersize=8)
plt.plot([1,2,3,4,5,6], [data["requirement_generation"], data["scenario_synthesis"], data["rule_case_association"], data["change_identification"], data["change_impact_analysis"], data["testcase_generation"]], marker='o', color=colors[2], linewidth=2, markersize=10)
plt.xticks([1,2,3,4,5,6], ["Req.", "Sce.", "Gra.", "C.R.", "A.S.", "U.TS."], fontsize=20)
plt.yticks(fontsize=20)
plt.ylabel('F1 (%)', fontsize=20)
plt.ylim(81, 100)
plt.xlim(0.4, 6.6)

from matplotlib.lines import Line2D

# 创建矩形和线条的配对
h1 = plt.Rectangle((0,0),1,1, facecolor=colors[0], edgecolor='black')

h2 = plt.Rectangle((0,0),1,1, facecolor=colors[1], edgecolor='black')

h3 = Line2D([0], [0], color=colors[2], marker='o', linewidth=3, markersize=10)  # 折线图的图例元素
legend_elements = [
    h1, h2, h3
]
plt.legend(handles=legend_elements, labels=["Phase I", "Phase II", "Average"], fontsize=16, loc="lower left", frameon=True, edgecolor='black', framealpha=0.7)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig("fig/exp2_step.pdf", dpi=300)
plt.savefig("fig/exp2_step.png", dpi=300)