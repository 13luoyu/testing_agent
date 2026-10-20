import json
import random
from tqdm import tqdm

MAX_ATTEMPTION = 1000

def random_add(data, num, kv_map):
    """
    在当前的数据中随机插入一个新元素
    data: 当前规则以及标注，结构为data={"prompt":"", "answer":""}
    num: 新生成数据的数量
    kv_map: 所有的key-value对，结构为kv_map[key]=[value1,value2,...]
    """
    # 新生成的数据，新生成数据的prompt
    new_datas, prompt_cache = [], []
    answer = data['answer'].replace("\n", " ").split(" ")
    prompt = data['prompt'].split("规则:")[1]
    # 记录当前已生成了多少条数据，以及循环次数
    count, while_count = 0, 0

    while count < num and while_count < MAX_ATTEMPTION:
        # 随机选择一对key-value
        key_to_add = random.choice(list(kv_map.keys()))
        value_to_add = random.choice(kv_map[key_to_add])
        if f"{key_to_add} is {value_to_add}" in data['answer']:
            continue
        # 将key-value加入prompt中。加入策略是将句子按照逗号分隔，并随机选一个句子，在该句后面新开一个句子放这个key-value
        sentence = prompt.split("，")
        add_pos = random.choice(list(range(len(sentence)+1)))
        # 如果在中间，插入"且key为value"；如果在开头，插入"key为value"；如果在结尾，则去掉前一句的句号并在当前句加入句号。
        sentence.insert(add_pos, f"且{key_to_add}为{value_to_add}")
        if add_pos == 0:
            sentence[add_pos] = sentence[add_pos][1:]
        elif add_pos == len(sentence):
            sentence[add_pos-1] = sentence[add_pos-1][:-1]  # 去掉末尾的句号
            sentence[add_pos] = sentence[add_pos] + "。"
        new_prompt = "，".join(sentence)
        
        # 去重，避免生成重复数据
        if new_prompt in prompt_cache or new_prompt == prompt:
            continue
        prompt_cache.append(new_prompt)

        # 更新answer
        # 统计answer中的value在add_pos前后的sentence中的位置，将新的value插入value出现在sentence中最多的句子中间
        # before: answer中的value出现在add_pos前的sentence中的位置
        # before_num: 同一个sentence中出现value的次数
        # before_idx: 同一个sentence中出现value的最大位置索引
        before, before_num, before_idx = [], [], 0
        mid = False  # before是否已经赋值，如果是，需要更新before，或寻找value在add_pos后的sentence的位置
        for i, a in enumerate(answer):
            if a == "if" and answer[i+1] != "then" or a == "then" or a == "and":
                value = answer[i+3]
                if not mid:
                    if add_pos >= 1 and value in sentence[add_pos-1]:  # 找到了value在add_pos前的sentence的位置
                        mid = True
                        before.append(i+3)
                        before_num.append(1)
                        before_idx = sentence[add_pos-1].find(value)
                    elif add_pos == 0:  # 新的元素插在开头
                        mid = True
                        before.append(i)
                        before_num.append(1)
                        before_idx = 0
                else:
                    if add_pos >= 1 and value in sentence[add_pos-1] and sentence[add_pos-1].find(value) > before_idx:  # 更多value出现在add_pos前的sentence
                        before[-1] = i+3
                        before_num[-1] += 1
                        before_idx = sentence[add_pos-1].find(value)
                    elif add_pos + 1 < len(sentence) and value in sentence[add_pos+1]:  # value出现在add_pos后的sentence
                        mid = False
                        before_idx = 0
                    
        if len(before_num) == 0:  # 插在了一些sentence后，且前面的sentence不能写成子句。因此将新的子句插入到每个if后面
            before = [i for i, a in enumerate(answer) if a == "if"]
            before_num = [1] * len(before)
        # 在before_num最大的before那里插入
        max_before_num = max(before_num)
        new_answer = []
        for i, a in enumerate(answer):
            new_answer.append(a)
            if i in before and before_num[before.index(i)] == max_before_num:
                if new_answer[-1] in ['if', 'then', 'and']:
                    new_answer += [key_to_add, "is", value_to_add, "and"]
                else:
                    new_answer += ["and", key_to_add, "is", value_to_add]
        
        new_answer = " ".join(new_answer).replace(" if", "\nif").replace(" then", "\nthen").replace(" rule", "\nrule").replace(" or", "\nor")
        
        new_datas.append({
            "prompt": data['prompt'].split("规则:")[0] + "规则:" + new_prompt,
            "answer": new_answer
        })
        count += 1

    return new_datas


