import json
import z3
from transfer.mydsl_to_rules import mydsl_to_rules
import re
from collections import OrderedDict
import copy


"""
A->B真值表
A  B  A->B
----------
0  0   1
0  1   1
1  0   0   条件真，结论假为假
1  1   1   条件真，结论真为真

A^B -> C^D真值表
A  B  C  D  A^B  C^D  A^B -> C^D
-----------------------------------
0  0  0  0   0    0        1
0  0  0  1   0    0        1
0  0  1  0   0    0        1
0  0  1  1   0    1        0
0  1  0  0   0    0        1
0  1  0  1   0    0        1
0  1  1  0   0    0        1
0  1  1  1   0    1        0
1  0  0  0   0    0        1
1  0  0  1   0    0        1
1  0  1  0   0    0        1
1  0  1  1   0    1        0
1  1  0  0   1    0        0
1  1  0  1   1    0        0
1  1  1  0   1    0        0   条件真，无论几个结论为假，都为假
1  1  1  1   1    1        1   条件真，结论真，为真
"""

"""
生成测试用例时，我们不考虑条件为假的情况，因为这样没有意义。
在结果部分，我们只考虑为“时间”、“数量”、“价格”等数值类型的约束和“操作”生成反例，同时注意更改状态信息，其他枚举变量不变
"""



def is_time_key(key):
    if key[-1] == "日" or key[-2:] == "时间" or "期" in key:
        return True
    return False

def is_num_key(key):
    if "量" in key or "数" in key:
        return True
    return False

def is_price_key(key):
    if ("价" in key or "基准" == key or "金额" in key) and "要素" not in key and "指令" not in key and "类型" not in key and "方式" not in key:
        return True
    return False


def find_word(s, word):
    """在字符串s中查找word出现的所有位置"""
    locs = [s.find(word)]
    while locs[-1] != -1:
        locs.append(s.find(word, locs[-1]+1))
    return locs[:-1]


def time_preprocess(time):
    """
    处理时间，判断time中是否有类似9:00-10:00的时间段，以及类似前、后的表达，如果有，返回True和处理后的时间段，否则返回False和空字符串
    Args:
        time: 时间字符串，形如"每个交易日的9:00-10:00"
    Returns:
        valid: 是否是合法的时间段
        numerical_time: 处理后的时间段，形如"9:00-10:00,11:00-12:00"或""
    """
    time_vals = re.findall(r"\d+:\d+", time)  # 所有形似9:00的时间值
    vals_locs = [time.find(time_val) for time_val in time_vals]  # 时间值在time中的位置
    loc_before = sorted(find_word(time, "前") + find_word(time, "早于"))  # 早于、晚于、至等比较词在time中的位置
    loc_after = sorted(find_word(time, "后") + find_word(time, "晚于"))
    loc_between = find_word(time, "至")
    locs = sorted(loc_before + loc_after + loc_between)
    if time_vals:
        time_vals = ["0" + time_val if len(time_val) == 4 else time_val for time_val in time_vals]
        t = ""
        # 考虑三种时间的情况，9:00至10:00，9:00后/晚于于9:00，9:00前/早于9:00，其他情况直接照抄
        if len(vals_locs) != len(loc_before) + len(loc_after) + 2*len(loc_between):
            return False, ""
        p = 0
        valid = True
        for loc in locs:
            if loc in loc_before:
                if time[loc:loc+1] == "前" and p < len(vals_locs) and vals_locs[p] < loc:
                    t += f"00:00:00-{time_vals[p]}:00,"
                    p += 1
                elif time[loc:loc+2] == "早于" and p < len(vals_locs) and vals_locs[p] > loc:
                    t += f"00:00:00-{time_vals[p]}:00,"
                    p += 1
                else:
                    valid = False
                    break
            elif loc in loc_after:
                if time[loc:loc+1] == "后" and p < len(vals_locs) and vals_locs[p] < loc:
                    t += f"{time_vals[p]}:00-24:00:00,"
                    p += 1
                elif time[loc:loc+2] == "晚于" and p < len(vals_locs) and vals_locs[p] > loc:
                    t += f"{time_vals[p]}:00-24:00:00,"
                    p += 1
                else:
                    valid = False
                    break
            else:
                if p+1 < len(vals_locs) and vals_locs[p] < loc and vals_locs[p+1] > loc:
                    t += f"{time_vals[p]}:00-{time_vals[p+1]}:00,"
                    p += 2
                else:
                    valid = False
                    break
        if valid:
            return True, t[:-1]
        else:
            return False, ""
    else:
        return False, ""


