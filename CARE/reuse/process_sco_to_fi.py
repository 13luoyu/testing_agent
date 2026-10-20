import json

def select_rules(sco):
    """
    将sco数据中的无法测试的规则和领域知识过滤掉，返回可测试的规则
    """
    fi = []
    for s in sco:
        if s["type"] == "1":
            fi.append(s)
    return fi

if __name__ == "__main__":
    sco_data = json.load(open("cache/sco.json", "r", encoding="utf-8"))
    fi_data = select_rules(sco_data)
    json.dump(fi_data, open("cache/fi.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)