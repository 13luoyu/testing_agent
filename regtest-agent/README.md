# RegTest Agent v2

基于 **LangGraph** 的法规测试智能体：把 **LLM4Fin**（测试生成）、**RAFT**（领域知识工程 + 测试生成）、**CARE**（测试复用/维护）三个原有工作流的步骤、函数与提示词包装为**可审计的工具**，由智能体负责**理解 → 补充输入 → 分析 → 规划 → 执行 → 人工复核 → 验证 → 报告/记忆**。

规划器**不自己发明流程**：它只依据证据（领域识别 + 知识库查询）在原工作流的 SOP 中做选择，执行器逐步调用对应工具。

| 场景 | 证据 | 选用的 SOP |
| --- | --- | --- |
| 生成测试 · 中文金融（证券）规则 | 领域=finance，命中 LLM4Fin 分类知识树/状态机/术语表 | **LLM4Fin**：预处理 → 过滤不可测规则(mengzi) → 规则元素抽取(mengzi) → 形式化 R1 → 一致性检测(z3) → 补全 R2 → 关系挖掘 R3(HanLP+状态机) → 生成测试(z3) |
| 生成测试 · 已有 RAFT 知识的领域（交通/电力/金融英文…） | 知识库有元模型 M / 需求表示 R / 约束 T | **RAFT Phase II**：切分 →（翻译）→ 需求筛选 → 知识注入形式化(Generate-Verify-Repair) → 五步 OCL 可测试性判定与精化 →（HITL 复核）→ post_process → z3 生成用例 |
| 生成测试 · 陌生领域 | 关键词与本地模型均无匹配知识 | **RAFT Phase I → 登记知识 → Phase II** |
| 知识工程 | 用户只要求构建知识 | **RAFT Phase I**：N 候选元模型 → 语义对齐 → K 共识提纯 → N 候选需求表示 → 并集聚合 → 登记 |
| 测试复用 / 维护 | 需要 原规则、新规则、原测试用例（缺失时智能体会询问） | **CARE**：原/新规则需求与场景生成 → 用例对齐 → 变更识别 → 影响分析 → 用例更新 |

## 架构

```
web/ (chat + 流程图 + 级联图 + 知识/变更/审计/记忆)  ──SSE/REST──  api/app.py (FastAPI)
                                                                    │
                                                         service.py（每会话一个后台 LangGraph 运行，事件持久化可回放）
                                                                    │
agent/graph.py   understand → gather⟲ → analyze → [ask_domain → redetect] → lookup → plan → execute⟲ → [review → apply_review]
                 → verify → report        （失败 → on_failure: 重试/跳过/终止；所有 interrupt 都在无副作用节点）
agent/sop.py     原工作流 SOP 与基于证据的路由      agent/memory.py   偏好 / 任务情节 / 文档指纹（LangGraph SqliteStore）
agent/verify.py  确定性检查 + 本地模型抽检（证据必须逐字出自原规则）
tools/*.py       30 个工具（common / l4f / raft / care），统一审计：工具、状态、耗时、LLM 调用/修复/截断
workers/*.py     隔离子进程（JSON-lines）加载 LLM4Fin / CARE / RAFT 原始代码与模型（mengzi、HanLP、z3）
llm/server.py    本地 OpenAI 兼容服务（mlx-lm + lm-format-enforcer 约束解码）；llm/client.py 重试退避、超长截断、schema 校验 + 修复提示
knowledge.py     知识包：内置 finance（LLM4Fin + RAFT 发布产物）、traffic / power（RAFT exp5 三模型产物按 N=3,K=2 合并）；RAFT 构建的新领域
```

## 安装与启动

依赖两个 conda 环境：`regtest-agent`（智能体、工作流 worker）与 `regtest-llm`（mlx-lm 本地模型服务）。原始仓库路径可用环境变量覆盖：

| 变量 | 默认 |
| --- | --- |
| `REGTEST_LLM4FIN_ROOT` | `/Users/bytedance/Desktop/code/test/intelligent-test` |
| `REGTEST_CARE_ROOT` | `/Users/bytedance/Desktop/code/test/CARE` |
| `REGTEST_RAFT_ROOT` | `/Users/bytedance/Desktop/code/fse 2027/RAFT` |
| `REGTEST_RUNTIME` | `.runtime`（数据库、检查点、上传、产物、知识） |
| `REGTEST_LLM_BASE_URL` / `REGTEST_LLM_MODEL` | `http://127.0.0.1:8800/v1` / Qwen3-30B-A3B-Instruct-2507-4bit |
| `REGTEST_LLM_THREADS` | 4（并发调用线程数） |
| `REGTEST_RAFT_N` / `REGTEST_RAFT_K` / `REGTEST_RAFT_TEMPS` | 3 / 2 / 0.3,0.7,1.0 |
| `REGTEST_TESTABILITY_MIN_PASS` | 3（五步可测试性判定中需通过的约束数） |
| `REGTEST_JUDGE_SAMPLES` | 6（验证抽检条数） |