def generate_time_testcase(consequence: list):
    """
    处理时间类型的约束，生成对应的测试用例
    Args:
        consequence: 形如["竞买日前", "不晚于", "当日"]
        time_testcase: 时间测试用例列表，要求生成的测试用例添加到这个列表中
        consequences_without_time: 无需特殊处理的结论列表
    """
    time_testcase = []
    time = consequence[2] if consequence[1] == "is" else consequence[1] + consequence[2]
    time.replace("不晚于", "早于").replace("不早于", "晚于")
    valid, numerical_time = time_preprocess(time)
    if valid:  # time是一个类似9:00-10:00的时间段，生成对应的测试用例
        # [[9:00-10:00], ]数组，转化成[[09:00-10:00], ]数组，然后生成反例
        time_testcase.append([consequence[0], numerical_time])
        # 生成反例
        time_list = []
        for t in numerical_time.split(","):
            time_list.extend(t.split("-"))
        for i in range(len(time_list)):
            if len(time_list[i]) == 4:
                time_list[i] = "0" + time_list[i]
        new_time_list = []
        begin = "00:00:00"
        i = 0
        while i < len(time_list):
            if time_list[i] == begin:
                begin = time_list[i+1]
                i += 2
                continue
            new_time_list.append(f"{begin}-{time_list[i]}")
            begin = time_list[i+1]
            i += 2
        if begin != "24:00:00":
            new_time_list.append(f"{begin}-24:00:00")
        time_testcase.append([consequence[0], ",".join(new_time_list)])
    else:  # 没有数字时间，可能是“当日”、“竞买日前”这种
        if "前" in time or "后" in time or "早于" in time or "晚于" in time:  # 生成正测试用例和反测试用例
            time_testcase.append([consequence[0], time])
            if "前" in time:
                time_testcase.append([consequence[0], time.replace("前", "后")])
            elif "后" in time:
                time_testcase.append([consequence[0], time.replace("后", "前")])
            elif "早于" in time:
                time_testcase.append([consequence[0], time.replace("早于", "晚于")])
            elif "晚于" in time:
                time_testcase.append([consequence[0], time.replace("晚于", "早于")])
        else:  # 无需特殊处理，交给z3处理
            time_testcase.append([consequence[0], time])
            time_testcase.append([consequence[0], "非" + time])
    return time_testcase

def judge_op(value):
    if "不低于" in value or "达到" in value or "以上" in value:
        return ">="
    if "不高于" in value or "以下" in value or "不超过" in value or "以内" in value:
        return "<="
    if "低于" in value or "未达到" in value or "不足" in value or "小于" in value:
        return "<"
    if "高于" in value or "超过" in value or "优于" in value or "大于" in value:
        return ">"
    if "不等于" in value:
        return "!="
    return "=="


