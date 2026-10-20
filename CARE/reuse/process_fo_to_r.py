import copy
import json
import re

OR_RELATION_ERROR = 0
RULE_ID_ERROR = 1
IF_ERROR = 2
THEN_ERROR = 3

POS_AND = 3  # and的位置，定值，不随规则表达变化而变


def fix_answer(data, error_type, error_info=None):
    """
    算法修正生成的R规则。主要修格式不正确的问题
    """
    fixed_answer = data
    # 修正or relation
    if error_type == OR_RELATION_ERROR:
        ...
    
    # 修正rule id
    elif error_type == RULE_ID_ERROR:
        fixed_answer =  f"rule {error_info['rule_idx']}"

    # 修正if
    elif error_type == IF_ERROR:
        if error_info["tag"] == "if":  # if出错
            if error_info["exist"] == False:  # 不存在if，直接加到开头
                return "if " + data
            else:  # 存在if，将if调整到开头，if前面的全部忽略
                words = data.split(" ")
                if_pos = words.index("if")
                return " ".join(words[if_pos:])
        elif error_info["tag"] == "body":
            words = data.split(" ")
            new_words = []
            # 处理a:b情况，分为a is b
            for i in range(len(words)):
                if i == 0:  # if
                    new_words.append(words[i])
                    continue
                if ":" in words[i]:
                    idx = words[i].find(":")
                    if idx > 0 and idx < len(words[i]) - 1:  # :在中间
                        if words[i][idx-1].isdigit() and words[i][idx+1].isdigit():
                            # :前后都是数字，这是一个时间，不进行分开处理
                            new_words.append(words[i])
                        else:  # a:b，分开处理
                            new_words.append(words[i][:idx])
                            new_words.append("is")
                            new_words.append(words[i][idx+1:])
                    else:  # :在开头或结尾？未知情况，不处理
                        new_words.append(words[i])
                else:  # 没有冒号情况
                    new_words.append(words[i])
            words = new_words

            # 将句子处理为以and分割的3元组
            idx = 1
            last_and_pos = 0
            while idx < len(words):
                if (idx-1) % 4 != POS_AND:  # 不该是and
                    if words[idx] == "and":
                        # 将last_and_pos到idx的内容转化为3元组
                        if idx - last_and_pos == 1:
                            # ...and and... 或 if and..., 去掉第二个位置的and
                            words = words[:last_and_pos+1] + words[idx+1:]
                            continue
                        elif idx - last_and_pos == 2:
                            # ...and *** and... 或 if *** and..., 将其写成 ...and 约束 is *** and...
                            words = words[:last_and_pos+1] + ["约束", "is"] + words[last_and_pos+1:]
                            continue
                        elif idx - last_and_pos == 3:
                            if "is" in words[last_and_pos+1:idx]:
                                if words[last_and_pos+1] == "is":
                                    words = words[:last_and_pos+1] + ["约束"] + words[last_and_pos+1:]
                                else:
                                    words = words[:last_and_pos] + words[idx:]
                                    idx = last_and_pos
                            else:
                            # 缺少is
                                words = words[:last_and_pos+2] + ["is"] + words[last_and_pos+2:]
                            continue
                    else:  # 正常情况
                        ...
                else:  # 应该是and
                    if words[idx] != "and":
                        # 补充and
                        words = words[:idx] + ["and"] + words[idx:]
                    last_and_pos = idx
                idx += 1
            # 对最后一个3元组检查处理
            if (idx-1) % 4 != POS_AND:  # 一般结束时idx=len(words)，这个位置本应该是下一个and
                if idx - last_and_pos == 1:  # ...and and...
                    words = words[:last_and_pos+1] + words[idx+1:]
                elif idx - last_and_pos == 2:
                    words = words[:last_and_pos+1] + ["约束", "is"] + words[last_and_pos+1:]
                elif idx - last_and_pos == 3:
                    if "is" in words[last_and_pos+1:idx]:
                        words = words[:last_and_pos+1] + ["约束"] + words[last_and_pos+1:]
                    else:
                        words = words[:last_and_pos+2] + ["is"] + words[last_and_pos+2:]
            fixed_answer =  " ".join(words)

    # 修正then
    elif error_type == THEN_ERROR:
        if error_info["tag"] == "then":
            if error_info["exist"] == False:
                return "then " + data
            else:
                words = data.split(" ")
                then_pos = words.index("then")
                return " ".join(words[then_pos:])
        elif error_info["tag"] == "body":
            words = data.split(" ")
            new_words = []
            # 处理a:b情况，分为a is b
            for i in range(len(words)):
                if i == 0:
                    new_words.append(words[i])
                    continue
                if ":" in words[i]:
                    idx = words[i].find(":")
                    if idx > 0 and idx < len(words[i]) - 1:  # :在中间
                        if words[i][idx-1].isdigit() and words[i][idx+1].isdigit():
                            # :前后都是数字，这是一个时间，不进行分开处理
                            new_words.append(words[i])
                        else:  # a:b，分开处理
                            new_words.append(words[i][:idx])
                            new_words.append("is")
                            new_words.append(words[i][idx+1:])
                    else:  # :在开头或结尾？未知情况，不处理
                        new_words.append(words[i])
                else:  # 没有冒号情况
                    new_words.append(words[i])
            words = new_words

            # 将句子处理为以and分割的3元组
            idx = 1
            last_and_pos = 0
            while idx < len(words):
                if (idx-1) % 4 != POS_AND:  # 不该是and
                    if words[idx] == "and":
                        # 将last_and_pos到idx的内容转化为3元组
                        if idx - last_and_pos == 1:  # ...and and...
                            words = words[:last_and_pos+1] + words[idx+1:]
                            continue
                        elif idx - last_and_pos == 2:
                            words = words[:last_and_pos+1] + ["约束", "is"] + words[last_and_pos+1:]
                            continue
                        elif idx - last_and_pos == 3:  # key is / is value / key value
                            if "is" in words[last_and_pos+1:idx]:
                                if words[last_and_pos+1] == "is":
                                    words = words[:last_and_pos+1] + ["约束"] + words[last_and_pos+1:]
                                else:
                                    words = words[:last_and_pos] + words[idx:]
                                    idx = last_and_pos
                            else:
                                words = words[:last_and_pos+2] + ["is"] + words[last_and_pos+2:]
                            continue
                    else:  # 正常情况
                        ...
                else:  # 应该是and
                    if words[idx] != "and":
                        # 补充and
                        words = words[:idx] + ["and"] + words[idx:]
                    last_and_pos = idx
                idx += 1
            # 对最后一个3元组检查处理
            if (idx-1) % 4 != POS_AND:  # 一般结束时idx=len(words)，这个位置本应该是下一个and
                if idx - last_and_pos == 1:  # ...and and...
                    words = words[:last_and_pos+1] + words[idx+1:]
                elif idx - last_and_pos == 2:
                    words = words[:last_and_pos+1] + ["约束", "is"] + words[last_and_pos+1:]
                elif idx - last_and_pos == 3:
                    if "is" in words[last_and_pos+1:idx]:
                        words = words[:last_and_pos+1] + ["约束"] + words[last_and_pos+1:]
                    else:
                        words = words[:last_and_pos+2] + ["is"] + words[last_and_pos+2:]
            fixed_answer =  " ".join(words)
    
    # print(f"修正前: {data}\n修正后: {fixed_answer}\n")
    return fixed_answer