```bash
scripts/start.sh          # 若 :8800 没有模型服务则先启动，然后启动 http://127.0.0.1:8080
# 或分别启动
PYTHONPATH=src ~/miniconda3/envs/regtest-llm/bin/python -m regtest_agent.llm.server --model .runtime/models/llm/Qwen3-30B-A3B-Instruct-2507-4bit --port 8800
PYTHONPATH=src ~/miniconda3/envs/regtest-agent/bin/python -m regtest_agent --port 8080
```

## 使用

- **生成测试**：上传规则文档（pdf/txt/md/docx），例如“根据这份规则生成测试用例”。领域无法确定时智能体会询问；陌生领域会先做 RAFT 知识工程并登记到知识库，之后同领域直接复用。
- **测试复用**：上传原规则、新规则、原测试用例（json），例如“规则修订了，帮我复用原来的测试用例”。缺哪个文件，智能体会停下来要。
- **RAFT 人工复核**：可测试性判定为不可测的需求会以勾选卡片交给你：全部丢弃（全自动 RAFT）、全部保留或按勾选保留。可说“记住：不可测需求直接丢弃”改为不再询问（偏好 `untestable_policy`）。
- **测试精简（可选）**：规则含多维枚举时会产生笛卡尔积式的近似重复用例。开启偏好 `minimize`（如“记住：开启测试精简”）后，在生成阶段追加 `tests.minimize` 步骤，对每个膨胀的用例组选取覆盖全部观测取值对（2-wise）且保留正/反例的最小子集，**不新造任何组合**；全量用例仍为准，精简版为附加视图（测试用例页可下载精简版）。
- **记忆**：偏好（默认工作流、抽检数、最大规则数、不可测策略、是否精简…）跨会话生效；同一文档（按内容指纹）再次处理时，计划中会提示历史任务。
- **命令行批量生成**（无需浏览器，便于 CI / 复现实验基线）：

```bash
PYTHONPATH=src ~/miniconda3/envs/regtest-agent/bin/python -m regtest_agent.generate 规则.pdf \
    --minimize --report 报告.html --title "..." --official-url "..." --effective-date 2022-05-16
# 产出带来源出处与统计的 *_testcases.json，并可选生成自包含 HTML 质量报告
```

前端标签页：**流程**（按阶段分泳道的 SOP 步骤图、规划依据与记忆、步骤详情、LangGraph 拓扑、验证结论）· **级联图**（规则 → 需求 → 场景 → 测试用例；总览按规则分批浏览、用例折叠为「用例×N」，双击任一节点查看完整上下游；CARE 用颜色标注 修改/删除/新增/复用/重映射，RAFT 标注 不可测丢弃/形式化失败/精化后可测/人工保留；搜索、点击看详情）· **规则·需求**（含 RAFT 逐条流水线：筛选 → GVR 修复轮次 → 五步 OCL 判定 → 精化 → 用例）· **测试用例**（分页、状态筛选、JSON/CSV 下载）· **知识**（元模型图 + 投票、领域符号/中文标签、BNF、OCL、LLM4Fin 状态机）· **变更**（CARE 规则差异、影响场景、删除用例）· **审计**（每次工具调用的后端、耗时、LLM 调用/修复）· **记忆**。

## API 摘要

`POST /api/threads` · `POST /api/threads/{id}/messages`（multipart: text, files[]）· `POST /api/threads/{id}/resume`（回答 interrupt：`{choice|text|keep|roles}`）· `POST /api/threads/{id}/stop` · `GET /api/threads/{id}/events`（SSE，支持 `Last-Event-ID` 回放）· `GET /api/runs/{rid}`、`/audit`、`/trace?focus=&cap=&offset=`（总览按规则分批，`focus=tcg:<节点>` 展开折叠的用例组）、`/node?id=`、`/table/{rule|requirement|scenario|testcase}`、`/details`、`/tests?fmt=json|csv[&variant=full|min]`、`/artifacts/{name}` · `GET /api/knowledge[/{domain}]` · `GET/PUT/DELETE /api/memory/prefs/{key}` · `GET /api/meta`（智能体拓扑、SOP、工具注册表）· `GET /api/health`。