def generate_consequence_z3_expr(consequences_without_time, z3_variables):
    """
    将所有的consequence转换为z3表达式
    """
    # 避免key重复
    keys = []
    for consequence in consequences_without_time:
        if consequence[0] not in keys:
            keys.append(consequence[0])
        elif not is_num_key(consequence[0]) and not is_price_key(consequence[0]):
            i = 2
            while consequence[0] + str(i) in keys:
                i += 1
            consequence[0] = consequence[0] + str(i)
            keys.append(consequence[0])

    z3_expr = []
    for consequence in consequences_without_time:
        # x为z3变量
        if consequence[0] in z3_variables:
            x = z3_variables[consequence[0]]
        else:
            # 特殊处理：前收盘价的上下100%、不高于匹配成交最近成交价的100个基点、算术运算表达式（如前收盘价格-100元×本次偿还比例）、
            if "%" in consequence[2] or "基点" in consequence[2] or any([op in consequence[2] for op in ["+", "-", "*", "/", "="]]) or (not is_num_key(consequence[0]) and not is_price_key(consequence[0])):
                x = z3.String(consequence[0])
            elif re.findall(r"\d+\.\d+", consequence[2]):
                x = z3.Real(consequence[0])
            elif re.findall(r"\d+", consequence[2]):
                x = z3.Int(consequence[0])
            else:
                x = z3.String(consequence[0])
            z3_variables[consequence[0]] = x
        
        # 如果是数量或价格，需要特殊处理
        if is_num_key(consequence[0]) and re.findall(r"\d+", consequence[2]) != [] and not ("%" in consequence[2] or "基点" in consequence[2] or any([op in consequence[2] for op in ["+", "-", "*", "/", "="]])):
            # 数量可能的情况：10万元面额或者其整数倍、不超过100亿元面额、不低于100万元面额、各应价申报数量等
            if "整数倍" in consequence[2]:
                num = int(re.findall(r"\d+", consequence[2])[0])
                # 考虑万、亿
                p_num = consequence[2].index(str(num))
                p_num += len(str(num))
                while p_num < len(consequence[2]) and (consequence[2][p_num] == "万" or consequence[2][p_num] == "亿"):
                    if consequence[2][p_num] == "万":
                        num *= 10000
                    else:
                        num *= 100000000
                    p_num += 1
                z3_expr.append(x % num == 0)
                z3_expr.append(x >= num)
            else:
                op = judge_op(consequence[1] + consequence[2])
                nums = re.findall(r"\d+", consequence[2])
                if nums:
                    num = int(nums[0])
                    # 考虑万、亿
                    p_num = consequence[2].index(str(num))
                    p_num += len(str(num))
                    while p_num < len(consequence[2]) and (consequence[2][p_num] == "万" or consequence[2][p_num] == "亿"):
                        if consequence[2][p_num] == "万":
                            num *= 10000
                        else:
                            num *= 100000000
                        p_num += 1
                    exp = None
                    if op == ">=":
                        exp = x >= num
                    elif op == "<=":
                        exp = x <= num
                    elif op == "<":
                        exp = x < num
                    elif op == ">":
                        exp = x > num
                    elif op == "==":
                        exp = x == num
                    elif op == "!=":
                        exp = x != num
                    else:  # 默认情况
                        exp = x == num
                    z3_expr.append(exp)
                else:
                    raise ValueError("数量约束中应该有数字，这违反了之前条件判断")

        elif is_price_key(consequence[0]) and re.findall(r"\d+", consequence[2]) != [] and not ("%" in consequence[2] or "基点" in consequence[2] or any([op in consequence[2] for op in ["+", "-", "*", "/", "="]])):
            # 价格可能的情况：全价价格、等于边际价格、前收盘价的上下100%、不高于匹配成交最近成交价的100个基点、0.001元等

            op = judge_op(consequence[1] + consequence[2])
            nums = re.findall(r"\d+\.\d+", consequence[2])
            if not nums:
                nums = re.findall(r"\d+", consequence[2])
            if nums:  # 有数字
                num = float(nums[0]) if "." in nums[0] else int(nums[0])
                # 考虑万、亿
                p_num = consequence[2].index(str(num))
                p_num += len(str(num))
                while p_num < len(consequence[2]) and (consequence[2][p_num] == "万" or consequence[2][p_num] == "亿"):
                    if consequence[2][p_num] == "万":
                        num *= 10000
                    else:
                        num *= 100000000
                    p_num += 1
                exp = None
                if op == ">=":
                    exp = x >= num
                elif op == "<=":
                    exp = x <= num
                elif op == "<":
                    exp = x < num
                elif op == ">":
                    exp = x > num
                elif op == "==":
                    exp = x == num
                elif op == "!=":
                    exp = x != num
                else:
                    exp = x == num
                z3_expr.append(exp)
            else:
                raise ValueError("价格约束中应该有数字，这违反了之前条件判断")
        elif "操作" in consequence[0] and (consequence[0][2:] == "" or consequence[0][2:].isdigit() and int(consequence[0][2:]) < 8):
            z3_expr.append(x == consequence[2])
        else:
            del z3_variables[consequence[0]]
    return z3_expr


