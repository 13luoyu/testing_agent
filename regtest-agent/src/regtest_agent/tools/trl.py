"""TRL (testable requirement language) checks used by RAFT's Generate-Verify-Repair loop."""
from __future__ import annotations

import re

from ..knowledge import canon
from ..llm import strip_fences

OPS = ["not in", "notin", ">=", "<=", "!=", "==", "=", ">", "<", "in", "is"]
CN_OPS = ["不得超过", "不得低于", "最高不超过", "不超过", "不低于", "不大于", "不小于", "不等于", "低于", "超过", "高于", "大于", "小于",
          "不足", "达到", "等于", "以上", "以下", "以内"]
FREE_VALUES = {"成功", "失败", "不成功", "可以", "不可以", "是", "否", "true", "false", "允许", "禁止", "不得", "应当", "须", "必须",
               "success", "failure", "yes", "no"}
FREE_KEYS = {"结果", "结果状态", "状态", "result", "resultstatus", "status", "outcome", "约束", "constraint"}


def normalize(trl: str) -> str:
    t = strip_fences(trl or "").replace("\\n", "\n").strip()
    t = re.sub(r"^\s*(输出|output)\s*[:：]\s*", "", t, flags=re.I)
    return t


def split_rules(trl: str) -> list[dict]:
    """Rule blocks; accepts 'rule N' headers, bare consecutive 'if … then …' blocks and 'and if'."""
    t = re.sub(r"(?i)\brule\s*\d+\s*[:：]?", "\n", normalize(trl))
    chunks = re.split(r"(?i)(?:^|\s)(?:and\s+)?if\s+", t)
    out = []
    for c in chunks[1:]:
        m = re.search(r"(?is)^(.*?)\bthen\b(.*)$", c)
        out.append({"raw": c.strip(), "if": (m.group(1) if m else c).strip(), "then": m.group(2).strip() if m else None})
    if not out and t.strip():
        out.append({"raw": t.strip(), "if": None, "then": None})
    return out


def clauses(part: str) -> list[str]:
    s = re.sub(r"[()（）]", " ", part or "")
    s = re.sub(r"->", " ", s)
    items = re.split(r"(?i)\s+(?:and|or)\s+|\n", s)
    return [re.sub(r"(?i)^\s*not\s+", "", x).strip().rstrip(",;；，") for x in items if x.strip()]


def parse_clause(c: str) -> tuple[str, str, str] | None:
    m = re.match(r"^(.+?)\s*%\s*(\d+(?:\.\d+)?)\s*(==|=)\s*(\d+(?:\.\d+)?)$", c)
    if m:
        return m.group(1).strip(), "%", f"{m.group(2)}=={m.group(4)}"
    for op in OPS:
        if op[0].isalpha():
            m = re.match(rf"^(\S+(?:\s\S+)?)\s+{op}\s+(.+)$", c, re.I)
        else:
            m = re.match(rf"^(.+?)\s*{re.escape(op)}\s*(.+)$", c)
        if m and m.group(1).strip() and m.group(2).strip():
            return m.group(1).strip(), op.lower(), m.group(2).strip().strip("\"'“”")
    for op in CN_OPS:
        m = re.match(rf"^(\S+)\s+{op}\s*(.+)$", c)
        if m:
            return m.group(1).strip(), op, m.group(2).strip()
    return None


DOC_MARK = "\x00doc:"


def _cjk(s: str) -> set[str]:
    return {c for c in s if "\u4e00" <= c <= "\u9fff"}


def _bigrams(s: str) -> list[str]:
    runs = re.findall(r"[\u4e00-\u9fff]+", s)
    return [r[i:i + 2] for r in runs for i in range(len(r) - 1)] or runs


