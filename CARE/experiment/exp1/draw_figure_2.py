import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

data = {
    "Expert": {
        "generation": 64.8,
        "execution": 177.2,
        "review": 10.4,
    },
    "GPT-5.2": {
        "generation": 5.6,
        "execution": 187.0,
        "review": 54.3,
    },
    "Grok-4.1": {
        "generation": 3.4,
        "execution": 153.2,
        "review": 73.5,
    },
    "Gemini-3": {
        "generation": 5.3,
        "execution": 190.4,
        "review": 52.1,
    },
    "ESIM": {
        "generation": 25.6,
        "execution": 171.3,
        "review": 51.2,
    },
    "RPTSP": {
        "generation": 19.2,
        "execution": 169.6,
        "review": 52.8,
    },
    "LLM4Fin": {
        "generation": 0.2,
        "execution": 792.0,
        "review": 21.9,
    },
    # "Ours-NoReuse": {
    #     "generation": 21.6,
    #     "execution": 400.8,
    #     "review": 19.6,
    # },
    "Ours": {
        "generation": 23.6,
        "execution": 173.2,
        "review": 14.2,
    },
}

for key in data:
    for sub_key in data[key]:
        if sub_key == "execution":
            data[key][sub_key] = data[key][sub_key] / 2
        data[key][sub_key] = data[key][sub_key] * 6 / 60
def draw_figure():
    labels = list(data.keys())
    x = np.arange(len(labels))
    x = list(x)
    width = 0.25

    generation_times = [data[label]["generation"] for label in labels]
    execution_times = [data[label]["execution"] for label in labels]
    review_times = [data[label]["review"] for label in labels]
    total_times = [generation + execution + review for generation, execution, review in zip(generation_times, execution_times, review_times)]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4), sharex=True, gridspec_kw={'height_ratios': [2, 5]})
    # 上半部分：展示LLM4Fin的极值
    idx = 6  # LLM4Fin的索引
    ax1.bar(x[idx]-width, generation_times[idx], width, color="#369bff", label="Gen.")
    ax1.bar(x[idx], review_times[idx], width, color="#ffb066", label="Rev.")
    ax1.bar(x[idx]+width, execution_times[idx], width, color="#438d42", label="Exe.")
    ax1.hlines(y=total_times[idx], xmin=x[idx]-width * 1.5, xmax=x[idx]+width * 1.5, colors='#d62728', linestyles='-', linewidth=3)
    ax1.plot(x[idx], total_times[idx], marker='o', color='#d62728', markersize=13, label="Total", linewidth=3)
    ax1.text(x[idx], total_times[idx] + 1.1, f"{total_times[idx]:.1f}", ha='center', fontsize=20, color='#d62728')
    ax1.set_ylim(38, 45)
    # ax1.set_yticks([400, 450])
    ax1.tick_params(axis='y', labelsize=22)
    ax1.spines['bottom'].set_visible(False)
    ax1.tick_params(axis='x', bottom=False)
    ax1.grid(axis='y', linestyle='--', alpha=0.7)


    for i, label in enumerate(labels):
        g_time, e_time, r_time = generation_times[i], execution_times[i], review_times[i]
        if i == 0:
            ax2.bar(x[i] - width, g_time, width, color="#369bff", edgecolor='red', linewidth=2)
        else:
            ax2.bar(x[i] - width, g_time, width, color="#369bff")
        ax2.bar(x[i] + width, e_time, width, color="#438d42")
        ax2.bar(x[i], r_time, width, color="#ffb066", edgecolor='red', linewidth=2)
        ax2.hlines(y=total_times[i], xmin=x[i]-width * 1.5, xmax=x[i]+width * 1.5, colors='#d62728', linestyles='-', linewidth=3)
        ax2.plot(x[i], total_times[i], marker='o', color='#d62728', markersize=10, linewidth=3)
        ax2.text(x[i], total_times[i] + 0.5, f"{total_times[i]:.1f}", ha='center', va='bottom', fontsize=20, color='#d62728')
    ax2.text(x[idx]-0.38, generation_times[idx], "12s", ha='center', va='bottom', fontsize=15, color='#369bff')
    
    ax2.set_ylabel("Time (h)", fontsize=22)
    ax2.yaxis.set_label_coords(-0.1, 0.73)
    ax2.set_xticks(x)
    ax2.set_xticklabels(["Exp.", "GPT", "Grok", "Gem.", "ESIM", "RPT.", "L4F", "CARE"], fontsize=20)
    labels = ax2.get_xticklabels()
    labels[-1].set_fontweight('bold')
    # labels[-1].set_color('red')
    ticklabels = ax2.get_xticklabels()

    dx = -5 / 72  # 向左 5 pt（论文友好单位）
    offset = mtransforms.ScaledTranslation(dx, 0, ax2.figure.dpi_scale_trans)

    ticklabels[2].set_transform(ticklabels[2].get_transform() + offset)
    ticklabels[4].set_transform(ticklabels[4].get_transform() - offset)
    ticklabels[5].set_transform(ticklabels[5].get_transform() - offset)

    ax2.tick_params(axis='y', labelsize=22)
    ax2.set_ylim(0, 17)
    ax2.spines['top'].set_visible(False)
    ax2.set_yticks([0, 5, 10, 15])
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    fig.legend(handles=ax1.get_legend_handles_labels()[0],  # 获取ax1的图例元素
        labels=ax1.get_legend_handles_labels()[1],   # 获取ax1的图例标签
        loc='upper center', fontsize=22, frameon=True, ncol=4, borderpad=0.2, labelspacing=0.1, handletextpad=0.2, columnspacing=0.7, bbox_to_anchor=(0.55, 1.037), edgecolor='black', framealpha=0.5)

    d = 0.5
    kwargs = dict(marker=[(-1, -d), (1, d)], markersize=12,
              linestyle="none", color='k', mec='k', mew=1, clip_on=False)
    ax1.plot([0, 1], [0, 0], transform=ax1.transAxes, **kwargs)
    ax2.plot([0, 1], [1, 1], transform=ax2.transAxes, **kwargs)

    plt.tight_layout()
    plt.subplots_adjust(left=0.135, right=0.975)
    plt.savefig("fig/exp1_time.pdf", dpi=300)
    plt.savefig("fig/exp1_time.png", dpi=300)


if __name__ == "__main__":
    draw_figure()