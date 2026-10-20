from transfer.mydsl_to_rules import mydsl_to_rules
import copy


class Link:
    def __init__(self, rule):
        self.rules = [rule]
        self.state = ""
        for condition in rule["conditions"]:
            if condition[0] == "状态":
                self.state = condition[2]
                break
        self.result_state = ""
        for consequence in rule["consequences"]:
            if consequence[0] == "状态":
                self.result_state = consequence[2]
                break
    
    def judge_and_link(self, link):
        if self.state == "" or self.result_state == "" or link.state == "" or link.result_state == "":
            return None
        for rule in self.rules:
            if rule in link.rules:
                return None
        if self.conflict(link):
            return None
        
        if self.state == link.result_state:
            # link在前面，self在后面
            new_link = copy.deepcopy(link)
            new_link.rules.extend(copy.deepcopy(self.rules))
            new_link.result_state = self.result_state
            return new_link
        elif self.result_state == link.state:
            # self在前面，link在后面
            new_link = copy.deepcopy(self)
            new_link.rules.extend(copy.deepcopy(link.rules))
            new_link.result_state = link.result_state
            return new_link
        else:
            return None
    
    def conflict(self, link):
        rule1_cons, rule2_cons = {}, {}
        # example:
        # rule1_cons['操作'] = ['申报', '买入']
        # ...
        for rule1 in self.rules:
            for condition in rule1['conditions']:
                if condition[0] not in rule1_cons:
                    rule1_cons[condition[0]] = [condition[2]]
                elif condition[2] not in rule1_cons[condition[0]]:
                    rule1_cons[condition[0]].append(condition[2])
            for consequence in rule1['consequences']:
                if consequence[0] not in rule1_cons:
                    rule1_cons[consequence[0]] = [consequence[2]]
                elif consequence[2] not in rule1_cons[consequence[0]]:
                    rule1_cons[consequence[0]].append(consequence[2])
        for rule2 in link.rules:
            for condition in rule2['conditions']:
                if condition[0] not in rule2_cons:
                    rule2_cons[condition[0]] = [condition[2]]
                elif condition[2] not in rule2_cons[condition[0]]:
                    rule2_cons[condition[0]].append(condition[2])
            for consequence in rule2['consequences']:
                if consequence[0] not in rule2_cons:
                    rule2_cons[consequence[0]] = [consequence[2]]
                elif consequence[2] not in rule2_cons[consequence[0]]:
                    rule2_cons[consequence[0]].append(consequence[2])
        
        for key in rule1_cons:
            if key in rule2_cons and (key in ["交易市场", "交易品种", "交易方向", "交易方式"] or "方式" in key or "品种" in key):
                if set(rule1_cons[key]) != set(rule2_cons[key]):  # 如果两条规则的条件结果中有相同的属性，但对应的值不相同，则为冲突
                    return True
        return False
    
    def __str__(self):
        return str(self.rules)
    
    def __repr__(self):
        return str(self.rules)
    
    def __eq__(self, other):
        return self.rules == other.rules


def generate_linked_scenario(r3):
    """
    计算需求场景的个数
    因为需求场景是使用“状态”、“结果状态”连接的r3规则，需要计算总共能够连接成多少个链条（需求场景）
    方法是找到匹配的状态和结果状态，然后判断它们条件部分是否冲突，不冲突则可以连接成一个链条
    首先将所有规则看作个体，如果两个个体可以连接，新增一个个体，重复这个过程直到不能连接
    之后大的链条去除小的链条，最后剩下的链条就是需求场景
    input:
    r3: str
    output:
    list[list[dict]]，每个元素是一个需求场景，其中包含多个规则
    """
    rules = mydsl_to_rules(r3)
    links = []
    for rule in rules:
        link = Link(rule)
        links.append(link)
    
    change = True
    index = 0
    while change:
        change = False
        index += 1
        for i in range(len(links)):
            for j in range(i+1, len(links)):
                new_link = links[i].judge_and_link(links[j])
                if new_link is not None and new_link not in links:
                    links.append(new_link)
                    change = True

    del_p = [False for _ in range(len(links))]
    for i in range(len(links)):
        for j in range(len(links)):
            if i == j:
                continue
            if links[j].rules in links[i].rules:
                del_p[j] = True
    for i in range(len(links)-1, -1, -1):
        if del_p[i]:
            links.pop(i)
    return [t.rules for t in links]