def random_delete(data, num):
    """
    在当前的数据中随机删除一个新元素
    data: 当前规则以及标注，结构为data={"prompt":"", "answer":""}
    num: 新生成数据的数量
    """
    new_datas, prompt_cache = [], []
    answer = data['answer'].replace("\n", " ").split(" ")
    prompt = data['prompt'].split("规则:")[1]
    # 找到所有的约束子句
    clauses = []
    for i, a in enumerate(answer):
        if a == "if" and answer[i+1] != "then" or a == "and" or a == "then":
            if answer[i+1:i+4] not in clauses:
                clauses.append(answer[i+1:i+4])
    all_values = [clause[2] for clause in clauses]
    count, while_count = 0, 0
    while count < min(num, len(clauses)) and while_count < MAX_ATTEMPTION:  # 限定最大循环次数
        while_count += 1
        # 随机选择一个删除
        value_to_delete = random.choice(clauses)[2]
        all_clause_to_delete = [clause for clause in clauses if clause[2] == value_to_delete]
        
        # 删除prompt中对应词
        new_prompt = prompt
        p = 0
        p = new_prompt[p:].find(value_to_delete)
        while p != -1:
            cover = False
            for value in all_values:
                if value == value_to_delete:
                    continue
                if value in new_prompt[max(p + len(value_to_delete) - len(value), 0): min(p + len(value), len(new_prompt))]:
                    cover = True
                    break
            if not cover:  # 删除
                new_prompt = new_prompt[:p] + new_prompt[p:].replace(value_to_delete, "", 1)
            else:  # 跳过当前词
                p += len(value_to_delete)
            next_p = new_prompt[p:].find(value_to_delete)
            if next_p == -1:
                break
            p = p + next_p
        
        # 避免重复
        if new_prompt in prompt_cache or new_prompt == prompt:
            continue
        prompt_cache.append(new_prompt)

        # 删除answer中对应词
        new_answer = []
        i = 0
        while i < len(answer):
            if answer[i:i+3] in all_clause_to_delete:
                if i+3 < len(answer) and answer[i+3] == "and":
                    i += 4
                else:
                    i += 3
            else:
                new_answer.append(answer[i])
                i += 1
        new_answer = " ".join(new_answer).replace(" if", "\nif").replace(" then", "\nthen").replace(" rule", "\nrule").replace(" or", "\nor")
        
        new_datas.append({
            "prompt": data['prompt'].split("规则:")[0] + "规则:" + new_prompt,
            "answer": new_answer
        })
        count += 1



    return new_datas



