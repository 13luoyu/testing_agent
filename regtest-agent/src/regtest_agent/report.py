"""Self-contained HTML quality report for a generation deliverable (no external assets)."""
from __future__ import annotations

import html
from collections import Counter
from pathlib import Path


def _bar(label: str, value: int, total: int, color: str) -> str:
    pct = round(100 * value / max(1, total))
    return (f'<div class="bar"><span class="bl">{html.escape(label)}</span>'
            f'<span class="bt"><i style="width:{pct}%;background:{color}"></i></span>'
            f'<span class="bv">{value}</span></div>')


def write_report(d: dict, out: Path) -> Path:
    s = d["stats"]
    prov = d.get("source_provenance", {})
    flat = [tc for g in d["testcases"] for tc in g]
    funnel = [("规则句", s["rule_sentences"], "#868e96"), ("可测试规则", s["testable_rules"], "#5c7cfa"),
              ("形式化需求", s["requirements_r2"], "#20c997"), ("业务场景", s["scenarios"], "#fab005"),
              ("测试用例", s["testcases"], "#e64980")]
    top = max(x[1] for x in funnel)
    concern = Counter(tc.get("测试关注点", "—") for tc in flat).most_common(10)
    sample = flat[:40]
    keys = list(dict.fromkeys(k for tc in sample for k in tc if k not in ("testid", "rule")))[:8]

    mi = d.get("minimize")
    rows = "".join(
        "<tr>" + f'<td class="mono">{html.escape(tc.get("rule",""))}</td>'
        + "".join(f'<td>{html.escape(str(tc.get(k,"")))}</td>' for k in keys)
        + f'<td class="{"ok" if tc.get("结果") in ("成功","可以") else "no"}">{html.escape(str(tc.get("结果","")))}</td></tr>'
        for tc in sample)

    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>测试用例质量报告 · {html.escape(prov.get('title') or prov.get('file',''))}</title>
<style>
:root{{--bg:#0f1221;--card:#191d33;--line:#2a3050;--fg:#e9ecf5;--mut:#9aa3c0;--ac:#6c8cff}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#0c0f1c,#131732);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:28px;margin:0 0 6px}}.sub{{color:var(--mut);margin-bottom:28px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:18px 0}}
.card h2{{font-size:17px;margin:0 0 16px;color:#cfd6f5}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:14px}}
.kpi .n{{font-size:30px;font-weight:700;color:var(--ac)}}.kpi .l{{color:var(--mut);font-size:13px}}
.bar{{display:flex;align-items:center;gap:12px;margin:9px 0}}.bl{{width:96px;color:var(--mut);font-size:13px;text-align:right}}
.bt{{flex:1;height:14px;background:#0d1024;border-radius:8px;overflow:hidden}}.bt i{{display:block;height:100%}}.bv{{width:56px;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}}
th{{color:var(--mut);font-weight:600}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#aeb8e6}}
td.ok{{color:#51cf66}}td.no{{color:#ff8787}}.tag{{display:inline-block;background:#232846;border:1px solid var(--line);border-radius:999px;padding:2px 10px;margin:3px 4px 0 0;font-size:12px;color:var(--mut)}}
.prov{{font-size:13px;color:var(--mut)}}.prov a{{color:var(--ac)}}.note{{color:var(--mut);font-size:13px;margin-top:8px}}
.wrap2{{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:10px}}
.pill{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;background:#1c3a2a;color:#51cf66;border:1px solid #2b6}}
</style></head><body><div class="wrap">
<h1>测试用例质量报告</h1>
<div class="sub">{html.escape(prov.get('title') or prov.get('file',''))} · <span class="pill">{html.escape(d.get('backend',''))}</span></div>

<div class="card"><h2>关键指标</h2><div class="kpi">
<div><div class="n">{s['testcases']}</div><div class="l">测试用例</div></div>
<div><div class="n">{s['positive']}/{s['negative']}</div><div class="l">正例 / 反例</div></div>
<div><div class="n">{s['scenarios']}</div><div class="l">业务场景</div></div>
<div><div class="n">{s['requirements_r2']}</div><div class="l">形式化需求</div></div>
<div><div class="n">{s['testable_rules']}</div><div class="l">可测试规则</div></div>
<div><div class="n">{s['conflicts']}</div><div class="l">一致性冲突</div></div>
</div></div>

<div class="card"><h2>生成漏斗（规则 → 需求 → 场景 → 用例）</h2>
{"".join(_bar(l, v, top, c) for l, v, c in funnel)}
<div class="note">由 {s['rule_sentences']} 条规则句经 mengzi 句分类筛出 {s['testable_rules']} 条可测试规则，形式化为 {s['requirements_r2']} 条结构化需求，结合状态机展开 {s['scenarios']} 个业务场景，z3 求解生成 {s['testcases']} 条正/反例用例。</div></div>

{(f'''<div class="card"><h2>测试精简（成对覆盖）</h2>
<div class="kpi"><div><div class="n">{mi['before']}</div><div class="l">精简前</div></div>
<div><div class="n">{mi['after']}</div><div class="l">精简后</div></div>
<div><div class="n">{round(mi['reduction']*100)}%</div><div class="l">缩减</div></div>
<div><div class="n">{mi['groups_reduced']}</div><div class="l">精简的用例组</div></div></div>
<div class="note">对每个因枚举笛卡尔积而膨胀的用例组，选取覆盖全部观测到的取值对（2-wise）且保留正/反例的最小子集，不新造任何组合。</div></div>''') if mi else ''}

<div class="card"><h2>测试关注点分布</h2>
{"".join(f'<span class="tag">{html.escape(str(k))} · {v}</span>' for k,v in concern)}</div>

<div class="card"><h2>用例样例（前 {len(sample)} 条，共 {s['testcases']} 条）</h2>
<div class="wrap2"><table><thead><tr><th>规则</th>{"".join(f"<th>{html.escape(k)}</th>" for k in keys)}<th>结果</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>

<div class="card"><h2>来源与出处</h2><div class="prov">
{"".join(f"<div><b>{html.escape(k)}</b>：" + (f'<a href="{html.escape(str(v))}">{html.escape(str(v))}</a>' if str(v).startswith('http') else html.escape(str(v))) + "</div>" for k,v in prov.items() if v)}
</div><div class="note">生成器：{html.escape(d.get('generated_by',''))} · 耗时 {d.get('seconds')}s</div></div>

</div></body></html>"""
    out.write_text(doc, encoding="utf-8")
    return out
