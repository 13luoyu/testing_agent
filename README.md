# Testing Agent · 法规合规测试智能体与原始工作流

本仓库汇集了**法规驱动的合规测试**全链路研究与工程实现：三项已发表 / 在投的学术工作（**LLM4Fin**、**CARE**、**RAFT**），以及把它们统一编排为一个可用智能体的工程项目（**RegTest Agent**）。

> 一句话概括：**给定一份法规 / 标准文档，自动生成高质量验收测试用例；当规则修订时，自动复用与维护已有用例；遇到陌生领域时，先做知识工程再生成。** 这些能力既可单独使用（三个原始工作流），也可由统一的 LangGraph 智能体按证据自动选择与执行。

---

## 目录结构

```
testing_agent/
├── intelligent-test/     # LLM4Fin（ISSTA 2024）：金融规则 → 测试用例
├── CARE/                 # CARE（ISSTA 2026）：规则修订 → 测试用例复用/维护
├── RAFT/                 # RAFT（论文）：知识工程 + 跨领域测试生成
├── regtest-agent/        # RegTest Agent：用 LangGraph 把上述三者封装为可审计工具的统一智能体
├── szse_bond_trading_rule_testcases.json   # 示例产出：深交所债券交易规则的测试用例（含来源出处与统计）
└── szse_bond_trading_rule_report.html      # 示例产出：对应的可视化质量报告
```

---

## 一、四个组成部分

### 1. LLM4Fin（`intelligent-test/`）— 金融规则自动生成测试

