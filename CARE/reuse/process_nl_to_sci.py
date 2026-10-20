import json
import os
import pdfplumber
import cn2an

from transfer.knowledge_tree import encode_tree

def judge_line_begin_with_id(before_str, str):
    """
    判断一行字符串的开头是否是一个id，如果是，返回True和id，否则返回False和空字符串。
    id包括三种：形如"1.1.1"的数字id和形如"第一章"的中文id，以及Rule 1。
    """
    if str == "":
        return False, ""
    # 考虑"1.1.1 正文", "1.1.1正文""1 正文", "1正文", "1.1.1", "正文"这些情况，"1"这种情况被认为是页码，前面预处理已经过滤掉了
    all_id = True
    id = ""
    ss = str.split(".")
    for i, s in enumerate(ss):  # 如果s是数字，加到id上，否则退出循环
        if s.isdigit():
            id += s + "."
        else:
            all_id = False
            break
    if all_id:  # 每一位都是数字，比如"1.1.1"
        # 为了统一特殊考虑一下"1"，它可能出现在txt中，这里将它看作页码
        if id[:-1].isdigit():
            return False, ""
        return True, id[:-1]
    # ss[i]为第一个非数字字符
    for s in ss[i]:
        if s.isdigit():
            id += s
        else:
            break
    if id != "":
        if before_str != "" and before_str[-1] != "。" and str[len(id)] != " ":  # 考虑数字出现在一段开头的特殊情况，比如"正文1正文"
            return False, ""
        return True, id

    # 处理"第一章"、"第一节"、"第一条"、"第1节"等情况
    if str[0] == "第":
        a, b = 1, float("inf")
        if "章" in str and str.index("章") < b:
            a, b = 1, str.index("章")
        if "节" in str and str.index("节") < b:
            a, b = 1, str.index("节")
        if "条" in str and str.index("条") < b:
            a, b = 1, str.index("条")
        if b == float("inf"):
            return False, ""
        s = str[a:b]
        if s.isdigit():
            return True, str[:b+1]
        try:
            cn2an.cn2an(s)
            return True, str[:b+1]
        except Exception as e:
            return False, ""
    
    # Rule 1, Rule 1.1
    if str.startswith("Rule "):
        id = str.split(" ")[1]
        if id.isdigit() or all(c.isdigit() for c in id.split(".")):
            return True, "Rule " + id
    return False, ""


def pdf_to_text(filepath):
    """
    将证券规则pdf文档转成纯文本格式并返回
    """
    # 使用PyPDF2读取pdf文档
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text += f"{page.extract_text()}\n"
    
    # 文档预处理1：替换生僻字符
    text = text.replace("〇", "零")

    # 将文档按照id组织
    s = ""
    for line in text.split("\n"):
        line = line.strip()
        if line == "":
            continue
        # 文档预处理2：去掉页码、附件等无关内容
        if line.find("附件") == 0:
            continue
        if "—" in line or line.isdigit():
            continue
        begin_with_id, id = judge_line_begin_with_id(s, line)
        if begin_with_id:
            # 文档预处理3：如果正文中有空格，删除空格，如果正文和id之间没有空格，加上空格
            content = line[len(id):].replace(" ", "")
            s += "\n" + id + " " + content
        else:
            s += line.replace(" ", "")

    return s


def get_market_variety(s, knowledge):
    market, market_num, variety, variety_num = "", 0, "", 0
    tree = encode_tree(knowledge)

    markets, varieties = [], []
    # 所有的品种/业务有：
    # variety = ["债券","可转债","股票","创业板","基金","基础设施基金","权证","存托凭证","股票质押式回购交易","融资融券交易","资产管理计划份额转让","资产证券化","深港通","质押式报价回购交易"]
    for key in tree:
        if "交易市场" == key['content'].split(":")[0]:
            markets.append(key['content'].split(":")[-1])
            
        elif "品种" in key['content'].split(":")[0] or "业务" == key['content'].split(":")[0]:
            varieties.append(key['content'].split(":")[-1])

    markets = list(set(markets))
    varieties = list(set(varieties))

    market, variety = "", ""
    for value in markets:
        value_count = s.count(value)
        if value_count > market_num:
            market_num = value_count
            market = value
    
    s = s.strip()
    for value in varieties:
        # 统计时只统计标题
        paper = s.split("\n")
        paper = [p for p in paper if not ("修订" in p or "制定" in p)]
        i = 0
        last_line = ""
        while i < len(paper) and not judge_line_begin_with_id(last_line, paper[i])[0]:
            last_line = paper[i]
            i += 1
        if i == 0 or i == len(paper):
            i = 2
        paper = "\n".join(paper[:i])
        value_count = paper.count(value)
        if value_count >= 1 and len(value) > len(variety):  # 选最长的，也就是最细粒度的
            variety = value
            variety_num = value_count

    if market_num == 0:
        if "\n".join(s.split("\n")).count("深圳") > "\n".join(s.split("\n")).count("上海"):
            market = "深圳证券交易所"
        elif "\n".join(s.split("\n")).count("深圳") < "\n".join(s.split("\n")).count("上海"):
            market = "上海证券交易所"
        else:
            if "\n".join(s.split("\n")).count("深交所") > "\n".join(s.split("\n")).count("上交所"):
                market = "深圳证券交易所"
            elif "\n".join(s.split("\n")).count("深交所") < "\n".join(s.split("\n")).count("上交所"):
                market = "上海证券交易所"
            else:
                market = ""
    if "证券交易所" not in market and market != "":
        market = market + "证券交易所"
    if variety_num == 0 and market != "":
        variety = "证券"
    return {"market": market, "variety": variety} if market != "" else {}



def nl_to_sci(knowledge, nl_file=None, nl_data=None, hybrid=False):
    """
    主函数: 将自然语言文本（pdf文档）转成SCI格式的数据，同时提取市场和品种并返回
    """
    # 读取自然语言文本
    if nl_file:
        nl_data = pdf_to_text(nl_file)

    # 识别市场品种
    market_variety = get_market_variety(nl_data, knowledge)

    # 识别SCI
    if not hybrid:
        nl_data = "\n".join(nl_data.strip().split("\n")[1:]).strip()
    default_id = 10000
    sci = []
    last_line = ""
    for line in nl_data.split("\n"):
        line = line.strip()
        if line == "":
            continue
        begin_with_id, id = judge_line_begin_with_id(last_line, line)
        last_line = line
        if ("章" in line or "节" in line) and line.startswith("第"):
            mid = line[1:]
            mid = line.split("章")[0].split("节")[0]
            if isinstance(mid, float):
                continue
            try:
                cn2an.cn2an(mid, mode="normal")
                continue
            except Exception:
                pass

        if begin_with_id:
            # 必须有id才能进入下一步sc
            sci.append({"id": id, "text": line[len(id):].strip()})
        else:
            sci.append({
                "id": str(default_id),
                "text": line.strip()
            })
            default_id += 1

    return sci, market_variety


if __name__ == "__main__":
    knowledge = json.load(open("../reuse/domain_knowledge/classification_knowledge.json", "r", encoding="utf-8"))
    sci, market_variety = nl_to_sci(knowledge, nl_file="cache/上海证券交易所债券交易规则.pdf")
    # input_data = open("cache/input.txt", "r", encoding="utf-8").read()
    # sci, market_variety = nl_to_sci(knowledge, nl_data = input_data)
    
    json.dump(sci, open("cache/sci.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    json.dump(market_variety, open("cache/setting.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)