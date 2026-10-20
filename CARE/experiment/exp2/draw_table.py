import json


def draw_table():
    data = {
        "ours": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
            "Changed Test Suite F1": [],
            "Changed Test Suite Delta": [],
            "Reused Test Suite F1": [],
            "Reused Test Suite Delta": [],
            "Overall Test Suite F1": [],
            "Overall Test Suite Delta": []
        },
        "w/o R+S+I": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
        },
        "w/o S+I": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": []
        },
        "w/o G+C": {
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
            "Overall Test Suite F1": [],
            "Overall Test Suite Delta": []
        },
        "w/o I": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
            "Changed Test Suite F1": [],
            "Changed Test Suite Delta": [],
            "Reused Test Suite F1": [],
            "Reused Test Suite Delta": [],
            "Overall Test Suite F1": [],
            "Overall Test Suite Delta": []
        },
        "ESIM": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
        },
        "RPTSP": {
            "Changed Test Case F1": [],
            "Changed Test Case Delta": [],
            "Reused Test Case F1": [],
            "Reused Test Case Delta": [],
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
        },
        "LLM4Fin": {
            "Overall Test Case F1": [],
            "Overall Test Case Delta": [],
            "Overall Test Suite F1": [],
            "Overall Test Suite Delta": []
        }
    }

    methods = ["ours", "no_scenario", "no_requirement", "directly", "no_change_impact_analysis", "ESIM", "RPTSP", "llm4fin"]
    keys = list(data.keys())

    for idx, method in enumerate(methods):
        for i in range(1, 7):
            result = json.load(open(f"log/{method}_dataset{i}.json", "r", encoding="utf-8"))
            if method not in ["directly", "llm4fin"]:
                data[keys[idx]]["Changed Test Case F1"].append(result[f"dataset{i}"]["f1_changed_testcase"])
                data[keys[idx]]["Changed Test Case Delta"].append("-")
            data[keys[idx]]["Overall Test Case F1"].append(result[f"dataset{i}"]["f1_testcase"])
            data[keys[idx]]["Overall Test Case Delta"].append("-")
            if method not in ["no_requirement", "no_scenario", "ESIM", "RPTSP"]:
                result = json.load(open(f"log/{method}_ts_result_dataset{i}.json", "r", encoding="utf-8"))
                if method not in ["directly", "llm4fin"]:
                    data[keys[idx]]["Changed Test Suite F1"].append(result[f"dataset{i}"]["f1_changed_testcase"])
                    data[keys[idx]]["Changed Test Suite Delta"].append("-")
                data[keys[idx]]["Overall Test Suite F1"].append(result[f"dataset{i}"]["f1_testcase"])
                data[keys[idx]]["Overall Test Suite Delta"].append("-")
            if method not in ["directly", "llm4fin"]:
                result = json.load(open(f"log/{method}_reuse_result_dataset{i}.json", "r", encoding="utf-8"))
                data[keys[idx]]["Reused Test Case F1"].append(result["testcase_reuse_f1"])
                data[keys[idx]]["Reused Test Case Delta"].append("-")
                if method not in ["no_requirement", "no_scenario", "ESIM", "RPTSP"]:
                    data[keys[idx]]["Reused Test Suite F1"].append(result["scenario_reuse_f1"])
                    data[keys[idx]]["Reused Test Suite Delta"].append("-")

    for method in keys:
        for metric in data[method]:
            if "Delta" not in metric:
                data[method][metric] = sum(data[method][metric]) / len(data[method][metric]) * 100
    
    for method in keys:
        for metric in data[method]:
            if "Delta" in metric:
                if method == "ours":
                    data[method][metric] = "-"
                else:
                    corresponding_metric = metric.replace("Delta", "F1")
                    delta = (data["ours"][corresponding_metric] - data[method][corresponding_metric]) / data["ours"][corresponding_metric] * 100
                    data[method][metric] = delta
    
    with open("fig/exp2_table.csv", "w", encoding="utf-8") as f:
        f.write("Method,Changed Test Case,,Reused Test Case,,Overall Test Case,,Changed Test Suite,,Reused Test Suite,,Overall Test Suite,\n")
        f.write(",F1,Delta,F1,Delta,F1,Delta,F1,Delta,F1,Delta,F1,Delta\n")
        for method in keys:
            if method == "ours" or method == "w/o I":
                f.write(method)
                for metric in data[method]:
                    if isinstance(data[method][metric], str):
                        f.write(f",{data[method][metric]}")
                    else:
                        f.write(f",{data[method][metric]:.1f}")
                        if "Delta" in metric:
                            f.write("↓")
                f.write("\n")
            elif method == "w/o G+C" or method == "LLM4Fin":
                f.write(method)
                f.write(f",-,-,-,-,{data[method]['Overall Test Case F1']:.1f},{data[method]['Overall Test Case Delta']:.1f}↓,-,-,-,-,{data[method]['Overall Test Suite F1']:.1f},{data[method]['Overall Test Suite Delta']:.1f}↓\n")
            else:
                f.write(method)
                f.write(f",{data[method]['Changed Test Case F1']:.1f},{data[method]['Changed Test Case Delta']:.1f}↓,{data[method]['Reused Test Case F1']:.1f},{data[method]['Reused Test Case Delta']:.1f}↓,{data[method]['Overall Test Case F1']:.1f},{data[method]['Overall Test Case Delta']:.1f}↓,-,-,-,-,-,-\n")



if __name__ == "__main__":
    draw_table()