import copy
import json
import os
import pdfplumber


def is_id(str):
    # 判断一句话是否是id开头
    str = str.split(" ")[0].strip()
    if str == "":
        return False
    if str[0]=="第" and "条" in str:
        return True
    if str.isdigit():
        return True
    if "." not in str:
        return False
    ids = str.split(".")
    for id in ids:
        if not id.isdigit():
            return False
    return True

def read_pdf_to_txt(pdf_file):
    """
    读取并解析pdf文件，将其转化为按照id划分的一个个句子
    pdf_file: 要读取的pdf文件
    ts: 一个字符串，按照id划分的句子之间以"\\n"区分
    """
    s = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            s += f"{page.extract_text()}\n"
    ts = ""
    for i, line in enumerate(s.split("\n")):
        # 每个line是pdf文档中的一行，但是可能有多个句子
        # 什么时候换行呢？
        # 如果是标题、附件等，换行；如果是一个规则的开始（遇到id），则换行
        line = line.strip()
        if line[0:2] == "附件":  # 通常是一篇文档的开始
            if len(line) == 2:
                ts += "\n" + line + "\n"
                continue
            elif line.replace(" ","")[2] == "：" or line.replace(" ","")[2] == ":" or line.replace(" ","")[2].isdigit():  # 附件：、附件:、附件1...
                ts += "\n" + line.replace(" ","") + "\n"
                continue
        if line == "" or line[0] in ["—", "－", "-"] and line[-1] == line[0] or line.isdigit():  # 忽略空行和页码
            continue
        if "（" == line[0] and line[1].isdigit():
            ts += "\n" + line
            continue
        if "目录" in line or "目 录" in line:
            ts += "\n" + line + "\n"
            continue
        if "修订）" == line[-3:]:  # 可能出现在标题中
            ts += line + "\n"
            continue
        if line[0] == "第" and " " in line and ("章" in line or "节" in line):  # 章节标题
            ts += "\n" + line + "\n"
        elif is_id(line) and ts[-1] == "。":  # 遇到1.1.1这样的
            ts += "\n" + line
        else:  # 标题或未结束的一句正文
            ts += line

    # with open("tmp.txt", "a+", encoding="utf-8") as f:
    #     f.write(ts)
    return ts

def get_all_ids(file):
    if file.endswith(".pdf"):
        texts = read_pdf_to_txt(file)
    elif file.endswith(".json"):
        datas = json.load(open(file, "r", encoding="utf-8"))
        texts = ""
        for i, data in enumerate(datas):
            texts += f"{i+1} {data['text']}\n"
    else:
        texts = open(file, "r", encoding="utf-8").read()
    ids = []
    for text in texts.split("\n"):
        if is_id(text):
            ids.append(text.split(" ")[0])
    return ids


def generate_change(ini_rule_file, upd_rule_file, ini_testcase_file, upd_testcase_file):
    change = []
    change_del = []
    ini_ids = get_all_ids(ini_rule_file)
    ini_testcases, upd_testcases = json.load(open(ini_testcase_file, "r", encoding="utf-8")), json.load(open(upd_testcase_file, "r", encoding="utf-8"))
    ini_testcases = [ti for t in ini_testcases for ti in t]
    upd_testcases = [tu for t in upd_testcases for tu in t]

    ini_testcase = sorted(ini_testcases, key=lambda x: x['testid'])
    upd_testcase = sorted(upd_testcases, key=lambda x: x['testid'])

    # 首先统计ini_testcases中哪些测试用例没有在upd_testcases中出现，即哪些测试用例被删除了
    begin, end = 0, 1
    while begin < len(ini_testcases):
        for rule_id in ini_ids:
            if ini_testcases[begin]['rule'].startswith(rule_id) and (ini_testcases[begin]['rule'] == rule_id or ini_testcases[begin]['rule'][len(rule_id)] == "."):
                break
        while end < len(ini_testcases) and ini_testcases[end]['rule'].startswith(rule_id) and (ini_testcases[end]['rule'] == rule_id or ini_testcases[end]['rule'][len(rule_id)] == "."):
            end += 1
        
        find = [False for _ in range(end - begin)]
        for i in range(begin, end):
            ini_testcase = ini_testcases[i]
            ini_testcase_without_id = copy.deepcopy(ini_testcase)
            del ini_testcase_without_id['testid']
            del ini_testcase_without_id['rule']

            for upd_testcase in upd_testcases:
                upd_testcase_without_id = copy.deepcopy(upd_testcase)
                del upd_testcase_without_id['testid']
                del upd_testcase_without_id['rule']
                if ini_testcase_without_id == upd_testcase_without_id:
                    find[i - begin] = True
                    break
        
        if not all(find) and rule_id not in change:
            change.append(rule_id)
            change_del.append(rule_id)

        begin = end
        end += 1
    # 接下来统计upd_testcases中哪些测试用例没有在ini_testcases中出现，即哪些测试用例被新增了
    begin, end = 0, 1
    ini_ids = get_all_ids(upd_rule_file)
    while begin < len(upd_testcases):
        for rule_id in ini_ids:
            if upd_testcases[begin]['rule'].startswith(rule_id) and (upd_testcases[begin]['rule'] == rule_id or upd_testcases[begin]['rule'][len(rule_id)] == "."):
                break
        while end < len(upd_testcases) and upd_testcases[end]['rule'].startswith(rule_id) and (upd_testcases[end]['rule'] == rule_id or upd_testcases[end]['rule'][len(rule_id)] == "."):
            end += 1
        
        find = [False for _ in range(end - begin)]
        for i in range(begin, end):
            upd_testcase = upd_testcases[i]
            upd_testcase_without_id = copy.deepcopy(upd_testcase)
            del upd_testcase_without_id['testid']
            del upd_testcase_without_id['rule']

            for ini_testcase in ini_testcases:
                ini_testcase_without_id = copy.deepcopy(ini_testcase)
                del ini_testcase_without_id['testid']
                del ini_testcase_without_id['rule']

                if ini_testcase_without_id == upd_testcase_without_id:
                    find[i - begin] = True
                    break
        
        if not all(find) and rule_id not in change:
            change.append(rule_id)

        begin = end
        end += 1

    return change, change_del


def generate_change_for_data():
    changes = {}
    changes_del = {}
    for file in sorted(os.listdir("data")):
        if "rule" not in file or "upd" in file:
            continue
        # if "dataset1" not in file:
        #     continue
        
        ini_rule_file = f"data/{file}"
        upd_rule_file = ini_rule_file.replace("ini", "upd")
        ini_testcase_file = f"data/{file.split('.')[0][:-5]}_testcase.json"
        upd_testcase_file = ini_testcase_file.replace("ini", "upd")
        
        change, change_del = generate_change(ini_rule_file, upd_rule_file, ini_testcase_file, upd_testcase_file)
        changes[file.split("_")[0]] = sorted(change)
        changes_del[file.split("_")[0]] = sorted(change_del)
    print(changes_del)
    json.dump(changes, open("data/change.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)




if __name__ == "__main__":
    exit(0)
    generate_change_for_data()