## 测试

```bash
PYTHONPATH=src ~/miniconda3/envs/regtest-agent/bin/python -m pytest -q     # 纯函数与视图测试，不需要模型
```

## 与原工作流的差异（如实说明）

- **单一本地模型**：所有 LLM 步骤使用本地 Qwen3-30B-A3B（4bit）。RAFT 论文用 3 个不同 LLM 产生 N 个候选，这里用同一模型的不同采样温度代替（无效候选会补采样，最多 2N 次），并在投票前加了一步语义对齐（同义要素合并）。
- **CARE 规则形式化**：原实现依赖 GLM4-LoRA 权重（未提供）。这里保留 CARE 的指令与输出格式，用 CARE 仓库中的 GLM4 预测结果做精确命中与近邻 few-shot，由本地模型生成；其余步骤（mengzi 筛选、to_r、R1→R3、对齐、变更识别、影响分析、z3 用例更新）均调用 CARE 原代码。
- **RAFT 可测试性判定**：采用 RAFT `testability/prompt` 的五步提示词（每个 OCL 约束一步）。本地模型在 RAFT 标注集上抽样 40 条的准确率：单提示词 0.43–0.53，五步全通过 0.55，**五步通过 ≥3 项 0.625**（默认阈值，可配置）。RAFT 论文中 GPT 的五步准确率为 0.91，本地模型更保守，因此加入了 HITL 复核作为补偿。
- **RAFT 需求筛选**：金融用 mengzi_rule_filtering；交通/电力用 exp5 的需求判定提示词；其他新领域把同一提示词中的领域示例替换为该领域名称与元模型要素。
- **形式化校验**（Generate-Verify-Repair 的 Verify）：语法三元组、键必须属于需求表示的领域符号、取值必须在原规则/原文中有依据（数字必须出自本条规则），否则带定位诊断修复，最多 3 次。
- **CARE 用例编号**：CARE 的 `testcase_update` 把复用用例重映射到新规则编号、新生成用例从 `_1` 开始编号，两者会撞号（演示数据中约 50–80 条）。这里复用用例优先保留编号，其余顺延到该规则下一个空闲序号，记录在 `care_update.renumbered`；验证阶段检查「用例编号唯一」。
- **CARE 范围外用例**：未被识别为变更、也没有被对齐到本次处理规则的原用例，CARE 原样保留；级联图中挂在虚拟的「范围外·规则」节点下，不计入规则统计与覆盖率。

## 端到端结果（本机，本地 Qwen3-30B-A3B 4bit）

| 场景 | 输入 | 智能体行为 | 结果 |
| --- | --- | --- | --- |
| LLM4Fin | 深交所债券交易规则.pdf | 识别为金融 → LLM4Fin SOP（8 步） | 366 句 → 可测 98 → 54 条规则 / 151 需求 / 1383 场景 / 4185 用例，耗时约 1.2 分钟；一致性检测 38 对冲突 |
| RAFT（已有知识） | 光伏电站故障穿越要求.txt | 命中内置电力知识 → RAFT Phase II；9 条不可测交人工复核（保留 2 条） | 39 句 → 35 条需求 → 31 条形式化（15 条经修复）→ 22 条可测（3 条经精化）+ 2 条人工保留 → 90 条用例，约 10 分钟（五步判定占 7 分钟） |
| RAFT（陌生领域） | 医疗器械说明书和标签管理规定 | 无知识 → Phase I（12 要素 / 21 符号 / 30 条 OCL，登记知识）→ Phase II；2 条不可测交人工复核 | 16 句 → 11 条需求 → 9 条形式化（6 条经修复）→ 7 条可测 + 2 条人工保留 → 14 条用例，约 5.4 分钟 |
| CARE | 深交所交易规则 2021 / 2023 版 + 474 条原用例 | 缺原用例时先追问，补齐后执行 CARE SOP（7 步） | 复用 344 + 重映射 16 + 新生成 197，删除 114（474 条原用例去向全部可核对），编号重复 0，验证通过，约 4.2 分钟 |

验证阶段的本地模型抽检对每条规则展示其各条需求及“对应需求”的用例；抽检结论只作提示，最终以人工复核为准。

以上四个任务的完整记录（对话、计划、产物、审计、知识）保存在 `.runtime/demo`，可直接打开查看：

```bash
REGTEST_RUNTIME=.runtime/demo PORT=8090 scripts/start.sh     # http://127.0.0.1:8090
```
