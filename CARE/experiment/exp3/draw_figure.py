import matplotlib.pyplot as plt
import json
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

def draw_figure():
    # x轴为3个领域，y为metric的值，每个领域有4个柱子，为testsuite reuse precision, recall, f1, bsc
    domain = ["finance", "automotive", "power"]
    datasets = ["dataset1", "dataset2", "dataset3", "dataset4", "dataset5"]
    metric = ["changed test case f1", "reused test case f1", "overall test case f1", "rc", "changed test suite f1", "reused test suite f1", "overall test suite f1"]

    # 每个值是6个数据集3个LLM的平均值
    data = {d: {m: [] for m in metric} for d in domain}
    
    # 金融
    for dataset in datasets + ["dataset6"]:
        dataraw = json.load(open(f"../exp1/log/ours_ts_result_{dataset}.json", "r", encoding="utf-8"))
        data['finance']['changed test suite f1'].append(dataraw[dataset]['f1_changed_testcase'])
        data['finance']['overall test suite f1'].append(dataraw[dataset]['f1_testcase'])
        dataraw = json.load(open(f"../exp1/log/ours_reuse_result_{dataset}.json", "r", encoding="utf-8"))
        data['finance']['reused test suite f1'].append(dataraw['scenario_reuse_f1'])
        data['finance']['reused test case f1'].append(dataraw['testcase_reuse_f1'])
        dataraw = json.load(open(f"../exp1/log/ours_{dataset}_bsc.json", "r", encoding="utf-8"))
        data['finance']['rc'].append(dataraw[dataset])
        dataraw = json.load(open(f"../exp1/log/ours_result_{dataset}.json", "r", encoding="utf-8"))
        data['finance']['changed test case f1'].append(dataraw[dataset]['f1_changed_testcase'])
        data['finance']['overall test case f1'].append(dataraw[dataset]['f1_testcase'])
    # 汽车
    for dataset in datasets[:3]:
            dataraw = json.load(open(f"log/ours_ts_result_{dataset}.json", "r", encoding="utf-8"))
            data['automotive']['changed test suite f1'].append(dataraw[dataset]['f1_changed_testcase'])
            data['automotive']['overall test suite f1'].append(dataraw[dataset]['f1_testcase'])
            dataraw = json.load(open(f"log/ours_reuse_result_{dataset}.json", "r", encoding="utf-8"))
            data['automotive']['reused test suite f1'].append(dataraw['scenario_reuse_f1'])
            data['automotive']['reused test case f1'].append(dataraw['testcase_reuse_f1'])
            dataraw = json.load(open(f"log/ours_{dataset}_bsc.json", "r", encoding="utf-8"))
            data['automotive']['rc'].append(dataraw[dataset])
            dataraw = json.load(open(f"log/ours_result_{dataset}.json", "r", encoding="utf-8"))
            data['automotive']['changed test case f1'].append(dataraw[dataset]['f1_changed_testcase'])
            data['automotive']['overall test case f1'].append(dataraw[dataset]['f1_testcase'])
    # 电力
    for dataset in datasets[3:5]:
            dataraw = json.load(open(f"log/ours_ts_result_{dataset}.json", "r", encoding="utf-8"))
            data['power']['changed test suite f1'].append(dataraw[dataset]['f1_changed_testcase'])
            data['power']['overall test suite f1'].append(dataraw[dataset]['f1_testcase'])
            dataraw = json.load(open(f"log/ours_reuse_result_{dataset}.json", "r", encoding="utf-8"))
            data['power']['reused test suite f1'].append(dataraw['scenario_reuse_f1'])
            data['power']['reused test case f1'].append(dataraw['testcase_reuse_f1'])
            dataraw = json.load(open(f"log/ours_{dataset}_bsc.json", "r", encoding="utf-8"))
            data['power']['rc'].append(dataraw[dataset])
            dataraw = json.load(open(f"log/ours_result_{dataset}.json", "r", encoding="utf-8"))
            data['power']['changed test case f1'].append(dataraw[dataset]['f1_changed_testcase'])
            data['power']['overall test case f1'].append(dataraw[dataset]['f1_testcase'])

    pt_data = {}
    for d in data:
        pt_data[d] = {}
        for m in data[d]:
            pt_data[d][m] = np.mean(data[d][m])
    print(json.dumps(pt_data, indent=4, ensure_ascii=False))

    x = np.arange(len(domain))              # 领域位置
    bar_width = 0.12                        # 柱子宽度
    fig, ax = plt.subplots(figsize=(11, 2.5))
    # 颜色（七种对比强烈）
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#17becf']
    # 画每个指标
    labels = ["Reg. TC F1", "Rec. TC F1", "Upd. TC F1", "Upd. TC BSC", "Reg. TS F1", "Rec. TS F1", "Upd. TS F1"]

    for m in metric:
        for d in domain:
            for i in range(len(data[d][m])):
                data[d][m][i] = data[d][m][i] * 100

    for i, m in enumerate(metric):
        values = [np.mean(data[d][m]) for d in domain]
        ax.bar(x + i * bar_width, values, width=bar_width, color=colors[i], label=labels[i], capsize=5)

        ax.scatter(x + i * bar_width, [min(data[d][m]) for d in domain], marker='_', s=200, color='black', linewidth=1.5)
        ax.scatter(x + i * bar_width, [max(data[d][m]) for d in domain], marker='_', s=200, color='black', linewidth=1.5)
        for xi in x:
            ax.vlines(xi + i * bar_width, min(data[domain[xi]][m]), max(data[domain[xi]][m]), colors='black', linestyles='-', linewidth=1.5)
        
    # ax.set_xlabel("Domain", fontsize=13)
    ax.set_ylabel("Metric (%)", fontsize=14)
    ax.set_xticks(x + bar_width * (len(metric) - 1) / 2)
    ax.set_xticklabels([d.capitalize() for d in domain], fontsize=14)
    ax.tick_params(axis='y', labelsize=13)
    ax.set_yticks(np.arange(0, 101, 20))
    ax.set_ylim(0, 105)
    ax.legend(fontsize=11.5, ncol=7, loc='upper center', bbox_to_anchor=(0.5, 1.3), edgecolor='black', framealpha=0.5, columnspacing=0.5, handletextpad=0.5)
    ax.grid(axis="y", linestyle="--", alpha=0.5)


    plt.tight_layout()
    plt.savefig("fig/exp3.pdf", dpi=300)
    plt.savefig("fig/exp3.png", dpi=300)



if __name__ == "__main__":
    draw_figure()