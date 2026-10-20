/* Cytoscape renderers: process DAG, agent topology, rule→requirement→scenario→testcase cascade,
   RAFT meta-model and LLM4Fin state machine. */
(function () {
  cytoscape.use(cytoscapeDagre);
  cytoscape.warnings(false);  // 3.30.x warns about wheelSensitivity on every instance even when it is left at the default

  const TYPE_COLOR = { rule: "#5c7cfa", requirement: "#20c997", scenario: "#fab005", testcase: "#adb5bd" };
  const STATUS_COLOR = {
    unchanged: "#adb5bd", modified: "#f08c00", deleted: "#e03131", added: "#2f9e44", reused: "#5c7cfa",
    remapped: "#7950f2", affected: "#ff922b", discarded: "#ced4da", refined: "#12b886", kept: "#e8590c", unformalized: "#868e96",
  };
  const STATUS_TEXT = {
    unchanged: "未变", modified: "修改", deleted: "删除", added: "新增", reused: "直接复用", remapped: "重映射复用",
    affected: "受影响", discarded: "不可测丢弃", refined: "精化后可测", kept: "人工保留", unformalized: "形式化失败",
  };
  const STEP_COLOR = { pending: "#dee2e6", running: "#4dabf7", ok: "#51cf66", needs_review: "#fcc419", review: "#ffa94d",
    error: "#ff6b6b", skipped: "#ced4da", not_run: "#e9ecef", cancelled: "#ced4da" };
  const PHASE_TEXT = { analyze: "分析", knowledge: "知识工程", formalize: "需求形式化", generate: "场景与用例生成", reuse: "测试复用", verify: "验证" };

  const base = [
    { selector: "node", style: { "font-size": 11, "text-wrap": "wrap", "text-max-width": 140, color: "#1f2430", "text-valign": "center", "text-halign": "center" } },
    { selector: "edge", style: { width: 1.4, "line-color": "#c3c9d8", "target-arrow-color": "#c3c9d8", "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.8 } },
    { selector: ":selected", style: { "border-width": 3, "border-color": "#3b5bdb" } },
  ];

  function make(el, elements, style, layout) {
    if (el._cy) el._cy.destroy();
    const cy = cytoscape({ container: el, elements, style: base.concat(style || []), layout: layout || { name: "dagre", rankDir: "LR", nodeSep: 18, rankSep: 50 },
      minZoom: 0.05, maxZoom: 3 });
    el._cy = cy;
    return cy;
  }

  /* ---- process graph: phases as swim lanes (columns), SOP steps stacked in execution order ---- */
  function processGraph(el, plan, onSelect) {
    if (!plan || !plan.steps) { if (el._cy) el._cy.destroy(); el.innerHTML = '<div class="empty">尚无执行计划</div>'; return null; }
    el.innerHTML = "";
    const els = [];
    const phases = [];
    plan.steps.forEach((s) => { if (!phases.includes(s.phase)) phases.push(s.phase); });
    if (!phases.includes("verify")) phases.push("verify");
    const rows = {};
    const pos = (phase) => { const c = phases.indexOf(phase); const r = (rows[c] = (rows[c] ?? -1) + 1); return { x: c * 250, y: r * 84 }; };
    phases.forEach((p) => els.push({ data: { id: "ph:" + p, label: PHASE_TEXT[p] || p, kind: "phase" } }));
    plan.steps.forEach((s, i) => {
      const sum = s.summary ? Object.entries(s.summary).slice(0, 2).map(([k, v]) => `${k}:${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ") : "";
      els.push({ data: { id: "st:" + i, parent: "ph:" + s.phase, label: `${s.title}\n${s.tool}${sum ? "\n" + sum.slice(0, 34) : ""}`,
        status: s.status || "pending", kind: "step", idx: i, wf: s.workflow }, position: pos(s.phase) });
      if (i > 0) els.push({ data: { id: `e:${i}`, source: "st:" + (i - 1), target: "st:" + i } });
    });
    const vs = plan._verify || "pending";
    els.push({ data: { id: "st:verify", parent: "ph:verify", label: "验证\n确定性检查 + 本地模型抽检", status: vs, kind: "step", idx: -1 }, position: pos("verify") });
    if (plan.steps.length) els.push({ data: { id: "e:v", source: "st:" + (plan.steps.length - 1), target: "st:verify" } });
    const cy = make(el, els, [
      { selector: 'node[kind="phase"]', style: { shape: "round-rectangle", "background-color": "#f8f9fc", "border-color": "#dfe3ee", "border-width": 1,
        label: "data(label)", "text-valign": "top", "text-halign": "center", "font-size": 14, "font-weight": 600, color: "#7a8194", padding: 14 } },
      { selector: 'node[kind="step"]', style: { shape: "round-rectangle", width: 206, height: 64, label: "data(label)", "background-color": (n) => STEP_COLOR[n.data("status")] || "#dee2e6",
        "border-width": 1, "border-color": "#fff", "font-size": 12, "text-max-width": 196 } },
      { selector: 'node[status="running"]', style: { "border-width": 3, "border-color": "#1c7ed6" } },
      { selector: "edge", style: { "curve-style": "taxi", "taxi-direction": "auto", "line-color": "#aab2c5", "target-arrow-color": "#aab2c5" } },
    ], { name: "preset", fit: false });
    // fit by width (columns = phases), grow the box to the content height so step labels stay legible
    const bb = cy.elements().boundingBox();
    const z = Math.max(0.55, Math.min(0.95, (el.clientWidth - 32) / bb.w));
    el.style.height = `${Math.max(220, Math.min(720, bb.h * z + 32))}px`;
    cy.resize();
    cy.zoom(z);
    cy.pan({ x: 16 - bb.x1 * z, y: 16 - bb.y1 * z });
    cy.on("tap", 'node[kind="step"]', (e) => onSelect && onSelect(e.target.data("idx")));
    return cy;
  }

  /* ---- agent topology from graph_spec ---- */
  const NODE_TEXT = { __start__: "开始", __end__: "结束", understand: "理解意图", gather: "补充输入", respond: "直接回答", analyze: "文档分析",
    ask_domain: "询问领域", redetect: "重新识别", lookup: "知识查询", plan: "规划 SOP", execute: "执行工具", on_failure: "失败处理",
    review: "人工复核", apply_review: "应用复核", verify: "验证", report: "报告与记忆" };
  function agentGraph(el, spec, active) {
    if (!spec) return null;
    const els = spec.nodes.map((n) => ({ data: { id: n.id, label: NODE_TEXT[n.id] || n.id, on: (active || []).includes(n.id) ? 1 : 0,
      hitl: ["gather", "ask_domain", "review", "on_failure"].includes(n.id) ? 1 : 0 } }));
    spec.edges.forEach((e, i) => els.push({ data: { id: "a" + i, source: e.source, target: e.target, cond: e.conditional ? 1 : 0 } }));
    return make(el, els, [
      { selector: "node", style: { shape: "round-rectangle", width: 74, height: 30, label: "data(label)", "background-color": "#edf2ff", "border-width": 1, "border-color": "#bac8ff", "font-size": 13 } },
      { selector: "node[hitl=1]", style: { "background-color": "#fff4e6", "border-color": "#ffc078" } },
      { selector: "node[on=1]", style: { "background-color": "#3b5bdb", color: "#fff", "border-color": "#3b5bdb" } },
      { selector: "edge[cond=1]", style: { "line-style": "dashed" } },
    ], { name: "dagre", rankDir: "LR", nodeSep: 12, rankSep: 22, padding: 6 });
  }

  /* ---- cascade trace graph ---- */
  function traceGraph(el, data, handlers) {
    if (!data || !data.nodes || !data.nodes.length) { if (el._cy) el._cy.destroy(); el.innerHTML = '<div class="empty">暂无级联数据</div>'; return null; }
    el.innerHTML = "";
    const els = data.nodes.map((n) => ({ data: { id: n.id, label: shortLabel(n), type: n.type, status: n.status || "", side: n.side || "",
      w: n.type === "testgroup" ? Math.min(60, 22 + 4 * Math.sqrt(n.count || 1)) : 0 } }));
    data.edges.forEach((e, i) => els.push({ data: { id: "t" + i, source: e.source, target: e.target, kind: e.kind } }));
    const big = data.nodes.length > 450;
    const cy = make(el, els, [
      { selector: "node", style: { label: "data(label)", "font-size": big ? 8 : 10, width: 26, height: 26, "background-color": (n) => TYPE_COLOR[n.data("type")] || "#ccc",
        "text-valign": "center", "text-halign": "right", "text-margin-x": 4, "text-max-width": 150, "text-wrap": "ellipsis", "min-zoomed-font-size": 7 } },
      { selector: 'node[type="rule"]', style: { shape: "round-rectangle", width: 38, height: 24 } },
      { selector: 'node[type="requirement"]', style: { shape: "diamond", width: 28, height: 28 } },
      { selector: 'node[type="scenario"]', style: { shape: "hexagon", width: 26, height: 24 } },
      { selector: 'node[type="testcase"]', style: { shape: "ellipse", width: 16, height: 16, "font-size": 9 } },
      { selector: 'node[type="testgroup"]', style: { shape: "round-rectangle", width: "data(w)", height: 20, "background-color": "#adb5bd", "font-size": 10, color: "#495057" } },
      { selector: 'node[status!=""]', style: { "border-width": 3, "border-color": (n) => STATUS_COLOR[n.data("status")] || "#fff" } },
      { selector: 'node[type="testcase"][status!=""], node[type="testgroup"][status!=""]', style: { "background-color": (n) => STATUS_COLOR[n.data("status")] || "#adb5bd", "border-width": 0 } },
      { selector: 'node[status="discarded"], node[status="deleted"], node[status="unformalized"]', style: { opacity: 0.55 } },
      { selector: 'node[side="old"]', style: { "background-opacity": 0.55 } },
      { selector: 'edge[kind="next"]', style: { "line-style": "dashed", "line-color": "#fab005", "target-arrow-color": "#fab005" } },
      { selector: 'edge[kind="conflict"]', style: { "line-color": "#e03131", "target-arrow-color": "#e03131", "line-style": "dotted", width: 2 } },
      { selector: 'edge[kind="evolves"]', style: { "line-color": "#7950f2", "target-arrow-color": "#7950f2", "line-style": "dashed" } },
      { selector: ".dim", style: { opacity: 0.12 } },
      { selector: ".hit", style: { "border-width": 4, "border-color": "#e64980" } },
    ], { name: "dagre", rankDir: "LR", nodeSep: big ? 4 : 10, rankSep: big ? 150 : 170, ranker: "tight-tree" });
    const bb = cy.elements().boundingBox();
    const wz = Math.min(1, (el.clientWidth - 60) / bb.w);
    if (!big && cy.zoom() < wz * 0.9) {  // tall fan-out: fit the cascade levels by width and start at the top; pan down for more
      cy.zoom(wz);
      cy.pan({ x: 20 - bb.x1 * wz, y: 20 - bb.y1 * wz });
    }
    cy.on("tap", "node", (e) => handlers.select && handlers.select(e.target.id()));
    cy.on("dbltap", "node", (e) => handlers.focus && handlers.focus(e.target.id()));
    cy.on("tap", (e) => { if (e.target === cy) cy.elements().removeClass("dim"); });
    cy.on("select", "node", (e) => {
      const n = e.target; const keep = n.predecessors().union(n.successors()).union(n);
      cy.elements().addClass("dim"); keep.removeClass("dim");
    });
    return cy;
  }

  function shortLabel(n) {
    if (n.type === "testcase") return n.label + (n.expected ? "·" + n.expected : "");
    if (n.type === "testgroup") return `${n.label}（正 ${n.positive} / 反 ${n.count - n.positive}）`;
    const t = (n.text || "").replace(/\s+/g, " ");
    if (n.type === "rule" && t) return `${n.label} ${t.slice(0, 14)}`;
    return n.label;
  }

  /* ---- RAFT meta-model: Rule → layers → leaf elements (+ Others) ---- */
  function metaModelGraph(el, mm) {
    if (!mm || !mm.entities) { el.innerHTML = '<div class="empty">无元模型</div>'; return null; }
    el.innerHTML = "";
    const els = [{ data: { id: "Rule", label: "Rule", kind: "core" } }];
    ["Precondition", "Operation", "ExpectedResult"].forEach((l) => { els.push({ data: { id: l, label: l, kind: "layer" } }); els.push({ data: { id: "r-" + l, source: "Rule", target: l } }); });
    Object.entries(mm.entities).forEach(([e, l]) => {
      const v = (mm.votes || {})[e];
      els.push({ data: { id: "e:" + e, label: e + (v ? ` (${v}/${mm.n || "?"})` : ""), kind: "leaf" } });
      els.push({ data: { id: "c-" + e, source: l, target: "e:" + e, rel: "contains" } });
    });
    const others = (mm.others && mm.others.entities) || {};
    const on = Object.keys(others);
    if (on.length) {
      els.push({ data: { id: "others", label: `Others（${on.length} 个低共识要素）`, kind: "others" } });
      els.push({ data: { id: "c-others", source: "Rule", target: "others" } });
    }
    (mm.relations || []).forEach(([a, r, b], i) => {
      const s = ["Rule", "Precondition", "Operation", "ExpectedResult"].includes(a) ? a : "e:" + a;
      const t = ["Rule", "Precondition", "Operation", "ExpectedResult"].includes(b) ? b : "e:" + b;
      if (r !== "contains" && els.some((x) => x.data.id === s) && els.some((x) => x.data.id === t))
        els.push({ data: { id: "x" + i, source: s, target: t, rel: r } });
    });
    return make(el, els, [
      { selector: "node", style: { shape: "round-rectangle", label: "data(label)", width: (n) => 12 + 6.2 * n.data("label").length, height: 24, padding: 6, "font-size": 10, "background-color": "#e7f5ff", "border-width": 1, "border-color": "#a5d8ff" } },
      { selector: 'node[kind="core"]', style: { "background-color": "#3b5bdb", color: "#fff" } },
      { selector: 'node[kind="layer"]', style: { "background-color": "#20c997", color: "#fff", "border-color": "#20c997" } },
      { selector: 'node[kind="others"]', style: { "background-color": "#f1f3f5", "border-style": "dashed", "border-color": "#adb5bd" } },
      { selector: "edge[rel][rel!='contains']", style: { "line-style": "dashed", "line-color": "#fab005", "target-arrow-color": "#fab005", label: "data(rel)", "font-size": 8, "curve-style": "unbundled-bezier" } },
    ], { name: "dagre", rankDir: "LR", nodeSep: 6, rankSep: 60 });
  }

  /* ---- LLM4Fin state machine ---- */
  function stateMachineGraph(el, sm) {
    if (!sm) { el.innerHTML = '<div class="empty">无状态机</div>'; return null; }
    el.innerHTML = "";
    const els = sm.state.map((s) => ({ data: { id: s, label: s } }));
    sm.transition.forEach((t, i) => els.push({ data: { id: "s" + i, source: t.from, target: t.to, label: t.trigger } }));
    return make(el, els, [
      { selector: "node", style: { shape: "round-rectangle", label: "data(label)", width: (n) => 16 + 12 * n.data("label").length, height: 26, padding: 8, "background-color": "#fff9db", "border-width": 1, "border-color": "#ffe066" } },
      { selector: "edge", style: { label: "data(label)", "font-size": 9, "text-background-color": "#fff", "text-background-opacity": 1, "curve-style": "bezier", "loop-direction": "-45deg", "loop-sweep": "40deg" } },
    ], { name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 80 });
  }

  window.Graphs = { processGraph, agentGraph, traceGraph, metaModelGraph, stateMachineGraph, STATUS_COLOR, STATUS_TEXT, STEP_COLOR, PHASE_TEXT, TYPE_COLOR };
})();