def check_and_fix_answer(answer):
    """
    检查生成R规则中的错误并且修正
    answer example:
        rule 1
        if 债券品种 is 债券现券
        then 约束 is 当日回转交易
        rule 2
        if 操作主体 is 投资者 and 时间 is 当日 and 操作 is 买入 and 交易品种 is 债券
        then 时间 is 当日 and 操作 is 卖出
    修正的类型包括：
        1. id修正，包括格式正确和递增正确
        2. if和then子句修正，包括3元组和连接词and
        3. or relation格式修正
    """
    # 删掉should
    answer = answer.replace("should ", "").replace("should", "")
    datas = answer.split("\n")
    new_data = []
    rule_idx = 1
    stage = 0  # 0: rule id/or relation, 1: if, 2: then
    for i, data in enumerate(datas):
        data = re.sub(r"\s+", " ", data)
        data = data.strip()
        if data == "":
            new_data.append(data)
            continue
        
        # if情况
        if stage == 1:
            if "then" in data:  # 没有if，只有then
                new_data.append("if")
                stage = 2
        if stage == 1:
            words = data.split(" ")
            idx = 0
            while idx < len(words):
                if idx == 0:
                    if words[idx] != "if":  # 如果第一个词不是if，修正
                        if "if" not in words:  # if不存在，在开头加上if
                            data = fix_answer(data, IF_ERROR, {"tag": "if", "exist": False})
                        else:  # if存在，调整顺序
                            data = fix_answer(data, IF_ERROR, {"tag":"if", "exist": True})
                elif (idx-1) % 4 == POS_AND:  # 内容部分必须是以and分割的3元组
                    if words[idx] != "and":
                        data = fix_answer(data, IF_ERROR, {"tag":"body"})
                else:
                    if words[idx] == "and":
                        data = fix_answer(data, IF_ERROR, {"tag":"body"})
                words = data.split(" ")
                idx += 1
            if (idx-1) % 4 != POS_AND:
                data = fix_answer(data, IF_ERROR, {"tag":"body"})
                words = data.split(" ")
            new_data.append(" ".join(words))
            stage = 2
            continue
        
        # then情况
        if stage == 2:
            if "rule" in data:  # 只有if，没有then
                new_data.append("then")
                stage = 0
        if stage == 2:
            words = data.split(" ")
            idx = 0
            while idx < len(words):
                if idx == 0:
                    if words[idx] != "then":
                        if "then" not in words:
                            data = fix_answer(data, THEN_ERROR, {"tag": "then", "exist": False})
                        else:
                            data = fix_answer(data, THEN_ERROR, {"tag": "then", "exist": True})
                elif (idx-1) % 4 == POS_AND:
                    if words[idx] != "and":
                        data = fix_answer(data, THEN_ERROR, {"tag":"body"})
                else:
                    if words[idx] == "and":
                        data = fix_answer(data, THEN_ERROR, {"tag":"body"})
                words = data.split(" ")
                idx += 1
            if (idx-1) % 4 != POS_AND:
                data = fix_answer(data, THEN_ERROR, {"tag":"body"})
                words = data.split(" ")
            new_data.append(" ".join(words))
            stage = 0
            continue
        
        if stage == 0:
            # or relation情况
            if "or" in data:
                pattern = r"or relation:\d+,\d+(,\d+)*"
                if not re.match(pattern, data):  # 格式不正确
                    # data1 = fix_answer(data, OR_RELATION_ERROR)
                    # new_data.append(data1)
                    continue
                else:  # 格式正确
                    new_data.append(data)
                continue
            
            # rule id情况
            if f"rule {rule_idx}" != data:
                new_id = fix_answer(data, RULE_ID_ERROR, {"rule_idx":rule_idx})
                new_data.append(new_id)
            else:
                new_data.append(data)
            rule_idx += 1
            stage = 1
            continue

    # 去重
    for i, data in enumerate(new_data):
        if "if" in data or "then" in data:
            first_word = data.split(" ")[0]
            words = []
            for j in range(1, len(data.split(" ")), 4):
                if data.split(" ")[j:j+3] not in words:
                    words.append(data.split(" ")[j:j+3])
            new_data[i] = first_word + " " + " and ".join([" ".join(w) for w in words])

    rule = "\n".join(new_data)
    return rule




