import json
import copy


def encode_tree(knowledge):
    index, root_index = 1, None
    tree = []
    tree, index = encode(knowledge, tree, index, root_index)
    return tree

def encode(knowledge, tree, index, father_index):
    if knowledge == {}:
        return tree, index
    for key in list(knowledge.keys()):
        tree.append({"id":index, "content":key, "father_id":father_index})
        index += 1
        tree, index = encode(knowledge[key], tree, index, index - 1)
    return tree, index





def decode_tree(knowledge_tree):
    knowledge = {}
    for k in knowledge_tree:
        key = f"{k['id']};{k['content']}"
        if k['father_id'] == None:
            knowledge[key] = {}
        else:
            _, knowledge = decode(knowledge, key, k['father_id'])
    
    knowledge = simplify(knowledge)
    return knowledge

def decode(knowledge, key, father_id):
    if knowledge == {}:
        return False, knowledge
    for k in list(knowledge.keys()):
        if str(father_id) == k.split(";")[0]:
            knowledge[k][key] = {}
            return True, knowledge
        if_add, knowledge[k] = decode(knowledge[k], key, father_id)
        if if_add:
            return True, knowledge
    return False, knowledge

def simplify(knowledge):
    if knowledge == {}:
        return knowledge
    for k in list(knowledge.keys()):
        new_k = k.split(";")[-1]
        knowledge[new_k] = knowledge[k]
        del knowledge[k]
        knowledge[new_k] = simplify(knowledge[new_k])
    return knowledge















def get_constraint_to_add(text, setting, knowledge):
    """
    从领域知识中寻找句子text对应的知识
    例如
    text="债券匹配成交的申报要素包括证券号码、数量和价格"
    返回
    {"申报要素":["证券号码","数量","价格"]}
    """
    if 'market' not in setting or 'variety' not in setting:
        return {}
    market, variety = setting['market'], setting['variety']
    if f"交易市场:{market}" in knowledge:
        knowledge = knowledge[f"交易市场:{market}"]
    else:
        return {}
    if f"交易品种:{variety}" in knowledge:
        knowledge = knowledge[f"交易品种:{variety}"]
    elif f"业务:{variety}" in knowledge:
        knowledge = knowledge[f"业务:{variety}"]
    else:
        return {}
    
    q = []  # BFS
    q.append((knowledge, 0))
    max_click_num = 0
    constraints = {}
    while len(q) > 0:
        node, click_num = q.pop(0)
        labels = list(node.keys())
        for label in labels:
            key, value = label.split(":")
            if key in text and node[label] == {}:  # 找到了约束
                if click_num > max_click_num:
                    max_click_num = click_num
                    constraints.clear()
                    constraints[key] = [value]
                elif click_num == max_click_num:
                    if key in constraints:
                        constraints[key].append(value)
                    else:
                        constraints[key] = [value]

            elif value in text:
                q.append((node[label], click_num + 1))
            else:
                q.append((node[label], click_num))

    return constraints


def get_constrainted_values(knowledge, defines, base_key):
    """
    给定场景约束defines，获取base_key对应的所有内容
    例如
    defines={"market":"深圳证券交易所","variety":"债券"}
    base_key="交易方式"
    返回
    ["匹配成交", "点击成交", ...]
    """
    values = []
    if "market" in defines:
        if f"交易市场:{defines['market']}" in knowledge:
            knowledge = knowledge[f"交易市场:{defines['market']}"]
        else:
            return values
    if "variety" in defines:
        if f"交易品种:{defines['variety']}" in knowledge:
            knowledge = knowledge[f"交易品种:{defines['variety']}"]
        elif f"业务:{defines['variety']}" in knowledge:
            knowledge = knowledge[f"业务:{defines['variety']}"]
        else:
            queen = [knowledge]
            head, tail = 0, 0
            find_key = defines['variety']
            find = False
            while head <= tail:
                for key in queen[head]:
                    if find_key == key.split(":")[-1]:
                        knowledge = queen[head][key]
                        find = True
                        break
                    else:
                        if queen[head][key] != {}:
                            queen.append(queen[head][key])
                            tail += 1
                if find:
                    break
                head += 1

    queen = [knowledge]
    head, tail = 0, 0
    find = False
    while head <= tail:
        for key in queen[head]:
            if base_key == key.split(":")[0]:
                values.append(key.split(":")[-1])
                find = True
            else:
                if queen[head][key] != {}:
                    queen.append(queen[head][key])
                    tail += 1
        if find:
            break
        head += 1

    return values