def _nums(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", s or "")


def _num_forms(x: str) -> set[str]:
    """Equivalent spellings of a number: 0.9 <-> 90 (percent), 30 <-> 30.0."""
    f = float(x)
    out = {x, f"{f:g}"}
    for y in (f * 100, f / 100):
        out.add(f"{round(y, 6):g}")
    return out


def grounded(value: str, sources: list[str]) -> bool:
    """CJK value supported by the source rule (character coverage) or the document context (bigram
    coverage); every number must come from the rule itself (document-level numbers belong to other rules)."""
    rule_src = [s for s in sources if s and not s.startswith(DOC_MARK)]
    if _nums(value):
        have = {f for s in rule_src for n in _nums(s) for f in _num_forms(n)} | {"0", "1"}
        if any(n not in have for n in _nums(value)):
            return False
    chars = _cjk(value)
    if not chars:
        return True
    rs = set().union(*(_cjk(s) for s in rule_src)) if rule_src else set()
    if len(chars & rs) / len(chars) >= 0.5:
        return True
    doc = "".join(s[len(DOC_MARK):] for s in sources if s and s.startswith(DOC_MARK))
    bg = _bigrams(value)
    return bool(doc and bg) and sum(b in doc for b in bg) / len(bg) >= 0.6


def check(trl: str, symbols: set[str], labels: set[str], sources: list[str]) -> dict:
    """Localized diagnostics. errors trigger repair; warnings are recorded only."""
    errors, warnings, n = [], [], 0
    sym_low = {s.lower() for s in symbols}
    blocks = split_rules(trl)
    if not blocks:
        return {"ok": False, "errors": ["输出为空或不包含任何规则"], "warnings": [], "rules": 0}
    for i, b in enumerate(blocks, 1):
        if b["then"] is None:
            errors.append(f"rule {i}: 缺少 if ... then ... 结构：{b['raw'][:60]}")
            continue
        n += 1
        if not b["then"].strip():
            errors.append(f"rule {i}: then 部分为空")
        for part, name in ((b["if"], "if"), (b["then"], "then")):
            cs = clauses(part)
            if not cs:
                errors.append(f"rule {i}: {name} 部分为空")
            for c in cs:
                if re.search(r"(?i)\bis\s+(not\s+)?in\b|\bcontains\b|\bnot\s+contains\b", c):
                    errors.append(f"rule {i}: 子句「{c[:40]}」使用了未定义的比较符（IS IN / CONTAINS），请改用 in / notin / =")
                    continue
                p = parse_clause(c)
                if p is None:
                    errors.append(f"rule {i}: 子句「{c[:40]}」不是 key op value 三元组（op 只能是 =, !=, >, >=, <, <=, in, notin）")
                    continue
                k, op, v = p
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k):
                    if k.lower() not in sym_low and canon(k).lower() not in sym_low and k.lower() not in FREE_KEYS:
                        errors.append(f"rule {i}: 键「{k}」不在需求表示的领域符号中（可用：{', '.join(sorted(symbols))[:200]}）")
                elif not _cjk(k):
                    errors.append(f"rule {i}: 键「{k[:30]}」不是单个领域符号")
                    continue
                elif k not in labels and k.lower() not in FREE_KEYS:
                    warnings.append(f"rule {i}: 中文键「{k}」不在符号标签中")
                if k.lower() in FREE_KEYS or v.lower() in FREE_VALUES:
                    continue
                if not grounded(v, sources):
                    errors.append(f"rule {i}: 值「{v[:30]}」在原文中找不到依据（禁止造词）")
    return {"ok": not errors and n > 0, "errors": errors[:12], "warnings": warnings[:12], "rules": n}


def blocks_for_generation(trl_post: str) -> list[str]:
    """Split a post-processed TRL ('rule k\\nif ...\\nthen ...') into single-rule blocks."""
    out, cur = [], []
    for line in (trl_post or "").split("\n"):
        if line.startswith("rule ") and cur:
            out.append("\n".join(cur))
            cur = []
        if line.strip():
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return [b for b in out if "\nif " in "\n" + b and "\nthen " in "\n" + b]