def generate_consequence_case_list(solver, z3_variables, consequence_z3_expr, consequence_case_list, index):
    """
    递归函数，用以对consequence_z3_expr中的每项取反并进行笛卡尔积，生成所有可能的情况并添加到consequence_case_list中
    Args:
        solver: z3求解器
        z3_variables: z3变量字典
        consequence_z3_expr: z3表达式列表
        consequence_case_list: 结论测试用例列表
        index: 当前处理的consequences的索引
    """
    if index == len(consequence_z3_expr):
        if solver.check() == z3.sat:
            rs = solver.model()
            consequence_case = []
            for variable in z3_variables:
                key = z3_variables[variable]
                value = rs[key]

                if isinstance(value, z3.IntNumRef):
                    value = int(value.as_long())
                elif isinstance(value, z3.RatNumRef):
                    value = float(value.as_decimal(prec=6)[:6])
                # else:  # z3.SeqRef
                #     value = str(value).replace("\\\\", "\\").replace("{", "").replace("}", "").replace("\"", "").encode("utf-8").decode("unicode_escape")
                else:  # z3.SeqRef (字符串)
                    try:
                        # 先获取原始字符串表示
                        str_repr = str(value)
                        # 移除额外的格式
                        str_repr = str_repr.replace("\\\\", "\\").replace("{", "").replace("}", "").replace("\"", "")
                        # 更安全地处理Unicode转义
                        value = str_repr.encode('utf-8').decode('unicode-escape')
                    except UnicodeDecodeError:
                        # 如果解码失败，使用更保守的方法
                        value = str(value).replace("{", "").replace("}", "").replace("\"", "")
                consequence_case.append([str(key), value])
            consequence_case_list.append(consequence_case)
        return
    
    expr = consequence_z3_expr[index]
    
    solver.push()
    solver.add(expr)
    generate_consequence_case_list(solver, z3_variables, consequence_z3_expr, consequence_case_list, index+1)
    solver.pop()

    solver.push()
    solver.add(z3.Not(expr))
    generate_consequence_case_list(solver, z3_variables, consequence_z3_expr, consequence_case_list, index+1)
    solver.pop()


def post_process_blank(consequence_case_list, consequences_without_time):
    """
    后处理，z3中string != "abc"会生成string为空白，处理这个空白
    """
    for case in consequence_case_list:
        for c in case:
            if c[1] == "":
                for consequence in consequences_without_time:
                    if consequence[0] == c[0]:
                        if consequence[2].startswith("不") or consequence[2].startswith("非"):
                            c[1] = consequence[2][1:]
                        else:
                            c[1] = "非" + consequence[2]
                        break
    


def generate_consequence_case_list_without_data(consequence_case_list, consequences, index, case):
    """
    不为数值型约束生成测试数据，将它们全部看作枚举值
    """
    if index == len(consequences):
        consequence_case_list.append(case)
        return
    consequence = consequences[index]
    key = consequence[0]
    value = consequence[2] if consequence[1] == "is" else consequence[1] + consequence[2]
    non_value = "非" + value if "不" not in value else value.replace("不", "")
    generate_consequence_case_list_without_data(consequence_case_list, consequences, index+1, case + [[key, value]])
    # generate_consequence_case_list_without_data(consequence_case_list, consequences, index+1, case + [[key, non_value]])


def cartesian_product(nums):
    """
    求笛卡尔组合
    例如: nums=[[1,2],[3,4]]，两两看作一组
    return: [[1,3], [1,4], [2,3], [2,4]]
    """
    if len(nums) == 0:
        return []
    if len(nums) == 1:
        return [[num] for num in nums[0]]
    sub_res = cartesian_product(nums[1:])
    res = []
    for num in nums[0]:
        for sub in sub_res:
            res.append([num] + sub)
    return res
    