# 例如：给定交易市场、交易品种，（以及交易方式），获取所有子内容
def get_constrainted_all_subvalues(knowledge, defines, base_value=None, remove_extro=True):
    """
    给定场景约束defines，获取base_value对应的所有内容，一直遍历到叶子节点，并且进行组合
    例如一条知识是
    A
    |  \
    B  C
    |  |  \
    D  E  F
    则返回
    [["A","B","D"],["A","C","E"],["A","C","F"]]

    base_value: 例如债券现券，如果不为None，则只返回包含base_value的知识
    """
    values = []
    varieties = []
    for key in encode_tree(knowledge):
        if "品种" in key['content'].split(":")[0] or "业务" == key['content'].split(":")[0]:
            varieties.append(key['content'].split(":")[-1])

    # 限制，避免过久的运行
    if "variety" not in defines or "market" not in defines or defines["variety"] not in varieties:
        return values
    if "market" in defines and f"交易市场:{defines['market']}" in knowledge:
        knowledge = knowledge[f"交易市场:{defines['market']}"]
    ori_knowledge = copy.deepcopy(knowledge)
    if "variety" in defines:
        if f"交易品种:{defines['variety']}" in knowledge:
            knowledge = knowledge[f"交易品种:{defines['variety']}"]
        elif f"业务:{defines['variety']}" in knowledge:
            knowledge = knowledge[f"业务:{defines['variety']}"]
        else:
            queen = [knowledge]
            head, tail = 0, 0
            find_key = defines['variety']
            find = False
            while head <= tail:
                for key in queen[head]:
                    if find_key == key.split(":")[-1]:
                        knowledge = queen[head][key]
                        find = True
                        break
                    else:
                        if queen[head][key] != {}:
                            queen.append(queen[head][key])
                            tail += 1
                if find:
                    break
                head += 1

    if "交易方式" in defines:
        queen = [knowledge]
        head, tail = 0, 0
        find_key = defines['交易方式']
        while head <= tail:
            to_del_key = []
            for key in queen[head]:
                if key.split(":")[0] == "交易方式" and key.split(":")[-1] != find_key:
                    to_del_key.append(key)
                else:
                    if queen[head][key] != {}:
                        queen.append(queen[head][key])
                        tail += 1
            for key in to_del_key:
                del queen[head][key]
            head += 1
        
    
    if base_value is not None:
        queen = [knowledge]
        head, tail = 0, 0
        find_key = defines['variety']
        find = False
        while head <= tail:
            for key in queen[head]:
                if base_value == key.split(":")[-1]:
                    knowledge = queen[head][key]
                    find = True
                    break
                else:
                    if queen[head][key] != {}:
                        queen.append(queen[head][key])
                        tail += 1
            if find:
                break
            head += 1
        if not find:
            knowledge = {}
    # 现在已经找到了指定市场、指定交易品种、指定交易方式、指定base_value的知识
    knowledge = remove_extro_type(knowledge)

    # 限制，避免过久的运行
    if knowledge == ori_knowledge:
        return values

    # 提取 *品种，交易方式，以及一些特殊的知识
    want_key = ["指令", "要素", "品种", "交易方式", "申报类型", "价格类型", "申报方式", "成交方式", "结算方式", "竞买方式", "多主体中标方式"]
    # 寻找所有内容
    values = dfs(knowledge, want_key)

    return values

