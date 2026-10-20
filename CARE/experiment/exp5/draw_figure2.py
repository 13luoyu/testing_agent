import matplotlib.pyplot as plt
import numpy as np
import json

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

data = json.load(open("data/rate.json", "r", encoding="utf-8"))

x = np.array([int(key) / (len(data)-1) * 100 for key in data])
y = np.array([data[key]["min"] * 100 for key in data])
y2 = np.array([data[key]["max"] * 100 for key in data])
# 画一个y=x作为对照
y3 = x

plt.figure(figsize=(8, 5))
plt.plot(x, y2, color="green")
plt.plot(x, y, color="green", linestyle="--")

plt.fill_between(x, y, y2, color="green", alpha=0.08, label="True Range")
plt.xlabel("Changed Rules (%)", fontsize=25)
plt.ylabel("Affected Test Cases (%)", fontsize=25)
plt.xticks([0, 20, 40, 60, 80, 100], labels=["0", "20", "40", "60", "80", "100"], fontsize=25)
plt.yticks([0, 20, 40, 60, 80, 100], labels=["0", "20", "40", "60", "80", "100"], fontsize=25)
plt.grid(axis="both", linestyle="--", alpha=0.7)


data = json.load(open("data/rate_ESIM.json", "r", encoding="utf-8"))
y4 = np.array([data[key]["min"] * 100 for key in data])
y5 = np.array([data[key]["max"] * 100 for key in data])
plt.plot(x, y5, color="blue")
plt.plot(x, y4, color="blue", linestyle="--")
plt.fill_between(x, y4, y5, color="blue", alpha=0.08, label="E/R Range")
plt.plot(x, y3, color="black", label="y = x")



plt.legend(fontsize=25, loc="lower right", edgecolor="black", borderpad=0.3, borderaxespad=0.2, labelspacing=0.1, handletextpad=0.4)


plt.tight_layout()
plt.savefig("fig/inter_exp_rate_esim.pdf", dpi=300)