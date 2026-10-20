import numpy as np
import matplotlib.pyplot as plt
import json


def draw_figure(metric):
    # load data
    # data = {method: {item: values of 6 datasets}}
    data = {
        "Grok-4": {
            "Changed Rule": [],
            "Changed Req.": [],
            "Changed Sce.": [],
            "Changed TC": [],
            "Changed TS": [],
            "TC": [],
            "TS": [],
        },
        "GPT-5": {
            "Changed Rule": [],
            "Changed Req.": [],
            "Changed Sce.": [],
            "Changed TC": [],
            "Changed TS": [],
            "TC": [],
            "TS": [],
        },
        "ReTool": {
            "Changed Rule": [],
            "Changed Req.": [],
            "Changed Sce.": [],
            "Changed TC": [],
            "Changed TS": [],
            "TC": [],
            "TS": [],
        }
    }

    for i in [1,2,6,7,9,11]:
        grok_chain_data = json.load(open(f"log/grok_chain_dataset{i}.json", "r", encoding="utf-8"))
        for key in grok_chain_data:
            grok_chain_data[key] = grok_chain_data[key] * 100
        if metric == "precision":
            metric = "pre"
        elif metric == "recall":
            metric = "rec"
        data['Grok-4']['Changed Rule'].append(grok_chain_data[f'rule_{metric}'])
        data['Grok-4']['Changed Req.'].append(grok_chain_data[f'req_{metric}'])
        data['Grok-4']['Changed Sce.'].append(grok_chain_data[f'sce_{metric}'])
        grok_tc_data = json.load(open(f"log/grok_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in grok_tc_data:
            grok_tc_data[key] = grok_tc_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['Grok-4']['Changed TC'].append(grok_tc_data[f'{metric}_changed_testcase'])
        data['Grok-4']['TC'].append(grok_tc_data[f'{metric}_testcase'])
        grok_ts_data = json.load(open(f"log/grok_ts_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in grok_ts_data:
            grok_ts_data[key] = grok_ts_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['Grok-4']['Changed TS'].append(grok_ts_data[f'{metric}_changed_testcase'])
        data['Grok-4']['TS'].append(grok_ts_data[f'{metric}_testcase'])

        gpt_chain_data = json.load(open(f"log/gpt_chain_dataset{i}.json", "r", encoding="utf-8"))
        for key in gpt_chain_data:
            gpt_chain_data[key] = gpt_chain_data[key] * 100
        if metric == "precision":
            metric = "pre"
        elif metric == "recall":
            metric = "rec"
        data['GPT-5']['Changed Rule'].append(gpt_chain_data[f'rule_{metric}'])
        data['GPT-5']['Changed Req.'].append(gpt_chain_data[f'req_{metric}'])
        data['GPT-5']['Changed Sce.'].append(gpt_chain_data[f'sce_{metric}'])
        gpt_tc_data = json.load(open(f"log/gpt_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in gpt_tc_data:
            gpt_tc_data[key] = gpt_tc_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['GPT-5']['Changed TC'].append(gpt_tc_data[f'{metric}_changed_testcase'])
        data['GPT-5']['TC'].append(gpt_tc_data[f'{metric}_testcase'])
        gpt_ts_data = json.load(open(f"log/gpt_ts_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in gpt_ts_data:
            gpt_ts_data[key] = gpt_ts_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['GPT-5']['Changed TS'].append(gpt_ts_data[f'{metric}_changed_testcase'])
        data['GPT-5']['TS'].append(gpt_ts_data[f'{metric}_testcase'])

        ours_chain_data = json.load(open(f"log/ours_chain_dataset{i}.json", "r", encoding="utf-8"))
        for key in ours_chain_data:
            ours_chain_data[key] = ours_chain_data[key] * 100
        if metric == "precision":
            metric = "pre"
        elif metric == "recall":
            metric = "rec"
        data['ReTool']['Changed Rule'].append(ours_chain_data[f'rule_{metric}'])
        data['ReTool']['Changed Req.'].append(ours_chain_data[f'req_{metric}'])
        data['ReTool']['Changed Sce.'].append(ours_chain_data[f'sce_{metric}'])
        ours_tc_data = json.load(open(f"log/ours_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in ours_tc_data:
            ours_tc_data[key] = ours_tc_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['ReTool']['Changed TC'].append(ours_tc_data[f'{metric}_changed_testcase'])
        data['ReTool']['TC'].append(ours_tc_data[f'{metric}_testcase'])
        ours_ts_data = json.load(open(f"log/ours_ts_result_dataset{i}.json", "r", encoding="utf-8"))[f'dataset{i}']
        for key in ours_ts_data:
            ours_ts_data[key] = ours_ts_data[key] * 100
        if metric == "pre":
            metric = "precision"
        elif metric == "rec":
            metric = "recall"
        data['ReTool']['Changed TS'].append(ours_ts_data[f'{metric}_changed_testcase'])
        data['ReTool']['TS'].append(ours_ts_data[f'{metric}_testcase'])



    colors = ['#8ecae6', '#219ebc', "#016292"]
    width = 0.25
    plt.figure(figsize=(10, 5))

    plot_data = []
    positions = []

    for i, cat in enumerate(['Changed Rule', 'Changed Req.', 'Changed Sce.', 'Changed TC', 'Changed TS', 'TC', 'TS']):
        for j, method in enumerate(['Grok-4', 'GPT-5', 'ReTool']):
            plot_data.append(data[method][cat])
            if j == 0:
                positions.append(i + j * width - 0.05)
            elif j == 1:
                positions.append(i + j * width)
            else:
                positions.append(i + j * width + 0.05)

    # draw boxplot
    bp = plt.boxplot(
        plot_data,
        positions=positions,
        widths=width,
        patch_artist=True,  # 允许填充颜色
        boxprops=dict(color='black'),
        capprops=dict(color='black'),
        whiskerprops=dict(color='black'),
        flierprops=dict(marker='o'),
        medianprops=dict(color='orange', linewidth=2)
    )
    
    # 为不同方法设置不同颜色
    for i, box in enumerate(bp['boxes']):
        box.set_facecolor(colors[i % len(colors)])

    x = [i + width for i in range(7)]
    plt.xticks(x, ['C. Rule      ', 'C. Req.   ', 'C. Sce.', 'C. TC', 'C. TS', 'O. TC', 'O. TS'], fontsize=25)
    plt.ylim(0, 120)
    plt.yticks([0, 20, 40, 60, 80, 100], fontsize=25)

    # 添加网格线
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 添加图例（只在第一个图添加）
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor=colors[i], edgecolor='black', label=method) 
        for i, method in enumerate(['Grok-4', 'GPT-5', 'ReTool'])
    ]
    plt.legend(handles=legend_elements, fontsize=24, ncol=3, loc="upper center", frameon=True, shadow=True, borderaxespad=0.1)
    # if metric == "precision":
    #     plt.ylabel("Precision (%)", fontsize=25)
    # elif metric == "recall":
    #     plt.ylabel("Recall (%)", fontsize=25)
    # elif metric == "f1":
    #     plt.ylabel("F1 Score", fontsize=25)


    plt.tight_layout()
    plt.savefig(f'fig/exp1_{metric}.png', dpi=300, bbox_inches='tight')



def draw_figure_bsc():
    with open(f"log/bsc.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()
    llm4fin, grok, gpt, ours = [], [], [], []
    grok_changed, gpt_changed, ours_changed = [], [], []
    for method in ["llm4fin", "grok", "gpt", "ours"]:
        for dataset in ["dataset1", "dataset2", "dataset6", "dataset7", "dataset9", "dataset11"]:
            res = 0
            changed_res = 0
            for line in lines:
                if method in line and dataset in line and line[line.index(dataset) + len(dataset)] == "的":
                    if "变更" in line:
                        changed_res = float(line.split("为")[-1]) * 100
                    else:
                        res = float(line.split("为")[-1]) * 100
            if method == "llm4fin":
                llm4fin.append(res)
            elif method == "grok":
                grok_changed.append(changed_res)
                grok.append(res)
            elif method == "gpt":
                gpt_changed.append(changed_res)
                gpt.append(res)
            elif method == "ours":
                ours_changed.append(changed_res)
                ours.append(res)
    width=0.25
    plt.figure(figsize=(10, 5))
    plot_data = [grok_changed, gpt_changed, ours_changed, grok, gpt, ours]
    positions = [0.7, 1, 1.3, 2, 2.3, 2.6]
    colors = ['#8ecae6', '#219ebc', "#016292", '#8ecae6', '#219ebc', "#016292"]

    # draw boxplot
    bp = plt.boxplot(
        plot_data,
        positions=positions,
        widths=width,
        patch_artist=True,  # 允许填充颜色
        boxprops=dict(color='black'),
        capprops=dict(color='black'),
        whiskerprops=dict(color='black'),
        flierprops=dict(marker='o'),
        medianprops=dict(color='orange', linewidth=2)
    )
    
    # 为不同方法设置不同颜色
    for i, box in enumerate(bp['boxes']):
        box.set_facecolor(colors[i])


    plt.xticks([1.025, 2.475], ['Change Test Cases', 'Overall Test Cases'], fontsize=25)
    plt.ylim(20, 120)
    plt.yticks([20, 40, 60, 80, 100], fontsize=25)

    # 添加网格线
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 添加图例（只在第一个图添加）
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor=colors[0], edgecolor='black', label='Grok-4'),
        plt.Rectangle((0,0),1,1, facecolor=colors[1], edgecolor='black', label='GPT-5'),
        plt.Rectangle((0,0),1,1, facecolor=colors[2], edgecolor='black', label='ReTool'),
    ]
    plt.legend(handles=legend_elements, fontsize=24, ncol=4, loc="upper center", frameon=True, shadow=True, borderaxespad=0.1, handletextpad=0.1, columnspacing=0.4)
    plt.ylabel("BSC (%)", fontsize=25)


    plt.tight_layout()
    plt.savefig(f'fig/exp1_bsc.png', dpi=300, bbox_inches='tight')




if __name__ == "__main__":
    draw_figure("precision")
    draw_figure("recall")
    draw_figure("f1")
    draw_figure_bsc()