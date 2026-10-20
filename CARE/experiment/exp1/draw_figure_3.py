import json
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

def draw_figure():
    data = {
        "Overall Test Case": {
            "Expert": [],
            "GPT-5.5": [],
            "Grok-4.3": [],
            "Gemini-3.1": [],
            "ESIM": [],
            "RPTSP": [],
            "LLM4Fin": [],
            "CARE": []
        },
        "Overall Test Suite": {
            "Expert": [],
            "GPT-5.5": [],
            "Grok-4.3": [],
            "Gemini-3.1": [],
            "LLM4Fin": [],
            "CARE": []
        }
    }

    keys1 = list(data["Overall Test Case"].keys())
    keys2 = list(data["Overall Test Suite"].keys())
    methods1 = ["expert", "gpt", "grok", "gemini", "ESIM", "RPTSP", "llm4fin", "ours"]
    methods2 = ["expert", "gpt", "grok", "gemini", "llm4fin", "ours"]

    for i in range(1, 7):
        for j, method in enumerate(methods1):
            result = json.load(open(f"log/{method}_result_dataset{i}.json", "r", encoding="utf-8"))
            data["Overall Test Case"][keys1[j]].append(result[f"dataset{i}"]["f1_testcase"])
        for j, method in enumerate(methods2):
            result = json.load(open(f"log/{method}_ts_result_dataset{i}.json", "r", encoding="utf-8"))
            data["Overall Test Suite"][keys2[j]].append(result[f"dataset{i}"]["f1_testcase"])
    
    for key in data.keys():
        for subkey in data[key].keys():
            data[key][subkey] = list(np.array(data[key][subkey]) * 100)
    
    # 8种对比强烈颜色
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#17becf']
    colors = colors + colors[:4] + colors[6:]
    width = 0.08
    fig, ax = plt.subplots(figsize=(8, 4))
    positions, plot_data = [], []
    for i in range(len(list(data.keys()))):
        for j in range(len(data[list(data.keys())[i]])):
            positions.append(i + j * (width + 0.02))
            plot_data.append(data[list(data.keys())[i]][list(data[list(data.keys())[i]].keys())[j]])
    
    bp = plt.boxplot(
        plot_data,
        positions=positions,
        widths=width,
        patch_artist=True,
        boxprops=dict(facecolor='white', color='black'),
        medianprops=dict(color='black', linewidth=1),
        whiskerprops=dict(color='black'),
        capprops=dict(color='black'),
        flierprops=dict(marker='o', color='black', markersize=5)
    )

    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
    x = []
    for i in range(len(data.keys())):
        center = i + (len(data[list(data.keys())[i]]) - 1) * (width + 0.02) / 2
        x.append(center)
    plt.xticks(x, ["Updated Test Case", "Updated Test Suite"], fontsize=20)
    plt.yticks(fontsize=20)
    plt.xlim(-0.1, 1.6)
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor=colors[i], edgecolor='black', label=method) 
        for i, method in enumerate(list(data["Overall Test Case"].keys()))
    ]
    leg = plt.legend(handles=legend_elements, fontsize=16, loc='upper center', bbox_to_anchor=(0.5, 1.28), ncol=4, frameon=True, borderpad=0.2, labelspacing=0.2, handletextpad=0.4, columnspacing=1, edgecolor='black', framealpha=0.5)

    leg.get_texts()[-1].set_fontweight('bold')

    plt.ylabel("F1 (%)", fontsize=22)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.subplots_adjust(top=0.81, bottom=0.11)
    plt.savefig("fig/exp1_var.pdf", dpi=300)
    plt.savefig("fig/exp1_var.png", dpi=300)


if __name__ == "__main__":
    draw_figure()