def random_replace(data, num, kv_map):
    """
    在当前的数据中随机将一个value替换为相同key的另一个value
    data: 当前规则以及标注，结构为data={"prompt":"", "answer":""}
    num: 新生成数据的数量
    kv_map: 所有的key-value对，结构为kv_map[key]=[value1,value2,...]
    """
    new_datas, prompt_cache = [], []
    answer = data['answer'].replace("\n", " ").split(" ")
    prompt = data['prompt'].split("规则:")[1]
    value_positions = []
    all_values = []
    count, while_count = 0, 0
    for i, a in enumerate(answer):
        if a == "if" and answer[i+1] != "then" or a == "then" or a == "and":
            value_positions.append(i+3)
            if answer[i+3] not in all_values:
                all_values.append(answer[i+3])

    while count < num and while_count < MAX_ATTEMPTION:
        while_count += 1
        
        replace_value_position = random.choice(value_positions)
        key, old_value = answer[replace_value_position-2], answer[replace_value_position]
        if key in kv_map and len(kv_map[key]) >= 2:
            new_value = random.choice(kv_map[key])
            while new_value == old_value:
                new_value = random.choice(kv_map[key])
            # 现在有了value和new_value，更新prompt和answer
            # 修改prompt
            new_prompt = prompt
            p = 0
            p = new_prompt[p:].find(old_value)
            while p != -1:
                cover = False
                for value in all_values:
                    if value == old_value:
                        continue
                    if value in new_prompt[max(p + len(old_value) - len(value), 0): min(p + len(value), len(new_prompt))]:
                        cover = True
                        break
                if not cover:  # 删除
                    new_prompt = new_prompt[:p] + new_prompt[p:].replace(old_value, new_value, 1)
                    p += len(new_value)
                else:  # 跳过当前词
                    p += len(old_value)
                next_p = new_prompt[p:].find(old_value)
                if next_p == -1:
                    break
                p = p + next_p
            
            # 避免重复
            if new_prompt in prompt_cache or new_prompt == prompt:
                continue
            prompt_cache.append(new_prompt)

            # 修改answer
            new_answer = []
            i = 0
            while i < len(answer):
                if answer[i] == key and answer[i+2] == old_value:
                    new_answer += [answer[i], answer[i+1], new_value]
                    i += 3
                else:
                    new_answer.append(answer[i])
                    i += 1
            new_answer = " ".join(new_answer).replace(" if", "\nif").replace(" then", "\nthen").replace(" rule", "\nrule").replace(" or", "\nor")
            
            new_datas.append({
                "prompt": data['prompt'].split("规则:")[0] + "规则:" + new_prompt,
                "answer": new_answer
            })
            count += 1

    return new_datas


