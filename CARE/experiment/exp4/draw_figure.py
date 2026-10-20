import matplotlib.pyplot as plt
import json
import numpy as np


def draw_acc():

    datasets = ["dataset6", "dataset7", "dataset11", "dataset1", "dataset2", "dataset9"]
    models = ['llama3.2-instruct-1b', 'llama3.2-instruct-3b', 'qwen1.5', 'chatglm3', 'qwen2-instruct', 'llama3-instruct', 'glm4']
    result = {}
    for model in models:
        result[model] = {}
        for dataset in datasets:
            result[model][dataset] = json.load(open(f"log/{model}_result_{dataset}.json", "r", encoding="utf-8"))
            for key in result[model][dataset]:
                result[model][dataset][key] = result[model][dataset][key] * 100


    # 画折线图，每个数据集一个图
    for dataset in datasets:
        x = [1,3,4,6,7,8,9]
        plt.figure(figsize=(8, 5))
        plt.plot(x, [result[model][dataset]["ts_f"] for model in models], marker="o", color="b", label="Overall TS F1", markersize=20, linewidth=5)
        plt.plot(x, [result[model][dataset]["ts_reuse_f"] for model in models], marker="s", color="g", label="Reused TS F1", markersize=20, linewidth=5)
        plt.xticks(x, ['1', '3', '4', '6', '7', '8', '9'], fontsize=40)
        plt.xlim(0, 10)
        

        plt.yticks([0, 20, 40, 60, 80, 100], fontsize=40)
        
        if dataset == "dataset6":
            plt.legend(fontsize=31.5, borderpad=0.1, loc="upper left", frameon=True, shadow=True, borderaxespad=0.05)

        plt.xlabel("# Parameters (B)", fontsize=40)
        plt.grid()
        plt.tight_layout()
        plt.savefig(f"fig/exp3_{dataset}.png")
        plt.close()





if __name__ == "__main__":
    draw_acc()