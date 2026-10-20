/* RegTest Agent UI: chat with HITL cards, live process view (SSE), cascade graph, artifacts, knowledge, memory. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  const fmtT = (t) => (t ? new Date(t * 1000).toLocaleString("zh-CN", { hour12: false }) : "");
  const secs = (x) => (x == null ? "" : x < 60 ? `${(+x).toFixed(1)}s` : `${(x / 60).toFixed(1)}min`);
  const J = (x) => (typeof x === "string" ? x : JSON.stringify(x, null, 1));

  async function api(path, opt = {}) {
    const r = await fetch(path, opt);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
    const ct = r.headers.get("content-type") || "";
    return ct.includes("json") ? r.json() : r.text();
  }
  const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

  const S = { tid: null, thread: null, es: null, lastSeq: 0, run: null, runs: [], meta: null, plan: null, live: {}, files: [],
    tab: "process", traceFocus: null, traceCy: null, reqKind: "rule", testsPage: 0, activeNodes: [] };

  /* ------------------------------------------------------------ threads -- */
  async function loadThreads() {
    const ts = await api("/api/threads");
    const ul = $("#threads");
    ul.innerHTML = ts.map((t) => `<li data-id="${t.id}" class="${t.id === S.tid ? "active" : ""}"><span class="dot ${t.status}"></span>
      <span class="t" title="${esc(t.title)}">${esc(t.title)}</span><span class="del" data-del="${t.id}">✕</span></li>`).join("") || '<li class="muted">还没有会话</li>';
    return ts;
  }
  $("#threads").addEventListener("click", async (e) => {
    const del = e.target.dataset.del;
    if (del) { e.stopPropagation(); if (confirm("删除该会话及其任务记录？")) { await api(`/api/threads/${del}`, { method: "DELETE" }); if (del === S.tid) S.tid = null; await loadThreads(); if (!S.tid) renderEmpty(); } return; }
    const li = e.target.closest("li[data-id]");
    if (li) openThread(li.dataset.id);
  });
  $("#newThread").onclick = async () => { const t = await post("/api/threads"); await loadThreads(); openThread(t.id); };

  async function openThread(tid) {
    S.tid = tid; S.live = {}; S.plan = null; S.run = null;
    if (S.es) { S.es.close(); S.es = null; }
    const th = await api(`/api/threads/${tid}`);
    S.thread = th; S.lastSeq = th.last_seq || 0;  // the snapshot already reflects every event up to last_seq
    $("#threadTitle").textContent = th.title; $("#threadTitle").contentEditable = "true";
    renderMessages(th.messages, th.pending);
    setStatus(th.busy ? "running" : th.status);
    await loadThreads();
    S.runs = th.runs;
    renderRunSelect();
    if (th.runs.length) await selectRun(th.runs[0].id); else renderRunEmpty();
    if (th.busy && S.run && S.run.plan) S.plan = { ...S.run.plan, run_id: S.run.id };
    connect();
  }
  $("#threadTitle").addEventListener("blur", async () => {
    if (!S.tid) return;
    await api(`/api/threads/${S.tid}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: $("#threadTitle").textContent.trim() }) });
    loadThreads();
  });

  function setStatus(st) {
    const map = { running: ["run", "执行中"], waiting: ["warn", "等待你的回答"], idle: ["", "空闲"] };
    const [cls, txt] = map[st] || ["", st || ""];
    $("#threadStatus").innerHTML = st ? `<span class="tag ${cls}">${txt}</span>` : "";
    $("#stopBtn").classList.toggle("hidden", st !== "running");
    $("#sendBtn").disabled = st === "running";
  }
  $("#stopBtn").onclick = () => S.tid && post(`/api/threads/${S.tid}/stop`);

  /* ---------------------------------------------------------------- SSE -- */
  function connect() {
    const tid = S.tid;
    const es = new EventSource(`/api/threads/${tid}/events?after=${S.lastSeq}`);
    S.es = es;
    const on = (type, fn) => es.addEventListener(type, (m) => { if (S.tid !== tid || !m.data) return; const e = JSON.parse(m.data); S.lastSeq = e.seq; fn(e.data, e); });
    on("message", (d) => { if (!$(`[data-mid="${d.id}"]`)) appendMessage(d); });
    on("status", (d) => { setStatus(d.status); if (d.status !== "running") { renderLive(); refreshAfterRun(d.run_id); } else renderLive(); loadThreads(); });
    on("phase", (d) => { S.live.phase = d; if (d.phase === "verify" && d.status === "done") { S.live.verify = d; if (S.plan) S.plan._verify = d.verdict; } renderLive(); renderPhases(); if (d.phase === "verify" && d.status === "done") renderVerify(d); });
    on("plan", (d) => { S.plan = d; S.live.progress = {}; ensureRun(d.run_id, d.workflow); renderPlan(); renderLive(); });
    on("step", (d) => {
      if (!S.plan || S.plan.run_id !== d.run_id) return;
      const i = S.plan.steps.findIndex((s) => s.id === d.id);
      if (i >= 0) S.plan.steps[i] = { ...S.plan.steps[i], ...d };
      S.live.step = d; renderPlan(); renderLive();
    });
    on("progress", (d) => { S.live.progress = S.live.progress || {}; S.live.progress[d.step] = d; renderLive(); });
    on("node", (d) => { S.activeNodes = [d.node]; if (S.tab === "process" && S.meta) Graphs.agentGraph($("#agentGraph"), S.meta.graph, S.activeNodes); });
    on("error", (d) => console.warn("agent error", d.error));
    es.onerror = () => { es.close(); setTimeout(() => S.tid && S.es === es && connect(), 2000); };
  }

  /* ----------------------------------------------------------- messages -- */
  function renderMessages(msgs, pending) {
    const box = $("#messages");
    box.innerHTML = msgs.length ? "" : '<div class="empty">上传规则文档并描述你的需求。我会识别领域、查询知识，按 LLM4Fin / RAFT / CARE 的原始流程规划并执行。</div>';
    msgs.forEach((m) => appendMessage(m, pending));
  }
  function appendMessage(m, pending) {
    const box = $("#messages");
    if ($(".empty", box)) box.innerHTML = "";
    const div = document.createElement("div");
    div.className = `msg ${m.role}`; div.dataset.mid = m.id;
    div.innerHTML = `<div class="bubble">${md(m.content)}${(m.cards || []).map((c) => card(c, m)).join("")}</div><div class="meta">${fmtT(m.created)}</div>`;
    const live = $("#liveBox"); if (live) box.insertBefore(div, live); else box.appendChild(div);
    bindCard(div);
    box.scrollTop = box.scrollHeight;
  }

  function card(c) {
    if (c.type === "files") return `<div class="files">${c.files.map((f) => `<span class="file">📄 ${esc(f.name)}</span>`).join("")}</div>`;
    if (c.type === "result") {
      const v = { pass: ["ok", "通过"], needs_review: ["warn", "需人工复核"], fail: ["err", "未通过"], cancelled: ["", "已取消"] }[c.verdict] || ["", c.verdict];
      return `<div class="card result"><div class="card-title">📊 任务结果 <span class="tag ${v[0]}">${v[1]}</span><span class="tag">${esc(c.workflow)}</span></div>
        <div class="opts"><button class="btn small" data-open-run="${c.run_id}" data-tab="process">流程</button><button class="btn small" data-open-run="${c.run_id}" data-tab="trace">级联图</button>
        <button class="btn small" data-open-run="${c.run_id}" data-tab="tests">测试用例</button><a class="btn small" href="/api/runs/${c.run_id}/tests?fmt=csv">下载 CSV</a></div></div>`;
    }
    if (c.type === "error") return `<div class="card error"><div class="card-title">⚠️ 异常</div><pre>${esc(c.trace || "")}</pre></div>`;
    if (c.type === "question") return questionCard(c);
    return "";
  }

  function questionCard(c) {
    const answered = S.thread && S.thread.pending ? S.thread.pending.id !== c.interrupt_id : true;
    const dis = answered ? "disabled" : "";
    let body = "";
    if (c.kind === "need_inputs") {
      body = `<div>缺少：${c.missing.map((x) => `<span class="tag warn">${esc(x)}</span>`).join("")}</div>
        ${c.files && c.files.length ? `<div class="muted" style="margin-top:4px">已识别：${c.files.map((f) => `${esc(f.name)} → ${roleText(f.role)}`).join("；")}</div>` : ""}
        <div class="muted" style="margin-top:4px">在下方输入框附上文件后发送即可继续。</div>`;
    } else if (c.kind === "need_domain") {
      body = `<div class="opts">${["金融证券", "道路交通", "电力并网"].map((d) => `<button class="btn small" ${dis} data-answer='${JSON.stringify({ text: d })}'>${d}</button>`).join("")}</div>
        <div class="muted" style="margin-top:4px">也可以直接在输入框写领域名称（新领域会先执行 RAFT 知识工程）。</div>`;
    } else if (c.kind === "review_untestable") {
      body = `<div class="review-list">${c.items.map((x) => `<label class="review-item"><input type="checkbox" value="${esc(x.rid)}" ${dis}>
        <div><b>${esc(x.rid)}</b> ${esc(x.rule).slice(0, 140)}<div class="mono muted">${esc(x.trl).slice(0, 220)}</div>
        <div>${(x.violations || []).map((v) => `<span class="tag err">${esc(v)}</span>`).join("")}<span class="muted">${esc(x.reason).slice(0, 160)}</span></div></div></label>`).join("")}</div>
        <div class="opts"><button class="btn small" ${dis} data-answer='{"choice":"drop"}'>全部丢弃（全自动 RAFT）</button>
        <button class="btn small" ${dis} data-answer='{"choice":"keep_all"}'>全部保留待复核</button>
        <button class="btn small primary" ${dis} data-keep>按勾选保留</button></div>`;
    } else if (c.kind === "step_failed") {
      body = `<pre>${esc(c.error)}</pre><div class="opts">${(c.options || []).map((o) => `<button class="btn small" ${dis} data-answer='${JSON.stringify({ choice: o.value, label: o.label })}'>${esc(o.label)}</button>`).join("")}</div>`;
    }
    return `<div class="card question" data-iid="${c.interrupt_id}"><div class="card-title">🙋 ${answered ? "已回答" : "需要你的确认"}</div>${body}</div>`;
  }
  const roleText = (r) => ({ main: "待测文档", old_rules: "原规则", new_rules: "新规则", old_tests: "原测试用例", other: "其他" }[r] || "未识别");

  function bindCard(div) {
    div.querySelectorAll("[data-answer]").forEach((b) => (b.onclick = () => answer(JSON.parse(b.dataset.answer))));
    div.querySelectorAll("[data-keep]").forEach((b) => (b.onclick = () => {
      const keep = [...b.closest(".card").querySelectorAll("input[type=checkbox]:checked")].map((x) => x.value);
      answer({ choice: "custom", keep, label: `保留 ${keep.length} 条：${keep.join("、") || "无"}` });
    }));
    div.querySelectorAll("[data-open-run]").forEach((b) => (b.onclick = async () => { await selectRun(b.dataset.openRun); switchTab(b.dataset.tab); }));
  }
  async function answer(a) {
    try { await post(`/api/threads/${S.tid}/resume`, a); S.thread.pending = null; document.querySelectorAll(".card.question button, .card.question input").forEach((x) => (x.disabled = true)); }
    catch (e) { alert(e.message); }
  }

  /* live progress box under the chat */
  function renderLive() {
    const box = $("#messages");
    let el = $("#liveBox");
    const running = $("#threadStatus").textContent.includes("执行中");
    if (!running) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement("div"); el.id = "liveBox"; el.className = "live"; box.appendChild(el); }
    const p = S.plan;
    let html = "";
    const ph = S.live.phase;
    if (ph) html += `<div class="row">🧭 阶段：<b>${Graphs.PHASE_TEXT[ph.phase] || ph.phase}</b> ${ph.status === "running" ? '<span class="tag run">进行中</span>' : ""}</div>`;
    if (p) {
      const done = p.steps.filter((s) => ["ok", "needs_review", "skipped", "error"].includes(s.status)).length;
      html += `<div class="row">📋 ${esc(p.title)}：${done}/${p.steps.length} 步 <div class="bar"><i style="width:${(100 * done) / p.steps.length}%"></i></div></div>`;
      const cur = p.steps.find((s) => s.status === "running");
      if (cur) {
        const pr = (S.live.progress || {})[cur.id];
        html += `<div class="row">⚙️ ${esc(cur.title)} <span class="mono muted">${esc(cur.tool)}</span></div>`;
        if (pr && pr.total) html += `<div class="row"><span class="muted">${esc(pr.msg || "")}</span><div class="bar"><i style="width:${(100 * pr.done) / pr.total}%"></i></div><span class="mono">${pr.done}/${pr.total}</span></div>`;
      }
    }
    el.innerHTML = html || "思考中…";
    box.scrollTop = box.scrollHeight;
  }

  /* ----------------------------------------------------------- composer -- */
  $("#fileInput").onchange = (e) => { S.files.push(...e.target.files); e.target.value = ""; renderAttach(); };
  function renderAttach() {
    $("#attachments").innerHTML = S.files.map((f, i) => `<span class="file">📄 ${esc(f.name)} <span class="x" data-i="${i}">✕</span></span>`).join("");
    $("#attachments").querySelectorAll(".x").forEach((x) => (x.onclick = () => { S.files.splice(+x.dataset.i, 1); renderAttach(); }));
  }
  document.querySelectorAll(".hints .chip").forEach((c) => (c.onclick = () => { $("#input").value = c.dataset.text; $("#input").focus(); }));
  $("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); } });
  $("#composer").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("#input").value.trim();
    if (!text && !S.files.length) return;
    if (!S.tid) { const t = await post("/api/threads"); await openThread(t.id); }
    const fd = new FormData();
    fd.append("text", text);
    S.files.forEach((f) => fd.append("files", f));
    $("#sendBtn").disabled = true;
    try { await api(`/api/threads/${S.tid}/messages`, { method: "POST", body: fd }); $("#input").value = ""; S.files = []; renderAttach(); if (S.thread) S.thread.pending = null; }
    catch (err) { alert(err.message); $("#sendBtn").disabled = false; }
  };

  /* --------------------------------------------------------------- runs -- */
  function renderRunSelect() {
    $("#runSelect").innerHTML = S.runs.map((r) => `<option value="${r.id}">${r.id} · ${r.workflow || "?"} · ${r.domain || ""} · ${r.status}</option>`).join("") || "<option>暂无任务</option>";
    if (S.run) $("#runSelect").value = S.run.id;
  }
  $("#runSelect").onchange = (e) => selectRun(e.target.value);
  function ensureRun(rid, wf) {
    if (!S.runs.find((r) => r.id === rid)) { S.runs.unshift({ id: rid, workflow: wf, status: "running" }); renderRunSelect(); }
    if (!S.run || S.run.id !== rid) { S.run = { id: rid, workflow: wf, plan: S.plan }; $("#runSelect").value = rid; }
  }
  async function selectRun(rid) {
    const r = await api(`/api/runs/${rid}`);
    S.run = r; S.plan = { ...r.plan, run_id: rid, _verify: r.verification ? r.verification.verdict : undefined }; S.traceFocus = null; S.traceOffset = 0; S.tracePages = [];
    $("#runSelect").value = rid;
    $("#runInfo").innerHTML = `<span class="tag">${esc(r.workflow)}</span><span class="tag">${esc(r.domain)}</span><span class="tag ${r.status === "pass" ? "ok" : r.status === "fail" ? "err" : r.status === "running" ? "run" : "warn"}">${esc(r.status)}</span>
      <span class="muted">${fmtT(r.started)}${r.ended ? " · 用时 " + secs(r.ended - r.started) : ""}</span>`;
    renderTab();
  }
  async function refreshAfterRun(rid) {
    if (!S.tid) return;
    const th = await api(`/api/threads/${S.tid}`);
    S.thread = th; S.runs = th.runs; renderRunSelect();
    if (th.pending) { const last = th.messages[th.messages.length - 1]; if (last) { const el = $(`[data-mid="${last.id}"]`); if (el) el.remove(); appendMessage(last); } }
    if (rid || S.run) await selectRun(rid || S.run.id);
  }
  function renderRunEmpty() { $("#runInfo").innerHTML = '<span class="muted">当前会话还没有任务</span>'; renderTab(); }
  function renderEmpty() { $("#messages").innerHTML = '<div class="empty">请选择或新建一个任务</div>'; $("#threadTitle").textContent = "请选择或新建一个任务"; S.runs = []; S.run = null; S.plan = null; renderRunSelect(); renderRunEmpty(); }

  /* --------------------------------------------------------------- tabs -- */
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
  function switchTab(t) {
    S.tab = t;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
    document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.id === "pane-" + t));
    renderTab();
  }
  function renderTab() {
    const t = S.tab;
    if (t === "process") return renderProcess();
    if (t === "trace") return renderTrace();
    if (t === "reqs") return renderReqs();
    if (t === "tests") return renderTests();
    if (t === "knowledge") return renderKnowledge();
    if (t === "changes") return renderChanges();
    if (t === "audit") return renderAudit();
    if (t === "memory") return renderMemory();
  }
  const needRun = (el) => { if (!S.run) { el.innerHTML = '<div class="empty">选择一个任务查看</div>'; return true; } return false; };

  /* ------------------------------------------------------------ process -- */
  function renderProcess() {
    renderPlan();
    if (S.meta) Graphs.agentGraph($("#agentGraph"), S.meta.graph, S.activeNodes);
    if (S.run && S.run.verification) renderVerify(S.run.verification); else $("#verifyBox").innerHTML = "";
  }
  function renderPlan() {
    const p = S.plan;
    if (S.tab !== "process") return;
    if (!p || !p.steps) { $("#planHeader").innerHTML = '<div class="empty">尚无执行计划。发送请求后，智能体会在这里展示它选择的工作流、理由与每一步的工具调用。</div>'; Graphs.processGraph($("#processGraph"), null); return; }
    const dom = p.domain || {};
    $("#planHeader").innerHTML = `<div class="plan-card"><div><div class="muted">工作流</div><div class="wf">${esc(p.title)}</div><div class="muted">${esc(p.intent_title || "")}</div></div>
      <div style="flex:1;min-width:260px"><div class="muted">规划依据（基于证据）</div><ul>${(p.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      ${dom.evidence && dom.evidence.length ? `<div class="muted" style="margin-top:4px">领域证据：${dom.evidence.slice(0, 4).map((e) => `<span class="tag">${esc(e)}</span>`).join("")}</div>` : ""}
      ${p.memory && p.memory.same_doc_runs && p.memory.same_doc_runs.length ? `<div class="muted" style="margin-top:4px">记忆：该文档此前已处理 ${p.memory.same_doc_runs.length} 次（${p.memory.same_doc_runs.map((r) => esc(r.run_id)).join("，")}）</div>` : ""}
      ${p.memory && p.memory.prefs && Object.keys(p.memory.prefs).length ? `<div class="muted">已应用偏好：${Object.entries(p.memory.prefs).map(([k, v]) => `<span class="tag info">${esc(k)}=${esc(v)}</span>`).join("")}</div>` : ""}</div>
      <div><div class="muted">阶段</div><div class="phases" id="phaseList"></div></div></div>`;
    renderPhases();
    Graphs.processGraph($("#processGraph"), p, showStep);
  }
  function renderPhases() {
    const el = $("#phaseList"); if (!el || !S.plan) return;
    el.innerHTML = (S.plan.phases || []).map((ph) => {
      const ss = S.plan.steps.filter((s) => s.phase === ph);
      let st = "";
      if (ph === "verify") st = S.plan._verify ? "done" : "";
      else if (ss.some((s) => s.status === "error")) st = "error";
      else if (ss.some((s) => s.status === "running")) st = "running";
      else if (ss.length && ss.every((s) => ["ok", "needs_review", "skipped"].includes(s.status))) st = "done";
      return `<span class="phase ${st}">${Graphs.PHASE_TEXT[ph] || ph}</span>`;
    }).join("→");
  }
  function showStep(i) {
    const box = $("#stepDetail");
    if (i < 0) { box.innerHTML = `<div class="box-title">验证</div><div class="muted">确定性检查（可追溯性、覆盖率、正反例、用例去向）+ 本地模型抽检（证据必须逐字出自原规则）</div>`; return; }
    const s = S.plan.steps[i];
    const tool = (S.meta && S.meta.tools.find((t) => t.name === s.tool)) || {};
    box.innerHTML = `<div class="box-title">${esc(s.title)} <span class="tag" style="background:${Graphs.STEP_COLOR[s.status]}">${esc(s.status)}</span></div>
      <div class="kv"><span class="k">工具</span><span class="mono">${esc(s.tool)}</span><span class="k">工作流</span><span>${esc(s.workflow)}</span>
      <span class="k">原始出处</span><span class="mono">${esc(s.origin)}</span><span class="k">后端</span><span>${esc(s.backend)}</span>
      <span class="k">输入→输出</span><span class="mono">${esc((tool.inputs || []).join(", "))} → ${esc((tool.outputs || []).join(", "))}</span>
      <span class="k">耗时</span><span>${secs(s.seconds)}</span>${s.llm ? `<span class="k">LLM 调用</span><span>${s.llm.calls} 次 · 修复 ${s.llm.repairs} · 失败 ${s.llm.failed} · 截断 ${s.llm.truncated}</span>` : ""}</div>
      <div class="muted" style="margin:6px 0">${esc(s.desc)}</div>
      ${s.args && Object.keys(s.args).length ? `<div class="muted">参数</div><pre>${esc(J(s.args))}</pre>` : ""}
      ${s.summary ? `<div class="muted">输出摘要</div><pre>${esc(J(s.summary))}</pre>` : ""}
      ${s.review ? `<div class="muted">人工复核</div><pre>${esc(J(s.review))}</pre>` : ""}
      ${s.error ? `<div class="muted">错误</div><pre>${esc(s.error)}</pre>` : ""}`;
  }
  function renderVerify(v) {
    if (S.tab !== "process") return;
    const vt = { pass: ["ok", "✅ 通过"], needs_review: ["warn", "⚠️ 需要人工复核"], fail: ["err", "❌ 未通过"] }[v.verdict] || ["", v.verdict];
    const rv = v.reviews || [];
    $("#verifyBox").innerHTML = `<div class="box"><div class="box-title">验证结论 <span class="tag ${vt[0]}">${vt[1]}</span></div>
      ${v.reason ? `<div class="muted" style="margin:2px 0 8px">${esc(v.reason)}</div>` : ""}
      <div class="checks">${(v.checks || []).map((c) => `<div class="check ${c.ok ? "" : "bad " + c.level}"><b>${c.ok ? "✔" : c.level === "error" ? "✖" : "!"} ${esc(c.name)}</b><div class="muted">${esc(c.detail)}</div></div>`).join("")}</div>
      ${rv.length ? `<div class="box-title" style="margin-top:10px">本地模型抽检（${rv.length} 条）</div><table class="grid"><tr><th>规则</th><th>忠实</th><th>用例一致</th><th>遗漏</th><th>理由 / 证据</th></tr>
      ${rv.map((r) => `<tr><td>${esc(r.rule_id)}</td><td>${tagYN(r.faithful)}</td><td>${tagYN(r.tests_consistent)}</td><td>${esc((r.missing || []).join("；"))}</td><td>${esc(r.reason)}${(r.evidence || []).map((e) => `<div class="mono muted">「${esc(e)}」</div>`).join("")}</td></tr>`).join("")}</table>` : ""}</div>`;
  }
  const tagYN = (x) => `<span class="tag ${x === "yes" ? "ok" : x === "no" ? "err" : "warn"}">${x === "yes" ? "是" : x === "no" ? "否" : "存疑"}</span>`;

  /* -------------------------------------------------------------- trace -- */
  async function renderTrace(focus, offset) {
    const el = $("#traceGraph");
    if (!S.run) { el.innerHTML = '<div class="empty">选择一个任务查看</div>'; return; }
    if (focus !== undefined) S.traceFocus = focus;
    if (offset !== undefined) S.traceOffset = offset;
    const q = S.traceFocus ? `?focus=${encodeURIComponent(S.traceFocus)}&cap=400` : `?cap=120&offset=${S.traceOffset || 0}`;
    const tok = (S.traceTok = (S.traceTok || 0) + 1);  // switchTab + focus fire two requests: only the latest may render
    const data = await api(`/api/runs/${S.run.id}/trace${q}`);
    if (tok !== S.traceTok) return;
    S.traceData = data;
    const st = data.stats || {};
    const pg = data.page;
    $("#traceInfo").innerHTML = `规则 ${st.rule || 0} · 需求 ${st.requirement || 0} · 场景 ${st.scenario || 0} · 用例 ${st.testcase || 0}；` +
      (data.mode === "overview"
        ? `总览：第 ${pg.offset + 1}–${pg.end} / ${pg.rules} 条规则（变更规则优先；每条规则抽样展示部分下游，用例折叠为「用例×N」），双击节点查看完整上下游
           <button class="btn small" id="tracePrev" ${pg.offset ? "" : "disabled"}>上一批</button><button class="btn small" id="traceNext" ${pg.next == null ? "disabled" : ""}>下一批</button>`
        : `聚焦 ${esc(S.traceFocus)}：显示 ${data.nodes.length} 个节点${data.collapsed ? "（用例按场景折叠，双击「用例×N」展开）" : ""}`);
    if (pg) {
      S.tracePages = S.tracePages || [];
      S.tracePages[pg.offset] = 1;
      const prev = $("#tracePrev"), next = $("#traceNext");
      if (prev) prev.onclick = () => { const starts = Object.keys(S.tracePages).map(Number).filter((x) => x < pg.offset); renderTrace(null, starts.length ? Math.max(...starts) : 0); };
      if (next) next.onclick = () => renderTrace(null, pg.next);
    }
    const sts = Object.keys(data.status || {}).map((k) => k.split(":")[1]).filter((v, i, a) => a.indexOf(v) === i);
    $("#statusLegend").innerHTML = sts.map((s) => `<i class="lg" style="background:${Graphs.STATUS_COLOR[s] || "#ccc"}"></i>${Graphs.STATUS_TEXT[s] || s}`).join(" ");
    S.traceCy = Graphs.traceGraph(el, data, { select: showNode, focus: (id) => renderTrace(id) });
    const hit = S.traceFocus && S.traceCy && S.traceCy.$id(S.traceFocus.replace(/^tcg:/, ""));
    if (hit && hit.length) hit.addClass("hit");
  }
  $("#traceReset").onclick = () => renderTrace(null, 0);
  $("#traceSearch").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter" || !S.run) return;
    const q = e.target.value.trim(); if (!q) return;
    for (const kind of ["rule", "requirement", "scenario", "testcase"]) {
      const r = await api(`/api/runs/${S.run.id}/table/${kind}?q=${encodeURIComponent(q)}&limit=1`);
      if (r.rows.length) { await renderTrace(r.rows[0].id); const n = S.traceCy && S.traceCy.$id(r.rows[0].id); if (n) { n.addClass("hit"); n.select(); S.traceCy.center(n); } showNode(r.rows[0].id); return; }
    }
    alert("没有找到匹配的节点");
  });
  async function showNode(id) {
    if (id.startsWith("tcg:")) {
      const g = (S.traceData.nodes || []).find((n) => n.id === id) || {};
      $("#nodeDetail").innerHTML = `<div class="box-title">测试用例组 · ${esc(g.label)}</div><div class="muted">属于 ${esc(g.of)}</div>
        <div style="margin:6px 0">正例 ${g.positive} · 反例 ${g.count - g.positive}</div>
        <div>${Object.entries(g.breakdown || {}).map(([k, v]) => `<span class="tag" style="background:${Graphs.STATUS_COLOR[k] || "#eee"};color:${Graphs.STATUS_COLOR[k] ? "#fff" : "#495057"}">${Graphs.STATUS_TEXT[k] || "新生成"} ${v}</span>`).join("")}</div>
        <div class="opts" style="margin-top:8px"><button class="btn small" id="focusBtn">展开这组用例</button></div>`;
      $("#focusBtn").onclick = () => renderTrace(id);
      return;
    }
    const d = await api(`/api/runs/${S.run.id}/node?id=${encodeURIComponent(id)}`);
    const n = d.node;
    const tname = { rule: "规则", requirement: "需求", scenario: "场景", testcase: "测试用例" }[n.type];
    $("#nodeDetail").innerHTML = `<div class="box-title">${tname} ${esc(n.label)} ${n.status ? `<span class="tag" style="background:${Graphs.STATUS_COLOR[n.status]};color:#fff">${Graphs.STATUS_TEXT[n.status] || n.status}</span>` : ""}</div>
      ${n.text ? `<pre>${esc(n.text)}</pre>` : ""}${n.focus ? `<div class="muted">关注点：${esc(n.focus)}</div>` : ""}
      ${n.data ? `<table class="grid">${Object.entries(n.data).map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table>` : ""}
      ${n.origin && n.origin !== n.label ? `<div class="muted">来自原用例：${esc(n.origin)}</div>` : ""}
      <div class="muted" style="margin-top:6px">上游</div>${d.parents.map((p) => `<div><a href="#" data-node="${esc(p.id)}">${esc(p.label)}</a> <span class="muted">${esc((p.text || "").slice(0, 60))}</span></div>`).join("") || '<div class="muted">无</div>'}
      <div class="muted" style="margin-top:6px">下游（${d.children_total}）</div>${d.children.slice(0, 20).map((p) => `<div><a href="#" data-node="${esc(p.id)}">${esc(p.label)}</a> <span class="muted">${esc((p.expected || p.text || "").slice(0, 60))}</span></div>`).join("") || '<div class="muted">无</div>'}
      ${(d.peers || []).length ? `<div class="muted" style="margin-top:6px">关联</div>${d.peers.map((p) => `<div><span class="tag ${p.relation === "conflict" ? "err" : "warn"}">${p.relation === "conflict" ? "一致性冲突" : "场景顺序"}</span><a href="#" data-node="${esc(p.id)}">${esc(p.label)}</a></div>`).join("")}` : ""}
      <div class="opts" style="margin-top:8px"><button class="btn small" id="focusBtn">聚焦此节点的上下游</button></div>`;
    $("#nodeDetail").querySelectorAll("[data-node]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); showNode(a.dataset.node); }));
    $("#focusBtn").onclick = () => renderTrace(id);
  }

  /* --------------------------------------------------------- reqs table -- */
  async function renderReqs() {
    const el = $("#reqsBody");
    if (needRun(el)) return;
    const wf = S.run.workflow;
    const kinds = [["rule", "规则"], ["requirement", "需求"], ["scenario", "场景"]];
    if (wf === "raft") kinds.push(["pipeline", "RAFT 逐条流水线"]);
    if (wf === "llm4fin") kinds.push(["conflicts", "一致性冲突"]);
    if (!kinds.some(([k]) => k === S.reqKind)) S.reqKind = "rule";
    el.innerHTML = `<div class="sub-tabs">${kinds.map(([k, n]) => `<button data-k="${k}" class="${S.reqKind === k ? "active" : ""}">${n}</button>`).join("")}</div>
      <div class="toolbar"><input id="reqQ" placeholder="搜索…"></div><div id="reqTable"></div>`;
    el.querySelectorAll(".sub-tabs button").forEach((b) => (b.onclick = () => { S.reqKind = b.dataset.k; renderReqs(); }));
    $("#reqQ").onkeydown = (e) => { if (e.key === "Enter") loadReqTable(e.target.value); };
    loadReqTable("");
  }
  async function loadReqTable(q) {
    const box = $("#reqTable");
    if (S.reqKind === "pipeline") return renderRaftPipeline(box, q);
    if (S.reqKind === "conflicts") return renderConflicts(box, q);
    const r = await api(`/api/runs/${S.run.id}/table/${S.reqKind}?q=${encodeURIComponent(q)}&limit=300`);
    box.innerHTML = `<div class="muted">共 ${r.total} 条${r.total > 300 ? "（显示前 300）" : ""}</div><div class="tbl-wrap"><table class="grid"><tr><th style="width:120px">编号</th><th>内容</th><th style="width:110px">状态</th><th style="width:80px"></th></tr>
      ${r.rows.map((n) => `<tr><td class="mono">${esc(n.label)}</td><td><pre>${esc(n.text)}</pre>${n.focus ? `<div class="muted">关注点：${esc(n.focus)}</div>` : ""}</td>
      <td>${n.status ? `<span class="tag" style="background:${Graphs.STATUS_COLOR[n.status]};color:#fff">${Graphs.STATUS_TEXT[n.status] || n.status}</span>` : ""}</td>
      <td><button class="btn small" data-trace="${esc(n.id)}">级联</button></td></tr>`).join("")}</table></div>`;
    box.querySelectorAll("[data-trace]").forEach((b) => (b.onclick = () => { switchTab("trace"); renderTrace(b.dataset.trace); showNode(b.dataset.trace); }));
  }
  async function renderConflicts(box, q) {
    const d = await api(`/api/runs/${S.run.id}/details`);
    const step = (S.plan.steps || []).find((s) => s.tool === "l4f.consistency") || {};
    let rows = d.conflicts || [];
    if (q) rows = rows.filter((c) => c.reason.includes(q) || c.rule_ids.some((x) => x.includes(q)));
    box.innerHTML = `<div class="muted" style="margin-bottom:8px">LLM4Fin 需求一致性检测（z3）：${esc(J(step.summary || {}))}。同一结果下约束互斥的需求对，需人工确认是否为规则本身的分支（如不同交易方式）或形式化错误。</div>
      <div class="tbl-wrap"><table class="grid"><tr><th style="width:200px">需求对</th><th>冲突说明</th><th style="width:80px"></th></tr>
      ${rows.map((c) => `<tr><td class="mono">${c.rule_ids.map((x) => `<a href="#" data-trace="req:${esc(x)}">${esc(x)}</a>`).join(" ⟷ ")}</td><td>${esc(c.reason)}</td>
        <td><button class="btn small" data-trace="req:${esc(c.rule_ids[0])}">级联</button></td></tr>`).join("") || '<tr><td colspan="3" class="muted">无冲突</td></tr>'}</table></div>`;
    box.querySelectorAll("[data-trace]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); switchTab("trace"); renderTrace(b.dataset.trace); showNode(b.dataset.trace); }));
  }

  async function renderRaftPipeline(box, q) {
    const d = await api(`/api/runs/${S.run.id}/details`);
    let rows = d.rules || [];
    if (q) rows = rows.filter((r) => (r.rule + (r.trl || "")).includes(q) || r.rid === q);
    const n = (f) => rows.filter(f).length;
    box.innerHTML = `<div class="stat-row">${[["规则句", rows.length], ["需求筛选通过", n((r) => r.testable)], ["形式化成功", n((r) => r.trl)],
      ["可测（含精化）", n((r) => r.testability && r.testability.testable)], ["人工保留", n((r) => r.testability && r.testability.override === "user_kept")], ["生成用例", rows.reduce((a, r) => a + r.tests, 0)]]
      .map(([l, v]) => `<div class="stat"><div class="n">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
      <div class="tbl-wrap"><table class="grid"><tr><th style="width:52px">编号</th><th>规则</th><th style="width:330px">流水线</th><th style="width:70px">用例</th><th style="width:60px"></th></tr>
      ${rows.map((r) => { const t = r.testability || {}; const g = r.gvr || {};
        const steps = [["筛选", r.testable ? "ok" : "no"], ["形式化" + (g.attempts > 1 ? `(修复${g.attempts - 1})` : ""), r.trl ? "ok" : r.testable ? "no" : ""],
          ["可测性" + (t.refined ? "(精化)" : ""), t.testable ? "ok" : t.override === "user_kept" ? "kept" : r.trl ? "no" : ""], ["用例", r.tests ? "ok" : ""]];
        return `<tr><td class="mono">${esc(r.rid)}</td><td>${esc(r.rule).slice(0, 160)}${t.violations && t.violations.length && !t.testable ? `<div>${t.violations.map((v) => `<span class="tag err">${esc(v)}</span>`).join("")}</div>` : ""}</td>
        <td><div class="pipeline">${steps.map(([s, c]) => `<span class="s ${c}">${s}</span>`).join("›")}</div></td><td>${r.tests}</td><td><button class="btn small" data-rid="${esc(r.rid)}">详情</button></td></tr>`; }).join("")}</table></div>`;
    box.querySelectorAll("[data-rid]").forEach((b) => (b.onclick = () => { const r = rows.find((x) => x.rid === b.dataset.rid); showRaftRule(r); }));
  }
  function showRaftRule(r) {
    const t = r.testability || {};
    const hist = (r.gvr && r.gvr.history) || [];
    modal(`RAFT 流水线 · ${r.rid}`, `<div class="muted">原规则</div><pre>${esc(r.rule)}</pre>
      ${r.filter_reason ? `<div class="muted">需求筛选：${r.testable ? "是需求" : "非需求"} — ${esc(r.filter_reason)}</div>` : ""}
      ${hist.length ? `<div class="muted" style="margin-top:8px">Generate-Verify-Repair（${hist.length} 轮）</div>${hist.map((h, i) => `<div class="muted">第 ${i + 1} 轮${h.errors && h.errors.length ? "：校验失败" : "：通过"}</div><pre>${esc(h.trl)}</pre>${(h.errors || []).map((e) => `<div class="tag err">${esc(e)}</div>`).join("")}`).join("")}` : ""}
      ${t.history ? `<div class="muted" style="margin-top:8px">可测试性判定（五步 OCL）与精化</div>${t.history.map((h, i) => `<div class="muted">${i === 0 ? "初判" : "精化 " + i}：${h.testable === true ? '<span class="tag ok">可测</span>' : h.testable === false ? '<span class="tag err">不可测</span>' : '<span class="tag warn">未通过校验</span>'}</div>
        ${h.trl ? `<pre>${esc(h.trl)}</pre>` : ""}${(h.steps || []).map((s) => `<div><span class="tag ${s.ok ? "ok" : "err"}">${esc(s.constraint)}</span><span class="muted">${esc(s.reason)}</span></div>`).join("")}
        ${h.note ? `<div class="muted">${esc(h.note)}</div>` : ""}${(h.check_errors || []).map((e) => `<div class="tag err">${esc(e)}</div>`).join("")}`).join("")}` : ""}
      ${t.override ? `<div class="muted">复核：${t.override === "user_kept" ? "用户保留" : "丢弃"}</div>` : ""}
      ${r.trl_postprocess ? `<div class="muted" style="margin-top:8px">后处理 TRL（post_process）</div><pre>${esc(r.trl_postprocess)}</pre>` : ""}`);
  }

  /* -------------------------------------------------------------- tests -- */
  async function renderTests() {
    const el = $("#testsBody");
    if (needRun(el)) return;
    const isCare = S.run.workflow === "care";
    const sf = S.testsStatus || "";
    const r = await api(`/api/runs/${S.run.id}/table/testcase?limit=200&offset=${S.testsPage * 200}&status=${sf}`);
    const keys = [...new Set(r.rows.flatMap((n) => Object.keys(n.data || {})))].filter((k) => !["rule", "testid"].includes(k)).slice(0, 12);
    const filters = isCare ? [["", "全部"], ["reused", "直接复用"], ["remapped", "重映射复用"], ["added", "新生成"], ["deleted", "已删除（原用例）"]] : [];
    el.innerHTML = `<div class="toolbar"><a class="btn" href="/api/runs/${S.run.id}/tests?fmt=json">下载 JSON</a><a class="btn" href="/api/runs/${S.run.id}/tests?fmt=csv">下载 CSV</a>
      ${S.plan && (S.plan.steps || []).some((s) => s.tool === "tests.minimize" && s.status === "ok") ? `<a class="btn" href="/api/runs/${S.run.id}/tests?fmt=json&variant=min" title="成对覆盖精简版">下载精简版</a>` : ""}
      ${filters.length ? `<span class="sub-tabs" style="margin:0">${filters.map(([v, n]) => `<button data-sf="${v}" class="${sf === v ? "active" : ""}">${n}</button>`).join("")}</span>` : ""}
      <span class="muted">共 ${r.total} 条</span><span class="pager"><button class="btn small" id="pgPrev" ${S.testsPage ? "" : "disabled"}>上一页</button>第 ${S.testsPage + 1} 页<button class="btn small" id="pgNext" ${(S.testsPage + 1) * 200 < r.total ? "" : "disabled"}>下一页</button></span></div>
      <div class="tbl-wrap"><table class="grid"><tr><th>用例</th><th>所属</th>${isCare ? "<th>复用状态</th>" : ""}${keys.map((k) => `<th>${esc(k)}</th>`).join("")}</tr>
      ${r.rows.map((n) => `<tr><td class="mono"><a href="#" data-trace="${esc(n.id)}">${esc(n.label)}</a></td><td class="mono">${esc((n.data || {}).rule)}</td>
      ${isCare ? `<td><span class="tag" style="background:${Graphs.STATUS_COLOR[n.status] || "#eee"};color:#fff">${Graphs.STATUS_TEXT[n.status] || n.status || ""}</span>${n.origin && n.origin !== n.label ? `<div class="mono muted">← ${esc(n.origin)}</div>` : ""}</td>` : ""}
      ${keys.map((k) => `<td>${esc((n.data || {})[k] ?? "")}</td>`).join("")}</tr>`).join("")}</table></div>`;
    $("#pgPrev").onclick = () => { S.testsPage--; renderTests(); };
    $("#pgNext").onclick = () => { S.testsPage++; renderTests(); };
    el.querySelectorAll("[data-sf]").forEach((b) => (b.onclick = () => { S.testsStatus = b.dataset.sf; S.testsPage = 0; renderTests(); }));
    el.querySelectorAll("[data-trace]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); switchTab("trace"); renderTrace(a.dataset.trace); showNode(a.dataset.trace); }));
  }

  /* ---------------------------------------------------------- knowledge -- */
  async function renderKnowledge(domain) {
    const el = $("#knowledgeBody");
    const list = await api("/api/knowledge");
    const cur = domain || (S.run && S.run.domain && list.find((k) => k.domain === S.run.domain) ? S.run.domain : list[0] && list[0].domain);
    el.innerHTML = `<div class="sub-tabs">${list.map((k) => `<button data-d="${k.domain}" class="${k.domain === cur ? "active" : ""}">${esc(k.title)} <span class="muted">${k.source === "builtin" ? "内置" : "RAFT 构建"}</span></button>`).join("")}</div><div id="kDetail"></div>`;
    el.querySelectorAll(".sub-tabs button").forEach((b) => (b.onclick = () => renderKnowledge(b.dataset.d)));
    if (!cur) return;
    const p = await api(`/api/knowledge/${cur}`);
    const rep = p.representation || {};
    const syms = rep.symbols || {};
    $("#kDetail").innerHTML = `<div class="box" style="margin-bottom:10px"><div class="kv"><span class="k">领域</span><span>${esc(p.title)}（${esc(p.domain)}）</span>
      <span class="k">来源</span><span>${esc(p.source)} · 工作流 ${esc(p.workflow)}</span><span class="k">出处</span><span class="mono">${esc(p.provenance)}</span>
      <span class="k">关键词</span><span>${(p.keywords || []).slice(0, 20).map((k) => `<span class="tag">${esc(k)}</span>`).join("")}</span>
      ${p.built_from ? `<span class="k">构建自</span><span>${esc(p.built_from)} · ${fmtT(p.built_at)}</span>` : ""}</div>
      ${p.source !== "builtin" ? `<div class="opts"><button class="btn small" id="kDel">删除该知识（下次将重新执行 RAFT 知识工程）</button></div>` : ""}</div>
      <div class="grid2"><div class="box"><div class="box-title">① 领域元模型 M（K 共识提纯）</div><div id="mmGraph" class="cy" style="height:420px"></div>
        ${p.meta_model && p.meta_model.others && Object.keys(p.meta_model.others.entities || {}).length ? `<div class="muted">Others：${Object.entries(p.meta_model.others.entities).slice(0, 30).map(([e, v]) => `<span class="tag">${esc(e)}·${v.votes}票</span>`).join("")}</div>` : ""}</div>
      <div class="box"><div class="box-title">② 需求表示 R（领域符号 → 中文标签）</div>
        <table class="grid"><tr><th>层</th><th>符号</th></tr>${Object.entries(syms).map(([l, xs]) => `<tr><td>${esc(l)}</td><td>${xs.map((x) => `<span class="tag info">${esc(x)}${rep.labels && rep.labels[x] ? "·" + esc(rep.labels[x]) : ""}</span>`).join("")}</td></tr>`).join("")}</table>
        <div class="box-title" style="margin-top:10px">语法（BNF）</div><pre>${esc((rep.bnf || []).map((r) => `${r.name} ::= ${r.alternatives.join(" | ")}`).join("\n"))}</pre></div></div>
      <div class="box" style="margin-top:12px"><div class="box-title">③ 可测试性约束 T（OCL，${(rep.ocl || []).length} 条）</div>
        <table class="grid"><tr><th style="width:90px">context</th><th style="width:200px">名称</th><th>约束</th></tr>${(rep.ocl || []).map((o) => `<tr><td>${esc(o.context)}</td><td class="mono">${esc(o.name)}</td><td class="mono">${esc(o.body)}</td></tr>`).join("")}</table></div>
      ${p.llm4fin ? `<div class="box" style="margin-top:12px"><div class="box-title">LLM4Fin 领域知识：${esc((p.llm4fin.state_machines[0] || {}).name || "状态机")} · 术语 ${p.llm4fin.terms} · 概念 ${p.llm4fin.concepts}</div>
        <div id="smGraph" class="cy" style="height:360px"></div><div class="muted">分类知识树根：${(p.llm4fin.classification_roots || []).map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</div></div>` : ""}`;
    Graphs.metaModelGraph($("#mmGraph"), p.meta_model);
    if (p.llm4fin) Graphs.stateMachineGraph($("#smGraph"), p.llm4fin.state_machines[0]);
    const del = $("#kDel"); if (del) del.onclick = async () => { if (confirm("确认删除？")) { await api(`/api/knowledge/${cur}`, { method: "DELETE" }); renderKnowledge(); } };
  }

  /* ------------------------------------------------------------ changes -- */
  async function renderChanges() {
    const el = $("#changesBody");
    if (needRun(el)) return;
    if (S.run.workflow !== "care") { el.innerHTML = '<div class="empty">变更视图用于 CARE 测试复用任务（原规则 → 新规则 → 用例更新）</div>'; return; }
    const d = await api(`/api/runs/${S.run.id}/details`);
    const tr = await api(`/api/runs/${S.run.id}/trace?cap=50`);
    const s = tr.status || {};
    const del = d.diff.to_delete_rules || [], add = d.diff.to_add_rules || [], mod = new Set(d.diff.modified || []);
    const newMap = d.diff.new_map || {};
    el.innerHTML = `<div class="stat-row">${[["原规则", d.old_rules.length], ["新规则", d.new_rules.length], ["修改", mod.size], ["删除(旧)", del.filter((r) => !mod.has(r.id)).length], ["新增(新)", add.filter((r) => !mod.has(r.id)).length],
        ["受影响场景", ((d.impact || {}).to_delete_scenarios || []).length], ["直接复用", s["testcase:reused"] || 0], ["重映射", s["testcase:remapped"] || 0], ["新生成", s["testcase:added"] || 0], ["删除用例", ((d.update || {}).deleted || []).length]]
      .map(([l, v]) => `<div class="stat"><div class="n">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
      <div class="muted" style="margin-bottom:8px">规则形式化：原 ${esc(J(d.formalize.old))}；新 ${esc(J(d.formalize.new))}</div>
      <div class="box"><div class="box-title">规则变更（CARE change_identify）</div><div class="tbl-wrap" style="max-height:420px"><table class="grid"><tr><th style="width:70px">类型</th><th style="width:110px">编号</th><th>原规则</th><th>新规则</th></tr>
      ${[...new Set([...del.map((r) => r.id), ...add.map((r) => r.id)])].map((id) => {
        const o = del.find((r) => r.id === id), n = add.find((r) => r.id === id);
        const kind = mod.has(id) ? ["modified", "修改"] : o ? ["deleted", "删除"] : ["added", "新增"];
        const scn = [].concat(newMap[id] || []).filter((x) => x !== id);
        return `<tr><td><span class="tag" style="background:${Graphs.STATUS_COLOR[kind[0]]};color:#fff">${kind[1]}</span></td><td class="mono">${esc(id)}${scn.length ? `<div class="muted" title="${esc(scn.join(", "))}">→ 新场景 ${scn.length} 个</div>` : ""}</td>
        <td>${o ? esc(o.text) : '<span class="muted">—</span>'}</td><td>${n ? esc(n.text) : '<span class="muted">—</span>'}</td></tr>`; }).join("")}</table></div></div>
      <div class="box" style="margin-top:12px"><div class="box-title">影响分析（impact_analysis）</div>
        <div class="muted">受影响场景：${((d.impact || {}).to_delete_scenarios || []).slice(0, 60).map((x) => `<span class="tag warn">${esc(x)}</span>`).join("") || "无"}</div>
        <div class="muted" style="margin-top:4px">受影响/删除用例：${((d.update || {}).deleted || []).slice(0, 80).map((x) => `<span class="tag err">${esc(x)}</span>`).join("") || "无"}</div></div>`;
  }

  /* -------------------------------------------------------------- audit -- */
  async function renderAudit() {
    const el = $("#auditBody");
    if (needRun(el)) return;
    const rows = await api(`/api/runs/${S.run.id}/audit`);
    const tot = rows.reduce((a, r) => a + (r.seconds || 0), 0);
    el.innerHTML = `<div class="muted" style="margin-bottom:8px">${rows.length} 次工具调用 · 合计 ${secs(tot)}</div><div class="tbl-wrap"><table class="grid"><tr><th>#</th><th>步骤</th><th>工具</th><th>状态</th><th>耗时</th><th>后端 / LLM</th><th>摘要 / 错误</th><th>时间</th></tr>
      ${rows.map((r, i) => { const d = r.detail || {}; const llm = d.llm;
        return `<tr><td>${i + 1}</td><td class="mono">${esc(r.step)}</td><td class="mono">${esc(r.tool)}</td><td><span class="tag ${r.status === "ok" || r.status === "pass" ? "ok" : r.status === "error" || r.status === "fail" ? "err" : "warn"}">${esc(r.status)}</span></td>
        <td>${secs(r.seconds)}</td><td>${esc(d.backend || "")}${llm ? `<div class="muted">${llm.calls} 次调用 · 修复 ${llm.repairs} · 失败 ${llm.failed} · ${(llm.models || []).join(",")}</div>` : ""}</td>
        <td>${d.error ? `<pre>${esc(d.error)}</pre>` : d.summary ? `<pre>${esc(J(d.summary))}</pre>` : d.checks ? `<pre>${esc(d.checks.map((c) => (c.ok ? "✔ " : "✖ ") + c.name + "：" + c.detail).join("\n"))}</pre>` : ""}</td><td class="muted">${fmtT(r.created)}</td></tr>`; }).join("")}</table></div>`;
  }

  /* ------------------------------------------------------------- memory -- */
  async function renderMemory() {
    const el = $("#memoryBody");
    const m = await api("/api/memory");
    el.innerHTML = `<div class="box"><div class="box-title">偏好（长期记忆，跨会话生效）</div><table class="grid"><tr><th style="width:170px">键</th><th>说明</th><th style="width:220px">值</th><th style="width:120px"></th></tr>
      ${Object.entries(m.pref_keys).map(([k, desc]) => `<tr><td class="mono">${k}</td><td class="muted">${esc(desc)}</td><td><input data-pref="${k}" value="${esc(m.prefs[k] ?? "")}" style="width:100%;border:1px solid var(--line);border-radius:6px;padding:3px 6px"></td>
      <td><button class="btn small" data-save="${k}">保存</button> <button class="btn small" data-forget="${k}">清除</button></td></tr>`).join("")}</table>
      <div class="muted" style="margin-top:6px">也可以在对话中说“记住：……”，智能体会自动写入。</div></div>
      <div class="box" style="margin-top:12px"><div class="box-title">任务记忆（情节）</div><div class="tbl-wrap" style="max-height:360px"><table class="grid"><tr><th>时间</th><th>请求</th><th>意图</th><th>工作流</th><th>领域</th><th>结论</th><th>规模</th></tr>
      ${m.episodes.map((e) => `<tr><td class="muted">${fmtT(e.ts)}</td><td>${esc((e.request || "").slice(0, 60))}<div class="muted">${esc((e.docs || []).join("，"))}</div></td><td>${esc(e.intent)}</td><td>${esc(e.workflow)}</td><td>${esc(e.domain)}</td>
      <td>${esc(e.verdict)}</td><td class="mono">${e.stats ? Object.entries(e.stats).map(([k, v]) => `${k}:${v}`).join(" ") : ""}</td></tr>`).join("")}</table></div></div>
      <div class="box" style="margin-top:12px"><div class="box-title">文档记忆（指纹 → 历史任务）</div><table class="grid"><tr><th>文档</th><th>指纹</th><th>处理记录</th></tr>
      ${m.docs.map((d) => `<tr><td>${esc(d.name)}</td><td class="mono">${esc(d.sha)}</td><td>${(d.runs || []).map((r) => `<span class="tag">${esc(r.workflow)}·${esc(r.status)}·${esc(r.run_id)}</span>`).join("")}</td></tr>`).join("")}</table></div>`;
    el.querySelectorAll("[data-save]").forEach((b) => (b.onclick = async () => { const k = b.dataset.save; await api(`/api/memory/prefs/${k}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: el.querySelector(`[data-pref="${k}"]`).value }) }); renderMemory(); }));
    el.querySelectorAll("[data-forget]").forEach((b) => (b.onclick = async () => { await api(`/api/memory/prefs/${b.dataset.forget}`, { method: "DELETE" }); renderMemory(); }));
  }

  /* --------------------------------------------------------------- misc -- */
  function modal(title, html) { $("#modalTitle").textContent = title; $("#modalBody").innerHTML = html; $("#modal").classList.remove("hidden"); }
  $("#modalClose").onclick = () => $("#modal").classList.add("hidden");
  $("#modal").onclick = (e) => { if (e.target.id === "modal") $("#modal").classList.add("hidden"); };

  async function health() {
    try {
      const h = await api("/api/health");
      const w = Object.values(h.workers || {});
      const mark = { ready: "✓", starting: "…", error: "✗", stopped: "·" };
      $("#health").innerHTML = `本地模型：<b>${h.llm.ok ? "在线" : "离线"}</b> ${esc(h.llm.model || "")}<br>工作流进程：${w.map((x) => `<b title="${esc(x.error || x.state)}">${esc(x.title)}</b>${mark[x.state] || "·"}`).join(" ")}<br>知识：${(h.knowledge || []).map(esc).join("、")}`;
    } catch (e) { $("#health").textContent = "服务不可用：" + e.message; }
  }

  (async function init() {
    S.meta = await api("/api/meta");
    const ts = await loadThreads();
    health(); setInterval(health, 30000);
    if (ts.length) openThread(ts[0].id); else renderEmpty();
  })();
})();