def random_swap(data, num):
    """
    在当前的数据中随机选择两个key相同的value进行交换
    data: 当前规则以及标注，结构为data={"prompt":"", "answer":""}
    num: 新生成数据的数量
    """
    new_datas, prompt_cache = [], []
    answer = data['answer'].replace("\n", " ").split(" ")
    prompt = data['prompt'].split("规则:")[1]
    count, while_count = 0, 0
    all_values = []
    for i, a in enumerate(answer):
        if a == "if" and answer[i+1] != "then" or a == "then" or a == "and":
            if answer[i+3] not in all_values:
                all_values.append(answer[i+3])
    
    # 统计具有相同key的value
    same_key_values = {}
    # same_key_value["交易方式"] = {
    #     "value": ["匹配成交", "点击成交"],
    #     "value_pos" = [50, 60]
    # }
    for i, a in enumerate(answer):
        if a == "if" and answer[i+1] != "then" or a == "then" or a == "and":
            if answer[i+1] in same_key_values:
                same_key_values[answer[i+1]]['value'].append(answer[i+3])
                same_key_values[answer[i+1]]['value_pos'].append(i+3)
            else:
                same_key_values[answer[i+1]] = {
                    "value": [answer[i+3]],
                    "value_pos": [i+3]
                }

    while count < num and while_count < MAX_ATTEMPTION:
        while_count += 1
        # 随机选择一个key
        key_to_swap = random.choice(list(same_key_values.keys()))
        # 获取对应的value，并随机选择两个不同的value
        vs = list(set(same_key_values[key_to_swap]['value']))
        if len(vs) == 1:
            continue
        value_to_swap_1 = random.choice(vs)
        value_to_swap_2 = random.choice(vs)
        while value_to_swap_2 == value_to_swap_1:
            value_to_swap_2 = random.choice(vs)
        value_to_swap_1_pos_answer = [p for i, p in enumerate(same_key_values[key_to_swap]['value_pos']) if same_key_values[key_to_swap]['value'][i] == value_to_swap_1]
        value_to_swap_2_pos_answer = [p for i, p in enumerate(same_key_values[key_to_swap]['value_pos']) if same_key_values[key_to_swap]['value'][i] == value_to_swap_2]

        # 先更新prompt
        new_prompt = prompt
        p = 0
        p1 = new_prompt[p:].find(value_to_swap_1) + p
        p2 = new_prompt[p:].find(value_to_swap_2) + p
        while p1 != -1 or p2 != -1:
            # 计算要替换的词的位置
            if p1 != -1 and p2 != -1:
                if p1 < p2:
                    p = p1
                    old_value = value_to_swap_1
                    new_value = value_to_swap_2
                else:
                    p = p2
                    old_value = value_to_swap_2
                    new_value = value_to_swap_1
            elif p1 != -1:
                p = p1
                old_value = value_to_swap_1
                new_value = value_to_swap_2
            else:
                p = p2
                old_value = value_to_swap_2
                new_value = value_to_swap_1
            # 必须与其他词不能重叠才替换
            cover = False
            for value in all_values:
                if value == old_value:
                    continue
                if value in new_prompt[max(p + len(old_value) - len(value), 0): min(p + len(value), len(new_prompt))]:
                    cover = True
                    break
            if not cover:  # 替换
                new_prompt = new_prompt[:p] + new_value + new_prompt[p + len(old_value):]
                p += len(new_value)
            else:
                p += len(old_value)
            
            p1 = new_prompt[p:].find(value_to_swap_1)
            p2 = new_prompt[p:].find(value_to_swap_2)
            if p1 == -1 and p2 == -1:
                break
            if p1 != -1:
                p1 += p
            if p2 != -1:
                p2 += p
        
        if new_prompt in prompt_cache or new_prompt == prompt:
                continue
        prompt_cache.append(new_prompt)

        # 更新answer
        new_answer = answer.copy()
        for p in value_to_swap_1_pos_answer:
            new_answer[p] = value_to_swap_2
        for p in value_to_swap_2_pos_answer:
            new_answer[p] = value_to_swap_1
        new_answer = " ".join(new_answer).replace(" if", "\nif").replace(" then", "\nthen").replace(" rule", "\nrule").replace(" or", "\nor")
            
        new_datas.append({
            "prompt": data['prompt'].split("规则:")[0] + "规则:" + new_prompt,
            "answer": new_answer
        })
        count += 1

    return new_datas


def data_augment(datas, nums=[4,2,4,1]):
    new_datas = []
    
    kv_map = {}
    # 记录标注数据中所有的key以及value
    # kv_map[key] = [value1, value2, ...]
    for data in datas:
        answer = data['answer'].replace("\n", " ").split(" ")
        for i, a in enumerate(answer):
            if a == "if" and answer[i+1] != "then" or a == "then" or a == "and":
                key, value = answer[i+1], answer[i+3]
                if key in kv_map and value not in kv_map[key]:
                    kv_map[key].append(value)
                elif key not in kv_map:
                    kv_map[key] = [value]

    for data in tqdm(datas):
        new_datas += random_add(data,num=nums[0],kv_map=kv_map)
        new_datas += random_delete(data, num=nums[1])
        new_datas += random_replace(data,num=nums[2],kv_map=kv_map)
        new_datas += random_swap(data,num=nums[3])
        new_datas.append(data)
        # print(new_datas)
        # exit(0)
    return new_datas


if __name__ == "__main__":
    datas = json.load(open("../data/data_for_LLM_decoder/formalization_train_data.json", "r", encoding="utf-8"))
    new_datas = data_augment(datas)
    random.shuffle(new_datas)
    json.dump(new_datas, open("../data/data_for_LLM_decoder/formalization_train_data_augmented.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)
