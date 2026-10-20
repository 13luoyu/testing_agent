import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


METHODS = [
    "Experts",
    "E2E LLMs",
    "ACC-Fra",
    "MSG-Spec",
    "LLM4Fin",
    "RAFT",
    "RAFT + HITL",
]

# Minutes across all six financial datasets.
EXPLICATION = np.array([0, 0, 350.8, 0, 20184.6, 20.4, 20.4])
GENERATION = np.array([2553.49, 84.3, 20.4, 179.6, 0, 70.6, 66.7])
REVIEW = np.array([0, 299.2, 260.1, 228.1, 0, 60.7, 214.659])
TOTAL = EXPLICATION + GENERATION + REVIEW
TOTAL_LABELS = ["42.56h", "6.39h", "10.52h", "6.80h", "336.41h", "2.53h", "5.03h"]


def main():
    x = np.arange(len(METHODS))
    width = 0.24
    colors = ["#3898ef", "#ffad5b", "#438f43"]

    fig, axes = plt.subplots(
        3,
        1,
        sharex=True,
        figsize=(9, 4.2),
        gridspec_kw={"height_ratios": [1, 1, 3], "hspace": 0.14},
    )

    for ax in axes:
        ax.bar(x - width, EXPLICATION, width, color=colors[0], label="Exp.")
        ax.bar(x, GENERATION, width, color=colors[1], label="Gen.")
        ax.bar(x + width, REVIEW, width, color=colors[2], label="Rev.")
        ax.hlines(TOTAL, x - 0.3, x + 0.3, color="#dc2525", linewidth=2.2)
        ax.scatter(x, TOTAL, color="#dc2525", s=55, zorder=3)
        ax.grid(axis="y", linestyle="--", color="#bdbdbd", alpha=0.8)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="y", labelsize=15)

    axes[0].set_ylim(19800, 20550)
    axes[1].set_ylim(2350, 2700)
    axes[2].set_ylim(0, 680)
    axes[0].spines["bottom"].set_visible(False)
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["bottom"].set_visible(False)
    axes[2].spines["top"].set_visible(False)
    for ax in axes[:2]:
        ax.tick_params(axis="x", which="both", bottom=False, top=False, labelbottom=False)

    for upper, lower in zip(axes[:-1], axes[1:]):
        kwargs = {"color": "black", "clip_on": False, "linewidth": 1.2}
        upper.plot((-0.01, 0.01), (-0.03, 0.03), transform=upper.transAxes, **kwargs)
        lower.plot((-0.01, 0.01), (0.97, 1.03), transform=lower.transAxes, **kwargs)

    for index, (total, label) in enumerate(zip(TOTAL, TOTAL_LABELS)):
        if total >= 10000:
            ax = axes[0]
            offset = 75
        elif total >= 2000:
            ax = axes[1]
            offset = 20
        else:
            ax = axes[2]
            offset = 35
        ax.text(
            index,
            total + offset,
            label,
            color="#dc2525",
            ha="center",
            fontsize=17,
        )

    axes[2].set_xticks(x)
    axes[2].set_xticklabels(METHODS, rotation=17, ha="center", fontsize=18)
    for index, label in enumerate(axes[2].get_xticklabels()):
        if index >= 5:
            label.set_fontweight("bold")
    axes[2].set_ylabel("Time (m)", fontsize=18)
    handles = [
        Patch(facecolor=colors[0], label="Exp."),
        Patch(facecolor=colors[1], label="Gen."),
        Patch(facecolor=colors[2], label="Rev."),
        Line2D([0], [0], color="#dc2525", marker="o", linewidth=2, label="Total"),
    ]
    fig.legend(
        handles=handles,
        loc="upper right",
        ncol=1,
        frameon=True,
        fontsize=14,
        handlelength=1.8,
    )

    fig.subplots_adjust(left=0.11, right=0.995, top=0.97, bottom=0.23)
    fig.savefig("fig/exp1_time.pdf", bbox_inches="tight")
    fig.savefig("fig/exp1_time.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
