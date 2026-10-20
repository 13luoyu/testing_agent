import json

methods = ["Expert", "GPT", "Grok", "Gemini", "ESIM", "RPTSP", "LLM4Fin", "Ours"]
products = ["Changed Test Case", "Reused Test Case", "Overall Test Case", "Changed Test Suite", "Reused Test Suite", "Overall Test Suite"]
metrics = ["Precision", "Recall", "F1"]

data = {
    method: {
        product: {
            metric: [] for metric in metrics
        } for product in products
    } for method in methods
}
for method in methods:
    data[method]["Overall Test Case"]["BSC"] = []


for method in methods:
    real_method = [method]
    if method == "Expert":
        real_method = [method.lower()]
    elif method == "GPT":
        real_method = ["gpt"]
    elif method == "Grok":
        real_method = ["grok"]
    elif method == "Gemini":
        real_method = ["gemini"]
    elif method == "LLM4Fin":
        real_method = ["llm4fin"]
    elif method == "Ours":
        real_method = ["ours"]
    for rm in real_method:
        for i in range(1, 7):
            l = json.load(open(f"log/{rm}_result_dataset{i}.json", "r", encoding="utf-8"))
            if rm != "llm4fin":
                data[method]["Changed Test Case"]["Precision"].append(l[f"dataset{i}"]["precision_changed_testcase"])
                data[method]["Changed Test Case"]["Recall"].append(l[f"dataset{i}"]["recall_changed_testcase"])
                data[method]["Changed Test Case"]["F1"].append(l[f"dataset{i}"]["f1_changed_testcase"])
            data[method]["Overall Test Case"]["Precision"].append(l[f"dataset{i}"]["precision_testcase"])
            data[method]["Overall Test Case"]["Recall"].append(l[f"dataset{i}"]["recall_testcase"])
            data[method]["Overall Test Case"]["F1"].append(l[f"dataset{i}"]["f1_testcase"])
            
            if rm != "llm4fin":
                l = json.load(open(f"log/{rm}_reuse_result_dataset{i}.json", "r", encoding="utf-8"))
                data[method]["Reused Test Case"]["Precision"].append(l["testcase_reuse_precision"])
                data[method]["Reused Test Case"]["Recall"].append(l["testcase_reuse_recall"])
                data[method]["Reused Test Case"]["F1"].append(l["testcase_reuse_f1"])
                if "scenario_reuse_precision" in l:
                    data[method]["Reused Test Suite"]["Precision"].append(l["scenario_reuse_precision"])
                    data[method]["Reused Test Suite"]["Recall"].append(l["scenario_reuse_recall"])
                    data[method]["Reused Test Suite"]["F1"].append(l["scenario_reuse_f1"])

            if rm != "ESIM" and rm != "RPTSP":
                l = json.load(open(f"log/{rm}_ts_result_dataset{i}.json", "r", encoding="utf-8"))
                if rm != "llm4fin":
                    data[method]["Changed Test Suite"]["Precision"].append(l[f"dataset{i}"]["precision_changed_testcase"])
                    data[method]["Changed Test Suite"]["Recall"].append(l[f"dataset{i}"]["recall_changed_testcase"])
                    data[method]["Changed Test Suite"]["F1"].append(l[f"dataset{i}"]["f1_changed_testcase"])
                data[method]["Overall Test Suite"]["Precision"].append(l[f"dataset{i}"]["precision_testcase"])
                data[method]["Overall Test Suite"]["Recall"].append(l[f"dataset{i}"]["recall_testcase"])
                data[method]["Overall Test Suite"]["F1"].append(l[f"dataset{i}"]["f1_testcase"])

            l = json.load(open(f"log/{rm}_dataset{i}_bsc.json", "r", encoding="utf-8"))
            data[method]["Overall Test Case"]["BSC"].append(l[f"dataset{i}"])
    
for key1 in data:
    for key2 in data[key1]:
        for key3 in data[key1][key2]:
            values = data[key1][key2][key3]
            avg_value = sum(values) / len(values) if len(values) > 0 else "-"
            data[key1][key2][key3] = round(avg_value * 100, 2) if avg_value != "-" else avg_value

# 画csv
with open("fig/exp1_table.csv", "w", encoding="utf-8") as f:
    f.write("Method,Changed Test Case,,,Reused Test Case,,,Overall Test Case,,,,Changed Test Suite,,,Reused Test Suite,,,Overall Test Suite,,\n")
    f.write(",Pre.,Rec.,F1,Pre.,Rec.,F1,Pre.,Rec.,F1,BSC,Pre.,Rec.,F1,Pre.,Rec.,F1,Pre.,Rec.,F1\n")
    for method in methods:
        f.write(method)
        for product in products:
            for metric in metrics:
                f.write(f",{data[method][product][metric]}")
            if product == "Overall Test Case":
                f.write(f",{data[method][product]['BSC']}")
        f.write("\n")