> 论文：[*LLM4Fin: Fully Automating LLM-Powered Test Case Generation for FinTech Software Acceptance Testing*](https://doi.org/10.1145/3650212.3680388)，**ISSTA 2024**。

把自然语言金融业务规则**全自动**转化为验收测试用例，分三步：

1. **规则抽取（Rule Extraction）**：微调的编码器 LLM（Mengzi / FinBERT）做**句分类**（过滤不可测句子）与**要素标注**（抽取规则元素），再组装成 `if-then` 结构化规则（R1）。
2. **测试场景生成（Test Scenario Generation）**：基于金融分类知识补全隐含要素（R2），结合**状态机**挖掘规则间显式/隐式关系，展开业务场景（R3）。
3. **测试数据生成（Test Data Generation）**：用 **z3** 为每个场景求解测试数据，生成正例 / 反例用例。

在真实股票交易软件上，LLM4Fin 在业务场景覆盖率、代码覆盖率、耗时上**同时优于通用 LLM（ChatGPT、ChatGLM）与资深测试工程师**。

### 2. CARE（`CARE/`）— 规则修订下的测试用例复用与维护

> 论文：[*CARE: Cascading Impact-Aware Compliance Test Suite Evolution under Regulatory Changes*](https://doi.org/10.1145/3832295)，**ISSTA 2026**。

法规频繁变更时，现有方法因孤立处理规则变化而常常**过度复用**或**漏改**。CARE 构建统一的**四层级联关系模型 规则 → 需求 → 场景 → 测试用例**，显式建模规则变化如何沿链条传播与放大，从而精确识别受影响、需更新的场景与用例，同时安全地最大化复用未受影响的部分。

跨多领域真实合规测试任务上，CARE 在更新后测试套件上取得平均 **F1 90.3%**，最高超越现有方法 **164%**，接近专家水平。

### 3. RAFT（`RAFT/`）— 知识工程 + 跨领域测试生成

> 论文手稿（`RAFT/main.pdf`、`main.tex`）。

现有混合（LLM + 模型）方法仍需**人工构造领域知识**。RAFT 让输入法规保持规则级语义的权威性，同时把 LLM 中隐含的法规知识显式化为**三类可复用的元级产物**：

- **领域元模型 M（domain meta-model）**
- **需求表示 R（requirements representation）**
- **可测试性约束 T（testability constraints）**

LLM 从参数化知识（可选少量语料辅助）构建这些产物，RAFT 将其注入**需求形式化、可测试性判定、测试生成**三个环节。在金融、道路交通、电力共 11 个数据集上，RAFT 金融场景取得 **F1 91.7%**、业务场景覆盖率 **87.1%**，F1 较最强自动化基线高 **23.6 个百分点**；人工复核产物后 F1 可升至 **96.2%**。

### 4. RegTest Agent（`regtest-agent/`）— 统一智能体

> 详见 [`regtest-agent/README.md`](./regtest-agent/README.md)。

基于 **LangGraph** 的法规测试智能体：把上述三个原有工作流的**步骤、函数与提示词包装为可审计的工具**，由智能体负责 **理解 → 补充输入 → 分析 → 规划 → 执行 → 人工复核 → 验证 → 报告 / 记忆** 的完整闭环。

核心原则——**规划器不自己发明流程**，只依据证据（领域识别 + 知识库查询）在原工作流的 SOP 中做选择：

| 场景 | 证据 | 选用的工作流 |
| --- | --- | --- |
| 生成测试 · 中文金融（证券）规则 | 领域=finance，命中 LLM4Fin 知识 | **LLM4Fin**：过滤不可测规则 → 要素抽取与形式化 → 补全 → 关系挖掘 → 生成测试 |
| 生成测试 · 已有 RAFT 知识的领域 | 知识库有元模型 M / 需求表示 R / 约束 T | **RAFT Phase II**：知识注入形式化 → 可测试性判定与精化 → 生成用例 |
| 生成测试 · 陌生领域 | 关键词与模型均无匹配知识 | **RAFT Phase I → 登记知识 → Phase II** |
| 知识工程 | 用户只要求构建知识 | **RAFT Phase I**：构建并登记 M / R / T |
| 测试复用 / 维护 | 需要 原规则、新规则、原测试用例 | **CARE**：需求/场景生成 → 用例对齐 → 变更识别 → 影响分析 → 用例更新 |

前端以可视化方式呈现：**规则 → 需求 → 场景 → 测试用例的级联图**、按阶段分泳道的 **SOP 执行流程图**、LangGraph 智能体拓扑、RAFT 元模型图、LLM4Fin 状态机、验证结论与工具审计、长期记忆等。

---

## 二、快速开始

各子项目的环境与依赖不同，请进入对应目录按其自身 README 操作：

| 想做的事 | 去哪里 | 入口 |
| --- | --- | --- |
| 金融规则 → 测试用例 | [`intelligent-test/`](./intelligent-test/README.md) | `cd ours && python main.py --file <规则.pdf> --model mengzi` |
| 规则修订 → 用例复用 | [`CARE/`](./CARE/README.md) | `cd ours && python update_testcase.py --old_file ... --new_file ...` |
| 知识工程 + 跨领域生成 | [`RAFT/`](./RAFT/) | 见论文手稿与 `RAFT/*.tex` |
| 统一智能体（Web + API） | [`regtest-agent/`](./regtest-agent/README.md) | `scripts/start.sh` → http://127.0.0.1:8080 |

### 用智能体一键生成（推荐）

```bash
cd regtest-agent
scripts/start.sh          # 若 :8800 无模型服务则先启动，然后启动 http://127.0.0.1:8080
```

打开网页后上传规则文档并描述需求（例如“根据这份规则生成测试用例”），智能体会识别领域、查询知识、按原工作流 SOP 规划并执行，过程与级联关系在右侧标签页实时可视化。

### 命令行批量生成（无需浏览器）

```bash
cd regtest-agent
PYTHONPATH=src python -m regtest_agent.generate 规则.pdf \
    --minimize --report 报告.html --title "..." --official-url "..." --effective-date 2022-05-16
```

产出带来源出处与统计的 `*_testcases.json` 和自包含 HTML 质量报告（本仓库根目录的
[`szse_bond_trading_rule_testcases.json`](./szse_bond_trading_rule_testcases.json) 与
[`szse_bond_trading_rule_report.html`](./szse_bond_trading_rule_report.html) 即为深交所债券交易规则的示例产出）。

---

## 三、模型与大文件说明

- 三个原始工作流依赖**微调 / 预训练大模型**（Mengzi、FinBERT、Qwen、GLM 等），这些权重通过各子项目 README 中的 HuggingFace 链接下载，**不随本仓库分发**（已在各自 `.gitignore` 中排除 `model/`、`cache/`、`.runtime/` 等）。
- 仓库内保留的是**代码、标注数据、领域知识、实验数据与结果**。其中
  `intelligent-test/data/data_for_LLM_encoder/tc_train_data_augmented.json` 约 60MB，
  超过 GitHub 50MB 的建议值（但未超 100MB 硬上限），如需精简可改用 Git LFS。

---

## 四、引用

如果这些工作对你有帮助，请引用对应论文：

- **LLM4Fin** — *Fully Automating LLM-Powered Test Case Generation for FinTech Software Acceptance Testing*, ISSTA 2024.
- **CARE** — *Cascading Impact-Aware Compliance Test Suite Evolution under Regulatory Changes*, ISSTA 2026.
- **RAFT** — *Requirements-Authoritative Formalization and Testing for knowledge-guided compliance test generation*（手稿）。

---

<div align="center">

*法规驱动测试：从单项工作流到统一智能体。*

</div>
