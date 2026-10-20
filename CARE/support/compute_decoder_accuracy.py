import copy
import os
import json
from nltk.translate.bleu_score import sentence_bleu
from rouge import Rouge
import ctypes
import math
from functools import reduce
import warnings
warnings.filterwarnings("ignore")
import sys
sys.setrecursionlimit(100000)  # 设置最大递归深度为100000



def compute_char_wise_accuracy(predictions, labels):
    char_wise_accuracy = []
    for pred, label in zip(predictions, labels):
        if pred == "":
            char_wise_accuracy.append(0)
            continue
        
        pred, label = list(pred), list(label)
        count = 0
        pred_idx = 0
        for label_char in label:
            last_pred_idx = pred_idx
            find = False
            while pred_idx < len(pred):
                if pred[pred_idx] == label_char:
                    count += 1
                    pred_idx += 1
                    find = True
                    break
                else:
                    pred_idx += 1
            if not find:
                pred_idx = last_pred_idx

        char_wise_accuracy.append(count / len(label))
    return sum(char_wise_accuracy) / len(char_wise_accuracy)


def compute_word_wise_accuracy(predictions, labels):
    word_wise_accuracy = []
    for pred, label in zip(predictions, labels):

        label_words = label.replace("\n", " ").split(" ")
        pred_words = pred.replace("\n", " ").split(" ")
        count = 0
        pred_idx = 0
        for label_word in label_words:
            last_pred_idx = pred_idx
            find = False
            while pred_idx < len(pred_words):
                if pred_words[pred_idx] == label_word:
                    count += 1
                    pred_idx += 1
                    find = True
                    break
                else:
                    pred_idx += 1
            if not find:
                pred_idx = last_pred_idx

        word_wise_accuracy.append(count / len(label_words))

    return sum(word_wise_accuracy) / len(word_wise_accuracy)



def compute_clause_wise_precision_recall_r1(predictions, labels):
    clause_wise_precision = []
    clause_wise_recall = []
    for pred, label in zip(predictions, labels):
        pred_clause, label_clause = [], []
        for line in pred.split("\n"):
            if "if" in line or "then" in line:
                line = " ".join(line.split(" ")[1:])
                pred_clause.extend(line.split(" and "))
        for line in label.split("\n"):
            if "if" in line or "then" in line:
                line = " ".join(line.split(" ")[1:])
                label_clause.extend(line.split(" and "))
        count = 0
        pred_idx = 0
        for label_word in label_clause:
            last_pred_idx = pred_idx
            find = False
            while pred_idx < len(pred_clause):
                if pred_clause[pred_idx] == label_word:
                    count += 1
                    pred_idx += 1
                    find = True
                    break
                else:
                    pred_idx += 1
            if not find:
                pred_idx = last_pred_idx
        clause_wise_recall.append(count / len(label_clause))
        clause_wise_precision.append(count / len(pred_clause))
        p, r = sum(clause_wise_precision) / len(clause_wise_precision), sum(clause_wise_recall) / len(clause_wise_recall)
        f =  2 * p * r / (p+r) if (p+r) > 0 else 0
    return p, r, f



def compute_req_wise_accuracy(predictions, labels):
    req_wise_accuracy = []
    for pred, label in zip(predictions, labels):
        pred_req, label_req = [], []
        s = ""
        for line in pred.split("\n"):
            if s != "" and "rule" in line:
                pred_req.append(s)
                s = line
            else:
                s += line
        pred_req.append(s)
        s = ""
        for line in label.split("\n"):
            if s != "" and "rule" in line:
                label_req.append(s)
                s = line
            else:
                s += line
        label_req.append(s)
        count = 0
        pred_idx = 0
        for label_word in label_req:
            last_pred_idx = pred_idx
            find = False
            while pred_idx < len(pred_req):
                if pred_req[pred_idx] == label_word:
                    count += 1
                    pred_idx += 1
                    find = True
                    break
                else:
                    pred_idx += 1
            if not find:
                pred_idx = last_pred_idx
        req_wise_accuracy.append(count / len(label_req))
    return sum(req_wise_accuracy) / len(req_wise_accuracy)



def compute_cumulative_bleu(predictions, labels):
    """
    BLEU（Bilingual Evaluation Understudy）是一种用于评估机器翻译质量的指标，它的设计灵感来源于信息检索中的精度指标。BLEU的原理相对简单，它通过比较机器翻译的输出与人工翻译的参考译文之间的重叠度来评分。以下是BLEU计算的基本步骤和原理：
    
    1、匹配（Matching）：BLEU首先会检查机器翻译的输出中出现了哪些单词或短语（n-gram，其中n可以是1、2、3、4等，分别对应单词、双词短语、三词短语等），并计算它们在参考译文中出现的次数。
    2、精度（Precision）：对于每个n-gram，BLEU计算一个精度分数，即该n-gram在机器翻译输出中出现的次数与在参考译文中出现的最大次数的比值(accuracy)。这个步骤是对每个n-gram分别进行的。
    3、权重和几何平均（Weighted Geometric Mean）：BLEU将不同长度的n-gram的精度分数进行加权，并计算它们的几何平均。通常，BLEU会给更长的n-gram更高的权重，因为它们更能反映翻译的准确性。
    5、BP（Brevity Penalty）：BLEU还会对机器翻译输出的长度进行惩罚。如果机器翻译的输出比参考译文短，那么会应用一个长度惩罚因子BP，BP=e^(1-r/c)，其中r为参考译文长度，c为预测值长度。BP的目的是惩罚那些过短的翻译，因为它们可能遗漏了重要的信息。
    6、最终分数：最终的BLEU分数是修正的精度和BP的乘积。这个分数的范围在0到1之间，1表示完美的匹配，而0表示完全没有匹配。
    
    BLEU的主要优点是它简单、快速，并且可以大规模应用。然而，它也受到了一些批评，因为它不考虑语言的语法和语义正确性，也不能很好地处理语言的灵活性和多样性。此外，BLEU对于不同的n-gram给予相同的权重，这可能不适用于所有情况，因为不同的n-gram在翻译质量评估中的重要性可能不同。尽管如此，BLEU仍然是机器翻译领域最常用的自动评估指标之一。
    """
    cumulative_bleu = []
    for pred, label in zip(predictions, labels):
        if pred == "":
            cumulative_bleu.append(0)
            continue
        pred = pred.replace("\n", " ").split(" ")
        label = label.replace("\n", " ").split(" ")
        bleu = sentence_bleu([label], pred, weights=(0.33, 0.33, 0.33, 0))
        cumulative_bleu.append(bleu)
    return sum(cumulative_bleu) / len(cumulative_bleu)