def process_r3_to_testcase(r3, generate_data = True):
    """
    基于r3规则生成测试用例
    Args:
        r3: r3规则
        generate_data: 是否生成具体数据，还是只生成枚举值
    Returns:
        testcases: 测试用例列表
    """
    rules = mydsl_to_rules(r3)
    # rule = {
    #     "rule": "3.3.4.1.1,3.3.4.9.1.1",
    #     "sourceId": ["3.1.8"],
    #     "conditions": [
    #         ["债券品种", "is", "债券现券"],
    #         ...
    #     ],
    #     "consequences": [
    #         ["单笔最大申报数量", "不超过", "100亿元面额"],
    #         ...
    #     ]
    # }
    testcases = []
    for rule in rules:
        index = 1
        testcase = []
        for condition in rule['conditions']:
            if condition[1] == "is":
                testcase.append([condition[0], condition[2]])
            else:
                testcase.append([condition[0], condition[1] + condition[2]])

        
        if generate_data:
            # 自行处理时间
            time_testcase = []
            consequences_without_time = []
            for consequence in rule['consequences']:
                if is_time_key(consequence[0]):
                    local_time_testcase = generate_time_testcase(consequence)
                    time_testcase.append(local_time_testcase)
                else:
                    consequences_without_time.append(consequence)
            time_testcase = cartesian_product(time_testcase)
            # 数量预处理，如果要生成数值的数量key的数目>=2且不一样，则统一成申报数量
            num_keys = {}
            for consequence in consequences_without_time:
                if is_num_key(consequence[0]) and re.findall(r"\d+", consequence[2]):
                    if consequence[0] in num_keys:
                        num_keys[consequence[0]] += 1
                    else:
                        num_keys[consequence[0]] = 1
            if len(list(num_keys.keys())) >= 2:
                for consequence in consequences_without_time:
                    if consequence[0] in num_keys:
                        consequence[0] = "申报数量"
            
            # 生成z3表达式
            z3_variables = {}
            consequence_z3_expr = generate_consequence_z3_expr(consequences_without_time, z3_variables)
            # 使用z3递归生成测试用例
            consequence_case_list = []
            solver = z3.Solver()
            generate_consequence_case_list(solver, z3_variables, consequence_z3_expr, consequence_case_list, 0)
            for consequence in consequences_without_time:
                if consequence[0] not in z3_variables:
                    for c in consequence_case_list:
                        if consequence[1] == "is":
                            c.append([consequence[0], consequence[2]])
                        else:
                            c.append([consequence[0], consequence[1] + consequence[2]])
            
            # 后处理，z3中string != "abc"会生成string为空白，处理这个空白
            post_process_blank(consequence_case_list, consequences_without_time)

            # 将时间测试用例添加到测试用例中
            if time_testcase:
                new_consequence_case_list = []
                for c in consequence_case_list:
                    for time_case in time_testcase:
                        new_case = c.copy()
                        for t in time_case:
                            # idx=2
                            # keys = [cc[0] for cc in new_case]
                            # if t[0] in keys:
                            #     while t[0] + str(idx) in keys:
                            #         idx += 1
                            #     t[0] = t[0] + str(idx)
                            new_case.append(t)
                        new_consequence_case_list.append(new_case)
                consequence_case_list = new_consequence_case_list
        
        else:
            # 将它们全部当作枚举值
            consequence_case_list = []
            generate_consequence_case_list_without_data(consequence_case_list, rule['consequences'], 0, [])



        # 将结果约束和条件约束组合
        testcase_of_this_rule = []
        for c in consequence_case_list:
            new_testcase = copy.deepcopy(testcase)
            new_testcase.extend(copy.deepcopy(c))
            
            final_testcase = OrderedDict()
            final_testcase['rule'] = rule['rule']
            final_testcase['testid'] = rule['rule'] + "_" + str(index)
            
            # 如果key在条件中且重复，分别设为key、key2、key3...
            # 如果key在结果中且重复，分别设为结果key、结果key2、结果key3...
            for tc in new_testcase:
                if len(final_testcase) - 2 < len(testcase) and tc[0] in final_testcase:  # key在条件中且重复
                    key_index = 2
                    while tc[0] + str(key_index) in final_testcase:
                        key_index += 1
                    tc[0] = tc[0] + str(key_index)
                elif len(final_testcase) - 2 >= len(testcase):  # key在结果中
                    if "结果" + tc[0] in list(final_testcase.keys())[len(testcase):]:  # 结果中重复
                        key_index = 2
                        while "结果" + tc[0] + str(key_index) in list(final_testcase.keys())[len(testcase):]:
                            key_index += 1
                        tc[0] = "结果" + tc[0] + str(key_index)
                    else:
                        tc[0] = "结果" + tc[0]
                final_testcase[tc[0]] = str(tc[1])
            final_testcase['结果'] = "成功" if index == 1 else "不成功"

            if index != 1:
                if "结果状态" in final_testcase:
                    final_testcase['结果状态'] = "非" + final_testcase['结果状态']
                last_r = "结果状态"
                i = 2
                while "结果状态" + str(i) in final_testcase:
                    final_testcase["结果状态" + str(i)] = "非" + final_testcase["结果状态" + str(i)]
                    i += 1
                    last_r = "结果状态" + str(i)
                if "状态" in final_testcase:
                    last_c = "状态"
                    j = 2
                    while "状态" + str(j) in final_testcase:
                        j += 1
                        last_c = "状态" + str(j)
                    final_testcase[last_r] = final_testcase[last_c]

            testcase_of_this_rule.append(final_testcase)
            index += 1
        testcases.append(testcase_of_this_rule)
    return testcases





if __name__ == "__main__":
    with open("cache/r3.mydsl", "r", encoding="utf-8") as f:
        r3 = f.read()
    testcase = process_r3_to_testcase(r3, generate_data=True)
    json.dump(testcase, open("cache/testcase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=4)