def to_r(datas, fix=True):
    r1 = ""
    for data in datas:
        source_id = data['id']
        if "<|begin_of_text|>" in data['prediction']:  # llama3
            answer = data['prediction'].split("<|end_header_id|>")[-1]
            if "<|eot_id|>" in answer:
                answer = answer.split("<|eot_id|>")[0]
            answer = answer.strip()
        elif "<s><|im_start|>" in data['prediction']:  # internlm2
            answer = data['prediction'].split("assistant")[-1]
            if "<|im_end|>" in answer:
                answer = answer.split("<|im_end|>")[0]
            answer = answer.strip()
        elif "<|im_start|>" in data['prediction']:  # qwen2
            answer = data['prediction'].split("assistant")[-1]
            if "<|im_end|>" in answer:
                answer = answer.split("<|im_end|>")[0]
            answer = answer.strip()
        elif "<s>" in data['prediction']:  # llama2
            answer = data['prediction'].split("Assistant:")[-1]
            if "</s>" in answer:
                answer = answer.split("</s>")[0]
            answer = answer.strip()
        elif "<|user|>" in data['prediction']:  # GLM4
            answer = data['prediction'].split("<|assistant|>")[-1]
            if "<|user|>" in answer:
                answer = answer.split("<|user|>")[0]
            answer = answer.strip()
        
        # 模型后处理，修正生成的规则
        if fix:
            rule = check_and_fix_answer(answer)
        else:
            rule = answer

        # 将规则转化为R1格式
        stage = 0
        for line in rule.split("\n"):
            if stage == 0:
                if "or relation" in line:
                    continue
                    if "," in line and (line[-1] != "," or line[-1] == "," and line[-2].isdigit()):  # or relation:1,2,3
                        max_idx = int(line.split(",")[-1])
                    else:
                        max_idx = line.split("or relation:")[-1]
                        if max_idx.isdigit():  # or relation:1
                            max_idx = int(max_idx)
                        else:  # or relation:
                            continue
                    line = "or relation:"
                    for i in range(1, max_idx+1):
                        line += f"{source_id}.{i},"
                    line = line[:-1]
                    # 为之前所有规则添加or relation
                    ls = r1.split("\n")
                    new_ls = copy.deepcopy(ls)
                    p = len(ls)
                    for i in range(len(ls)-1, -1, -1):
                        if ls[i] == "":
                            p = i
                        elif "sourceId" in ls[i]:
                            if source_id == ls[i].split(" ")[-1].strip():
                                new_ls = new_ls[:p] + [line] + new_ls[p:]
                            else:
                                break
                    r1 = "\n".join(new_ls)
                else:
                    idx = line.split(" ")[-1].strip()
                    r1 += f"\nrule {source_id}.{idx}\nsourceId {source_id}\n"
                    stage = 1
            elif stage == 1:  # if
                r1 += line.strip() + "\n"
                stage += 1
            elif stage == 2:  # then
                r1 += line.strip() + "\n"
                stage = 0
    # 将"不得"替换为"不"
    r1 = r1.replace("不得", "不")

    return r1.strip()







if __name__ == '__main__':
    fo = json.load(open("cache/fo.json"))
    r1 = to_r(fo, fix=True)
    with open("cache/r1.mydsl", "w", encoding="utf-8") as f:
        f.write(r1)
