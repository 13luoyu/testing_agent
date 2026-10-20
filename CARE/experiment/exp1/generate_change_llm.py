import json
from experiment.exp1.compute_acc import judge_same
from tqdm import tqdm

gpt_change = {
    "dataset1": [],
    "dataset2": [],
    "dataset3": [],
    "dataset4": [],
    "dataset5": [],
    "dataset6": []
}

gemini_change = {
    "dataset1": [],
    "dataset2": [],
    "dataset3": [],
    "dataset4": [],
    "dataset5": [],
    "dataset6": []
}

grok_change = {
    "dataset1": [],
    "dataset2": [],
    "dataset3": [],
    "dataset4": [],
    "dataset5": [],
    "dataset6": []
}


def generate_llm_change(ini_testcase, llm_testcase, index):
    for testcase in llm_testcase:
        if not isinstance(testcase, list):
            print(testcase)
    changes = []
    ini_testcase = [t for tc in ini_testcase for t in tc]
    llm_testcase = [t for tc in llm_testcase for t in tc]
    # 若case在init不在now，说明删掉；若case在now不在init，说明添加。修改被包含在其中（case不同）
    for it in tqdm(ini_testcase):
        find = False
        for lt in llm_testcase:
            if judge_same(0, 0, it, lt):
                find = True
                break
        if not find:  # 被删掉
            ids = it['rule'].split(",")
            if index == 4 or index == 5:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:3])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index == 2:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:2])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index in [1, 6]:
                new_ids = []
                for id in ids:
                    id = id.split(".")[0]
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index == 3:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:-2])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            for id in ids:
                if id not in changes:
                    changes.append(id)
    
    for lt in tqdm(llm_testcase):
        find = False
        for it in ini_testcase:
            if judge_same(0, 0, it, lt):
                find = True
                break
        if not find:  # 新增
            ids = lt['rule'].split(",")
            if index == 4 or index == 5:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:3])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index == 2:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:2])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index in [1, 6]:
                new_ids = []
                for id in ids:
                    id = id.split(".")[0]
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            elif index == 3:
                new_ids = []
                for id in ids:
                    id = ".".join(id.split(".")[:-2])
                    if id not in new_ids:
                        new_ids.append(id)
                ids = new_ids
            for id in ids:
                if id not in changes:
                    changes.append(id)
    
    return changes





if __name__ == "__main__":
    for i in range(1, 7):
        print(f"Processing dataset{i}...")
        ini_testcase = json.load(open(f"data/dataset{i}_ini_testcase.json", "r", encoding="utf-8"))
        gemini_testcase = json.load(open(f"gemini_result/dataset{i}_upd_testcase.json", "r", encoding="utf-8"))
        gpt_testcase = json.load(open(f"gpt_result/dataset{i}_upd_testcase.json", "r", encoding="utf-8"))
        grok_testcase = json.load(open(f"grok_result/dataset{i}_upd_testcase.json", "r", encoding="utf-8"))

        gemini_change[f"dataset{i}"] = generate_llm_change(ini_testcase, gemini_testcase, i)
        gpt_change[f"dataset{i}"] = generate_llm_change(ini_testcase, gpt_testcase, i)
        grok_change[f"dataset{i}"] = generate_llm_change(ini_testcase, grok_testcase, i)

    json.dump(gemini_change, open("gemini_result/change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(gpt_change, open("gpt_result/change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(grok_change, open("grok_result/change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)