def compute_score(predictions, labels):
    """
    打分：满分为1，一条规则包含序号、条件、结果、or关系4个部分，规定:
    部分        要求                    分数
    序号        序号格式正确            0.05
    条件/结果    格式正确               0.05
                每个条件属性和值正确     0.4
                每个结果属性和值正确     0.4
    or关系      关系正确                0.1
    """
    score_setting = [0.05, 0.05, 0.4, 0.4, 0.1]
    scores = []
    for pred, label in zip(predictions, labels):
        if pred == "":
            scores.append(0)
            continue
        score = 0

        # 序号
        # 检查label中的每个rule {id}是否在pred中出现
        max_rule_id = 1
        while f"rule {max_rule_id}" in label:
            max_rule_id += 1
        wrong_rule_id = False
        for rule_id in range(1, max_rule_id):
            if "rule" + str(rule_id) not in pred:
                wrong_rule_id = True
                break
        if not wrong_rule_id:
            score += score_setting[0]
        
        # 条件/结果
        # 先校验格式，对条件和结果子句，查看是否有if、then、and、or关键词关联3元组
        pred_cp = copy.deepcopy(pred)
        pred = pred.replace("\n", " ").split(" ")
        format_correct = True
        i = 0
        while i < len(pred) and pred[i] != "if":
                i += 1
        while i < len(pred):
            if pred[i] in ["if", "then", "and", "or"]:
                i += 4
            else:
                format_correct = False
                break
        if format_correct:
            score += score_setting[1]
        
        # 校验每个条件属性和值是否正确
        label_cp = copy.deepcopy(label)
        label = label.replace("\n", " ").split(" ")
        label_if_cons, label_then_cons = [], []
        i = 0
        while i < len(label) and label[i] != "if":
            i += 1
        while i < len(label) and label[i] == "then":
            label_if_cons.append(" ".join(label[i+1:i+4]))
            i += 4
        while i < len(label) and label[i] != "or":
            label_then_cons.append(" ".join(label[i+1:i+4]))
            i += 4
        # pred的格式千奇百怪，所以只能检查label中的if和then是否在pred中出现
        if_cover, then_cover = 0, 0
        for con in label_if_cons:
            if con in pred_cp:
                if_cover += 1
        for con in label_then_cons:
            if con in pred_cp:
                then_cover += 1
        if len(label_if_cons) == 0:
            score += score_setting[2]
        else:
            score += score_setting[2] * if_cover / len(label_if_cons)
        if len(label_then_cons) == 0:
            score += score_setting[3]
        else:
            score += score_setting[3] * then_cover / len(label_then_cons)

        # 校验or relation是否正确
        if "or relation" not in label_cp and "or relation" not in pred_cp:
            score += score_setting[4]
        elif "or relation" in label_cp and "or relation" in pred_cp:
            label_or_relation = label_cp.split("or relation")[-1].strip()[1:]
            pred_or_relation = pred_cp.split("or relation")[-1].strip()
            i = 0
            while len(pred_or_relation) > i and not pred_or_relation[i].isdigit():
                i += 1
            pred_or_relation = pred_or_relation[i:]
            if pred_or_relation == label_or_relation:
                score += score_setting[4]
        
        scores.append(score)

    return sum(scores) / len(scores)


def compute_rouge_f1(predictions, labels):
    # metrics包括rouge-1、rouge-2、rouge-l。
    # rouge-1等除了计算accuracy，还计算recall和f1 score。
    # rouge-l将n-gram的precision优化为公共子序列计算。
    r = Rouge(metrics=["rouge-l"])
    rouge_scores = []
    for pred, label in zip(predictions, labels):
        if pred == "":
            rouge_scores.append(0)
            continue
        rouge_score = r.get_scores(pred, label)
        # F1 score
        rouge_scores.append(rouge_score[0]['rouge-l']['f'])
    return sum(rouge_scores) / len(rouge_scores)





def compute_acc(predictions, labels):
    # char_wise_accuracy = compute_char_wise_accuracy(predictions, labels)
    # word_wise_accuracy = compute_word_wise_accuracy(predictions, labels)
    clause_wise_accuracy, clause_wise_recall, clause_wise_f1 = compute_clause_wise_precision_recall_r1(predictions, labels)
    # req_wise_accuracy = compute_req_wise_accuracy(predictions, labels)
    bleu = compute_cumulative_bleu(predictions, labels)
    rouge_f1 = compute_rouge_f1(predictions, labels)
    score = compute_score(predictions, labels)

    return clause_wise_accuracy, clause_wise_recall, clause_wise_f1, bleu, rouge_f1, score







if __name__ == "__main__":
    ...