def remove_extro_type(knowledge):
    """
    如果知识中有品种和交易方式，则删除品种
    """
    have_pz, have_fs = False, False
    for key in knowledge:
        if "品种" in key:
            have_pz = True
        if "交易方式" in key:
            have_fs = True
    if have_pz and have_fs:
        to_del_key = []
        for key in knowledge:
            if "品种" in key:
                fs = get_constrainted_values(knowledge, {key.split(":")[0]:key.split(":")[-1]}, "交易方式")
                if len(fs) > 0:
                    to_del_key.append(key)
        for key in to_del_key:
            del knowledge[key]
        return knowledge
    else:
        return knowledge


def dfs(knowledge, want_key):
    if knowledge == {}:
        return []
    elements = []
    element = []
    last_key = ""
    values = []
    for base_key in want_key:
        for key in knowledge:
            if base_key in key.split(":")[0]:
                if "指令" in base_key or "要素" in base_key:
                    if last_key != key.split(":")[0] and element != []:
                        if element not in elements:
                            elements.append(element)
                        element = []
                    element.append(key)
                    last_key = key.split(":")[0]
                else:
                    new_values = dfs(knowledge[key], want_key)
                    if len(new_values) == 0:
                        new_values = [[key]]
                    else:
                        new_values = [[key] + value for value in new_values]
                    values += new_values

        if element != []:
            if element not in elements:
                elements.append(element)
            element = []
            last_key = ""

    if values == []:
        value = []
        for element in elements:
            k, v = "", ""
            for e in element:
                k = e.split(":")[0]
                v = v + e.split(":")[-1] + ","
            v = v[:-1]
            value.append(f"{k}:{v}")
        values.append(value)
    else:
        # 笛卡尔组合
        values = merge(values)
        for value in values:
            for element in elements:
                k, v = "", ""
                for e in element:
                    k = e.split(":")[0]
                    v = v + e.split(":")[-1] + ","
                v = v[:-1]
                value.append(f"{k}:{v}")
    

    return values

def merge(values):
    new_values = []
    for index in range(1<<len(values)):
        new_value = []
        conflict = False
        for i, value in enumerate(values):
            if index & 1<<i > 0:
                if new_value == []:
                    for v in value:
                        new_value.append(v)
                else:
                    conflict = judge_conflict(new_value, value)
                    if conflict:
                        break
                    for v in value:
                        if v not in new_value:
                            new_value.append(v)
        if not conflict:
            new_values.append(new_value)
    
    # 去重
    values = sorted(new_values, key=lambda x:len(x))
    new_values = []
    while len(values)>0:
        new_values.append(values[-1])
        del values[-1]
        to_del_index = []
        for i, value in enumerate(values):
            exceed = False
            for v in value:
                if v not in new_values[-1]:
                    exceed = True
                    break
            if not exceed or value == []:
                to_del_index.append(i)
        to_del_index.reverse()
        for index in to_del_index:
            del values[index]

    return new_values

def judge_conflict(value1, value2):
    for v1 in value1:
        for v2 in value2:
            if v1.split(":")[0] == v2.split(":")[0] and v1.split(":")[1] != v2.split(":")[1]:
                return True
    return False





if __name__ == "__main__":
    knowledge_file = "../reuse/domain_knowledge/classification_knowledge.json"
    knowledge_tree_file = "../reuse/domain_knowledge/classification_knowledge_tree.json"
    after_decode_file = "../reuse/domain_knowledge/classification_knowledge_decode.json"

    knowledge = json.load(open(knowledge_file, "r", encoding="utf-8"))
    knowledge_tree = encode_tree(knowledge)
    json.dump(knowledge_tree, open(knowledge_tree_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    knowledge = decode_tree(knowledge_tree)
    json.dump(knowledge, open(after_decode_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)

    values = get_constrainted_values(knowledge, {"market":"深圳证券交易所", "variety":"债券"}, "债券品种")
    # values = get_constrainted_all_subvalues(knowledge, {"market":"深圳证券交易所", "variety":"债券"}, "债券现券")
    print(values)