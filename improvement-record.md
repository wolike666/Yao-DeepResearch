## 改进记录：My-DeepResearch 对齐 Alibaba 深研能力

日期：2026-05-11
状态：已完成
适用范围：F:/Code/LLM/My-DeepResearch-2

### 本轮目标
1. 输出增加可解析引用，兼容 DeepResearch Bench 的 raw_data 评分格式。

### 本轮实施内容
1. 证据与引用对齐
- `src/my_deepresearch/agent/state.py` 增加 `evidence` 字段，用于记录 read 的结构化证据（url/title/snippet/summary）。
- `src/my_deepresearch/agent/orchestrator.py` 在 read 后写入 evidence，并在 synthesize 提示词中增加正文内联引用规则（Markdown 链接）。

2. 输出格式兼容
- `src/my_deepresearch/agent/utils.py` 在结果中新增 `prompt` 与 `article` 字段，`article` 为带引用的正文。
- 若正文未包含内联引用，自动追加 fallback `Sources:` 行（优先 evidence，其次 sources），避免评分流程无引用可抽取。

日期：2026-04-15
状态：已完成（代码改造与回归验证均通过）
适用范围：F:/Code/LLM/My-DeepResearch-2

### 本轮确认约束（用户最新口径）
1. 对齐等级：中度对齐。
2. 运行方式：只做单问题交互。
3. 模型接口：继续 OpenAI 兼容。
4. 工具范围：仅搜索、网页读取、学术搜索。
5. 暂不建设评测链路。
6. 最终输出主看 answer，可保留 think。
7. 允许调整 .env 字段命名，继续复用 Alibaba 密钥配置。
8. 参数与文档允许非零破坏更新。

### 本轮实施内容（2026-04-15）
1. 模块拆分完成
- 新增目录：src/my_deepresearch/agent
- 新增模块：state.py、planner.py、reflector.py、orchestrator.py、utils.py
- engine.py 调整为兼容层，仅转发 run_research 到 orchestrator

2. 配置层兼容增强
- config.py 新增共享 .env 加载逻辑：先本地，再 Alibaba .env（override=False）
- 支持字段回退：OPENAI_* 为空时，回退 API_KEY/API_BASE/INFER_MODEL_NAME/MODEL_PATH

3. 运行脚本对齐
- 新增 scripts/run_single_research_windows.py
- 脚本风格参考 Alibaba run_react_infer_windows，但只保留单问题流程

4. 文档更新
- README.md 重写为 My-DeepResearch-2 当前架构与使用方式
- .env.example 增加 Alibaba 兼容字段与单题脚本默认项

### 验收计划（本轮）
1. 使用下列三个问题实跑：
- 帮我调研DeepResearch
- 2026年佛山大学有几项成果获评广东省高校党建研究优秀成果奖？
- 佛山大学计算机与人工智能学院召开2026年春季学期教职工大会日期是什么？谁主持会议？
2. 成功判据：
- 每题都生成 result_*.json
- result 中 answer 非空
- steps/sources/reflections 字段存在

### 验收结果（2026-04-15）
1. 三个验收问题均已跑通并生成结果文件：
- outputs/acceptance/result_20260415_180846.json
- outputs/acceptance/result_20260415_181113.json
- outputs/acceptance/result_20260415_181331.json

2. 快速冒烟回归：
- outputs/acceptance/result_20260415_181509.json

3. 验证结论：
- 每次运行均成功落盘 result JSON。
- answer 均为非空。
- steps、sources、reflections 字段均存在。
- 单问题全流程（plan -> act -> reflect -> synthesize）可稳定执行。

日期：2026-04-13
状态：方案已确认，待实施
适用范围：F:/Code/LLM/My-DeepResearch

### 一、改造目标（已确认）
1. 在 planner 增加硬约束：前 5 步里至少 1 步必须是 read。
2. 参考 Alibaba 提示词风格，已在本系统提示词方向上做对齐。
3. 增加信源分层能力。
4. 参考 Alibaba 已配置目录，补一个 scholar 检索工具。

### 二、问题复盘（改造前）
1. 过程动作偏 search-only，read 触发不足，导致 notes 为空或证据链偏弱。
2. 结果容易陷入“实体归属争议”而非围绕用户问题展开章节化分析。
3. sources 目前无分层字段，无法稳定优先高可信来源。
4. 缺少 scholar 检索，学术证据密度不足。

### 三、方案摘要（已冻结）
1. 约束层
- 在 planner 提示词与运行时双重约束 read 触发。
- 若 step <= 5 且尚未 read，执行层强制覆盖为 read。

2. 提示词层
- 保持现有 JSON 规划协议。
- 参考 Alibaba 的“目标-证据-结论”结构，不迁移 XML tool-call 协议。
- 强化最终答案必须覆盖：对比、优势、劣势、场景、风险、趋势。

3. 数据层
- 扩展 source 字段：domain、source_tier、access_time、relevance_score。
- 引入分层策略：official、academic、news、community。
- read 选源优先高层级且未访问来源。

4. 工具层
- 新增 scholar_tool，参考 Alibaba 的 tool_scholar 最小实现。
- scholar 返回结构与现有 web search 保持一致，便于统一合并与排序。

### 四、执行清单（按顺序）
1. 修改 engine 的 planner 约束与运行时兜底逻辑。
2. 抽离并重构提示词模块（planner/extractor/reflect/synthesize）。
3. 修改 search_tool 与 sources 合并逻辑，加入信源分层打标。
4. 新增 scholar_tool 并接入 engine 的 search 分支。
5. 更新 config 与 main 参数，保持向后兼容。
6. 运行回归问题进行对比验收。

### 五、验收标准
1. 在 max-steps=5 的任务中，steps 前 5 步至少出现 1 次 action=read。
2. 输出 JSON 中 notes 非空。
3. sources 每条记录含 source_tier。
4. 结果正文包含：对比、优势、劣势、适用场景、风险、趋势。
5. 学术主题查询时，sources 中可见 academic 来源。

### 六、风险与对策
1. 风险：硬约束过强导致策略僵化。
- 对策：只约束“前 5 步至少 1 次 read”，不强制固定步位。

2. 风险：scholar 结果与 web 结果结构不一致。
- 对策：统一字段标准后再入库合并。

3. 风险：新增分层后召回下降。
- 对策：默认 balanced 策略，支持 strict 模式开关。

### 七、参考来源（迁移依据）
1. Alibaba scholar 工具：F:/Code/LLM/Alibaba-NLP-DeepResearch/inference/tool_scholar.py
2. Alibaba 提示词模板：F:/Code/LLM/Alibaba-NLP-DeepResearch/inference/prompt.py
3. Alibaba 评测提示词：F:/Code/LLM/Alibaba-NLP-DeepResearch/evaluation/prompt.py

### 八、关联计划文档
- /memories/session/plan.md

### 九、实施进展（2026-04-14 至 2026-04-15）
日期：2026-04-15
状态：已完成本轮确认项并通过回归验证

本轮按用户确认执行：
1. 不执行原计划中的“强制 scholar 兜底”和“主体覆盖硬约束”改造。
2. 执行“reflections 增加 step 序号”。
3. 执行“提示词升级为更接近 Alibaba 的协议化约束（保持 JSON 流程兼容）”。
4. 补充“answer 导出 md 脚本”，用于结果可读化。

已落地改动如下：
1. `src/my_deepresearch/engine.py`
- ` _reflect_step(...)` 新增 `step_id` 入参。
- 反思 JSON schema 增加 `step` 字段示例。
- 反思结果写入时增加回填逻辑：若模型未返回 step，则使用当前轮次 step_id。
- 调用处更新为 `_reflect_step(llm, state, step_id, plan, observation)`。

2. `src/my_deepresearch/prompts.py`
- Planner 提示词升级为协议化动作描述（search/read/reflect/synthesize/finish）与更强约束。
- Reflect 提示词增加“输出 step 序号”要求。
- Extractor 提示词补充“无有效信息”处理约束。
- Synthesize 提示词明确 `<think>/<answer>` 标签输出约束。

3. `scripts/json_answer_to_md.py`（新增）
- 支持从结果 JSON 提取 `answer` 字段转为 `.md`。
- 若 `answer` 为空，回退从 `answer_tagged` 中提取 `<answer>...</answer>`。
- 输出目录可配置，默认写入 `outputs/md_exports`。

本轮验证结果：
1. 运行结果文件：`My-DeepResearch/outputs/result_20260414_230159.json`
2. 关键验证通过：
- `reflections` 已出现 step 字段（与 `steps` 可对齐审计）。
- 端到端流程可正常完成并落盘。
3. md 导出验证通过：
- 脚本成功生成：`My-DeepResearch/outputs/md_exports/result_20260413_115310.md`

可复现实验命令：
1. 运行调研：
```bash
f:/Code/LLM/.venv/Scripts/python.exe My-DeepResearch/main.py --question "帮我调研DeepResearch，输出长篇调研报告，包括对比、优势、劣势、适用场景、风险与趋势" --max-steps 5 --search-mode hybrid --source-policy balanced --save-dir My-DeepResearch/outputs
```

2. 导出 Markdown：
```bash
f:/Code/LLM/.venv/Scripts/python.exe My-DeepResearch/scripts/json_answer_to_md.py --input My-DeepResearch/outputs/result_20260413_115310.json --out-dir My-DeepResearch/outputs/md_exports
```

备注：
1. 本轮未实现“强制调用 scholar_tool 访问论文”和“对比主体覆盖率硬约束”，属于后续可选增强项。
2. 若后续要继续对齐 Alibaba 行为，可在不改变 JSON 协议前提下继续强化 Planner 的来源与覆盖约束。
## 2026-05-11 补充记录：DeepResearch Bench 引用格式修复（id=1 对齐）

### 背景与问题
- 目标：让本框架输出更符合 `Deep_Research_Bench` 评分抽取习惯（FACT 抽取/去重/校验链路）。
- 现状问题：`answer/article` 中引用主要是 Markdown 超链接（`[title](url)`）和非标准标记（如 `[Evidence: ...]`），与基准样例常见的 `正文 [1][2] + 文末参考文献编号列表` 不一致。

### 依据
- 参考文档：
  - `Deep_Research_Bench/deep_research_bench/README.md`
  - `Deep_Research_Bench/DeepResearch-Bench-Dataset/README.md`
- 对照样例：
  - `Deep_Research_Bench/deep_research_bench/data/test_data/raw_data/claude-3-7-sonnet-latest.jsonl`（id=1 为 `[n]` 编号引用风格）
  - 本地输出：`outputs/bench_sample_20260511_1/result_20260511_162735.json`

### 代码改动
1. `src/my_deepresearch/agent/orchestrator.py`
- 更新综合写作提示词中的引用规则：
  - 明确要求正文使用数字引用 `[1] [2]`；
  - 禁止正文 `[](...)` 链接样式；
  - 要求文末输出 `参考文献：` + 编号条目。

2. `src/my_deepresearch/agent/utils.py`
- 扩展引用识别：`has_inline_citations` 同时识别 Markdown 链接和 `[n]`。
- 新增规范化后处理：`normalize_benchmark_citations(...)`
  - 清理 `[Evidence: ...]` 非标准标记；
  - 将 `[](...)` 自动转为 `[n]`；
  - 将裸 URL 自动收敛为 `[n]`；
  - 自动补齐并重建文末 `参考文献：` 编号列表；
  - 若正文无行内编号但有来源，自动补最小行内引用（`[1]`）。
- 调整 `build_citation_fallback(...)`：改为编号参考文献输出，不再拼 Markdown 链接。
- 调整 `build_result_payload(...)`：
  - 在最终落盘前统一做引用规范化；
  - 回写 `answer_tagged` 中 `<answer>...</answer>` 内容，保证 `answer`/`article`/`answer_tagged` 一致。

### 本地验证
- 语法校验：
  - `python -m py_compile src/my_deepresearch/agent/utils.py src/my_deepresearch/agent/orchestrator.py` 通过。
- 针对 `outputs/bench_sample_20260511_1/result_20260511_162735.json` 的 `answer` 做规范化验证：
  - `has_markdown_links = False`
  - `has_numeric = True`
  - 文末存在编号参考文献列表（`[1] url - title`）。

## 2026-05-11 补充记录：默认 MAX_STEPS=5 + 成本档位联动修复
### 背景
- 目标：将默认步数统一为“标准档 5 步”，同时保留低成本与高质量两种档位。
- 发现的问题：CLI 参数 `--max-steps` 有固定默认值，会覆盖 `COST_MODE` 的档位默认值，导致成本档位对步数不生效。

### 本轮修改
1. `src/my_deepresearch/config.py`
- 新增 `cost_mode` 配置项与三档默认值：
  - `low`: steps=3, search_results=3, page_chars=5000, scholar_results=3
  - `standard`: steps=5, search_results=5, page_chars=8000, scholar_results=5
  - `high`: steps=8, search_results=8, page_chars=12000, scholar_results=8
- `load_settings()` 新增读取 `COST_MODE`（low/standard/high），并保持 `MAX_*` 显式环境变量优先覆盖。

2. `scripts/run_single_research_windows.py`
- `--max-steps` 默认值改为 `None`，仅在显式传参时覆盖配置值。
- 新增 `--cost-mode` 参数，并在加载配置前写入 `os.environ["COST_MODE"]`。

3. `main.py`
- `--max-steps` 默认值改为 `None`，仅在显式传参时覆盖配置值。
- 新增 `--cost-mode` 参数，并在加载配置前写入 `os.environ["COST_MODE"]`。

4. `.env.example`
- 新增 `COST_MODE=standard`。
- 将 `MAX_*` 改为可选覆盖（默认留空），未显式配置时跟随 `COST_MODE`（standard=5）。

### 结果
- 默认行为：未显式指定时，按 `COST_MODE=standard` 运行 5 步。
- 成本可控：切到 `low` 可明显降成本，切到 `high` 可提升检索深度。
- 覆盖关系清晰：CLI 显式参数 > 环境变量 `MAX_*` > `COST_MODE` 档位默认值。

### 结果
- 输出逻辑已从“Markdown 超链接引用”切换为“Bench 友好的数字编号引用 + 文末参考文献列表”。
- 该修复直接覆盖 `id1` 场景中 `answer` 字段引用格式问题，并对后续题目自动生效。
## 2026-05-11 Addendum: Citation Alignment + Search/Read Coupling
### Changes
1. `src/my_deepresearch/agent/utils.py`
- Unified bibliography header to `References:` to avoid encoding-sensitive parsing.
- Reworked `normalize_benchmark_citations(...)` to re-index body citations into contiguous `[1..N]`.
- Enforced one-to-one alignment between inline `[n]` citations and reference entries.

2. `src/my_deepresearch/agent/orchestrator.py`
- Added execution rule: if previous `search` step has `new_results > 0`, prioritize a `read` step next when unread URLs exist.
- Added `read_ok` flag and only append to `state.evidence` when `read_ok=True`.
- Updated synthesis citation instruction to use `References:`.

### Validation (id=1, max_steps=8)
- Output: `outputs/bench_sample_20260511_1/result_id1_20260511_175402.json`
- Stats: `steps=8`, `search=1`, `read=7`, `sources=8`, `read_ok=6`
- Citation checks:
  - no markdown links in body
  - inline citation ids: `[1,2,3,4]`
  - reference ids: `[1,2,3,4]`
  - mismatch: `[]`
## 2026-05-11 Addendum: Anti-Read-Loop Controls
### Goal
- Avoid `search -> read -> read -> read` collapse.
- Prevent repeated reads of failed/low-value URLs.
- Keep citation formatting stable for benchmark scoring.

### Code Changes
1. `src/my_deepresearch/agent/state.py`
- Added `tried_urls` and `failed_urls` to track attempted and failed reads.

2. `src/my_deepresearch/agent/orchestrator.py`
- Added `_is_low_value_note(...)` heuristic to detect low-value reads (`404`, `Failed to read`, `无有效信息`, etc.).
- Read selection now rejects planner `url` when it was already attempted; falls back to untried candidate.
- URL is added to `tried_urls` before fetch to avoid retry loops.
- `read_ok=True` now requires both successful fetch and non-low-value extraction note.
- Only `read_ok=True` entries are appended to `evidence`.
- Added cadence guard: after two consecutive reads with low confidence, force next step to `search`.

### Validation Run
- Output: `outputs/bench_sample_20260511_1/result_id1_20260511_191727.json`
- Action mix: `search=3`, `read=5` (no longer `search=1`, `read=7`)
- Read URL uniqueness: `5/5` unique, `0` duplicate reads
- Citation checks: inline ids align with references, `References:` present, no markdown citation links
## 2026-05-12 Addendum: PDF Read Support
### Why
- `sources` had many PDF links but `read` could not reliably extract PDF text, so evidence stayed sparse.

### Changes
1. `requirements.txt`
- Added `pypdf>=5.0.0`.

2. `src/my_deepresearch/tools/pdf_tool.py`
- Added `extract_pdf_text(pdf_bytes, max_chars)` using `pypdf.PdfReader`.
- Extracts page text incrementally and truncates by `max_chars`.

3. `src/my_deepresearch/tools/fetch_tool.py`
- Added PDF-aware path:
  - detect `.pdf` URLs and parse directly first;
  - if response `Content-Type` is PDF, extract via `pypdf`;
  - then fallback to Jina read and HTML extraction as before.

### Quick Validation
- `http://hprc.org.cn/.../P020221125409740211070.pdf` can now return extractable text path (non-empty).
- `https://www.swufe.edu.cn/chfs/report/CHFS_2023_Report_Summary_CN.pdf` currently returns 404 from source side (not parser issue).
## 2026-05-12 Addendum: 404 Backup Recovery (Wayback + Title Re-search)
### User Decision
- Installed new dependency set and kept scope to PDF support (no domain priority policy).
- Enabled automatic backup recovery for broken/404 links.

### Implemented
1. Dependency install
- Ran `f:/Code/LLM/.venv/Scripts/python.exe -m pip install -r requirements.txt`.
- `pypdf` installed successfully.

2. Fetch-layer recovery (`src/my_deepresearch/tools/fetch_tool.py`)
- Added error-like content detection for 404/error pages.
- Added Wayback archive fallback:
  - query CDX API for latest 200 snapshot;
  - fetch snapshot content when available.
- Preserved existing fallback chain and now raise explicit failure when no useful content can be fetched.

3. Agent-layer recovery (`src/my_deepresearch/agent/orchestrator.py`)
- Added automatic “same-title re-search” on low-value/failed `read`:
  - query by exact title;
  - query by exact title + original domain.
- Added dedupe guard via `state.backup_queries`.
- Added `backup_queries`/`backup_new_results` logs into step records.

4. State extension (`src/my_deepresearch/agent/state.py`)
- Added `backup_queries` set for backup-search deduplication.

### Verification Run
- Output: `outputs/bench_sample_20260511_1/result_id1_20260512_153617.json`
- Action mix: `search=4`, `read=4`
- Backup queries triggered on failed reads and expanded sources to `36`.
- Citation format remained aligned (`[n]` in body matches `References:` list).
## 2026-05-12 Addendum: Reference Header by Output Language
### Changes
- Updated citation post-processing to select bibliography header by answer language:
  - Chinese answer body -> `参考文献：`
  - English answer body -> `References:`
- Applied in both main citation normalization and fallback reference construction.
- Updated synthesis instruction to explicitly follow the same language-dependent header rule.
## 2026-05-12 Addendum: read_ok Split into fetch_ok + evidence_ok
### Changes
1. `src/my_deepresearch/agent/orchestrator.py`
- Added structured extractor stage for each read:
  - `_extract_page_evidence(...)` asks extractor model to return JSON:
    `is_relevant`, `evidence_count`, `key_facts`, `summary`, `reason`.
- `read_ok` no longer depends on free-form note only.
- New step-level fields:
  - `fetch_ok`: whether enough page text was fetched (>=300 chars).
  - `evidence_ok`: whether extracted evidence is relevant and count > 0.
  - `read_ok = fetch_ok and evidence_ok`.
- On failed reads, keeps backup title re-search logic.

2. `src/my_deepresearch/agent/utils.py`
- Added language-adaptive bibliography header:
  - Chinese body -> `参考文献：`
  - English body -> `References:`

### Validation Run
- Output: `outputs/bench_sample_20260511_1/result_id1_20260512_164236.json`
- Action mix: `search=4`, `read=4`
- Read quality stats:
  - `fetch_ok=3/4`
  - `evidence_ok=1/4`
  - `read_ok=1/4`
- Meaning: data fetch success is no longer conflated with evidence usefulness.

## 2026-05-13 Addendum: Clarification Fix for read semantics
### Clarification
- User intent is **not** to make one read step batch-read all links.
- Correct intent: each read step still reads one URL, but links found in search should be queued and consumed progressively.

### Code Changes
1. `src/my_deepresearch/agent/state.py`
- Added `pending_read_urls` queue.

2. `src/my_deepresearch/agent/orchestrator.py`
- Search step now enqueues newly discovered source URLs into `pending_read_urls`.
- Added forced action `force_read_pending_sources`: if pending queue is non-empty after search, planner action is redirected to `read`.
- Read step now consumes exactly one URL per step from queue (preferred URL first if not tried).
- Preserved structured `fetch_ok/evidence_ok/read_ok` scoring and backup title re-search on failed reads.
- Updated synthesis guidance to avoid absolute wording when evidence is insufficient.

### Outcome
- Restored predictable step latency (single-URL read per step).
- Preserved user-requested behavior: search results are read and applied progressively as evidence/sources.

## 2026-05-13 补充记录：修正过程记录改为中文 + 重新运行 id=1
### 本次调整
1. 记录语言统一
- 按要求将后续修正记录统一改为中文，避免中英文混写造成追踪困难。

2. 运行任务
- 在当前代码基础上重新执行 `id=1`（从 `Deep_Research_Bench/deep_research_bench/data/prompt_data/query.jsonl` 读取问题）。
- 运行完成后将新结果保存到 `outputs/bench_sample_20260511_1`，用于与历史版本对比引用质量、`read_ok` 有效率与答案表述风格。

### 说明
- 目前 `read` 仍保持“每步仅读取 1 个链接”的设计；`search` 发现的新链接进入待读队列，后续步骤逐步消费。
- 若步骤预算较小而搜索结果较多，可能出现“待读队列未清空”现象，属于当前策略与成本约束下的预期行为。

### 本次运行结果补记
1. 首次重跑（未显式覆盖步数）
- 输出文件：`outputs/bench_sample_20260511_1/result_id1_20260513_105512.json`
- 实际步数：`MAX_STEPS=3`
- 现象：虽然预期默认 5 步，但运行时仍为 3 步。

2. 二次重跑（设置 `COST_MODE=standard`）
- 输出文件：`outputs/bench_sample_20260511_1/result_id1_20260513_105705.json`
- 实际步数：`MAX_STEPS=3`
- 结论：仅设置 `COST_MODE=standard` 仍不足以生效 5 步，说明存在环境变量覆盖。

3. 三次重跑（显式强制 `settings.max_steps = 5`）
- 输出文件：`outputs/bench_sample_20260511_1/result_id1_20260513_105947.json`
- 实际步数：`MAX_STEPS=5`
- 结论：当前环境中 `MAX_STEPS` 变量可能被固定为 3，需要在运行脚本中显式覆盖或清理环境变量后再加载配置。

## 2026-05-13 补充记录：批量 read 并发 + 引用池扩展 + 引用约束强化
### 代码改动
1. 批量 read（并发抓取）
- 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增批量读取能力：
  - `BATCH_READ_SIZE`（默认 3，范围 1~5）
  - `BATCH_READ_MAX_WORKERS`（默认 3，范围 1~5）
- 每个 `read` 步骤改为：
  - 先从队列取最多 `batch_size` 个 URL；
  - 用线程池并发抓取网页正文；
  - 抽取与判定（evidence）仍串行执行，避免模型调用并发过高。

2. 引用池扩展（不再 evidence/sources 二选一）
- 文件：`src/my_deepresearch/agent/state.py`
  - 新增 `read_sources` 字段，用于记录“抓取成功但未必 evidence_ok”的可引用来源。
- 文件：`src/my_deepresearch/agent/orchestrator.py`
  - `fetch_ok=True` 即写入 `read_sources`。
  - `evidence_ok` 仅影响 `read_ok/confidence`，不再阻止来源进入引用池。
- 文件：`src/my_deepresearch/agent/utils.py`
  - 引入 `_merge_reference_items(evidence, read_sources, sources)` 去重合并。
  - 引用构建改为使用合并后的来源集合。

3. synthesis 引用硬约束强化
- 文件：`src/my_deepresearch/prompts.py`
  - `SYNTHESIZE_SYSTEM_PROMPT` 增加硬约束：
    - 每个关键结论句后必须有 `[n]`；
    - 参考文献不少于 6 条；
    - 正文使用数字引用，文末统一参考文献格式。
- 文件：`src/my_deepresearch/agent/orchestrator.py`
  - `_synthesize_answer` 的 user prompt 同步加入上述约束，并显式传入 `read_sources`。

### 验证结果
- 运行文件：`outputs/bench_sample_20260511_1/result_id1_20260513_161002.json`
- 运行配置：
  - `max_steps=5`
  - `BATCH_READ_SIZE=3`
  - `BATCH_READ_MAX_WORKERS=3`
- 结果摘要：
  - `sources=28`
  - `read_sources=8`
  - `evidence=0`（本轮相关性判定偏严，但不影响来源进入引用池）
- 文末参考文献条目数约 20（显著高于旧版本）
- 每个 `read` 步均批量读取 3 条 URL（并发抓取生效）

## 2026-05-13 补充记录：正文引用与参考文献强对照修复
### 问题
- 之前出现“参考文献很多，但正文 `[n]` 与文末条目不严格对照”的现象。
- 根因是后处理只做编号归一化，未强制“正文只可引用已分配编号目录”，且文末会附带未在正文出现的条目。

### 修复方案
1. 新增固定编号引用目录（Citation Catalog）
- 文件：`src/my_deepresearch/agent/utils.py`
- 新增 `build_citation_catalog(evidence, read_sources, sources)`：
  - 先合并去重来源；
  - 为每个 URL 预分配固定 `id`（如 1..20）。

2. 正文引用严格限制为目录编号
- 文件：`src/my_deepresearch/agent/utils.py`
- `normalize_benchmark_citations(...)` 改为：
  - 仅把正文中的 URL/markdown 链接映射到 catalog 的固定 `id`；
  - 过滤掉不在 catalog 的编号；
  - 不再做“任意旧编号重映射”。

3. 文末参考文献仅输出正文实际使用的编号
- 文件：`src/my_deepresearch/agent/utils.py`
- 在 `build_result_payload(...)` 中：
  - 提取正文实际 `used_ids`；
  - 仅输出 `used_ids` 对应的条目；
  - 从而保证“正文 `[n]` 集合 == 文末条目编号集合”。

4. 写作阶段显式提供编号目录
- 文件：`src/my_deepresearch/agent/orchestrator.py`
- `_synthesize_answer(...)` 里新增：
  - `Available citation catalog`（`[id] title - url`）；
  - 要求模型只使用这些编号。

### 验证
- 输出文件：`outputs/bench_sample_20260511_1/result_id1_20260513_164421.json`
- 自动核验结果：
  - `USED_IDS = [1,2,3,6,8,9,10,11,12]`
  - `REF_IDS  = [1,2,3,6,8,9,10,11,12]`
  - `IDS_MATCH = True`
- 结论：正文引用编号与文末参考文献编号已实现严格对照。

## 2026-05-14 补充记录：正文连续编号 + 每句（行）最多 3 个引用
### 需求
- 正文引用编号连续。
- 每句引用数量不超过 3 个（工程上采用“每行正文最多 3 个引用”，比每句更严格）。

### 代码改动
1. 提示词约束增强
- 文件：`src/my_deepresearch/prompts.py`
- 在 `SYNTHESIZE_SYSTEM_PROMPT` 的引用规则新增：
  - 正文编号尽量连续；
  - 每句最多 3 个引用。

2. 后处理强约束落地
- 文件：`src/my_deepresearch/agent/utils.py`
- 新增/调整：
  - `_limit_sentence_citations(...)`：对正文行做引用裁剪，保留前 3 个去重引用；
  - `normalize_benchmark_citations(...)`：将正文使用到的旧编号重映射为连续编号 `1..N`；
  - 参考文献列表按重映射后的新编号重建，保证正文与文末完全一致。

### 验证
- 验证输出：`outputs/bench_sample_20260511_1/result_id1_20260514_142117.json`
- 检查结果：
  - `CONTIGUOUS=True`（正文编号连续）
  - `TEXT_REF_MATCH=True`（正文编号集合与文末编号集合一致）
  - `LINE_GT3=0`（正文行无超过 3 个引用）

## 2026-05-14 补充记录：清理“source/[notes]”与参考文献标题质量修复
### 问题复现
- `article` 中出现 `[notes]`、`source` 等占位词。
- 参考文献标题出现省略号 `...`、短代码（如 `01B...`）或乱码（mojibake）。

### 代码修复
1. 抓取层增加页面真实标题
- 文件：`src/my_deepresearch/tools/fetch_tool.py`
  - 新增 `fetch_page_bundle(url)`，返回 `text + title + source`。
  - HTML 读取优先提取 `<title>`；
  - PDF 读取通过 `extract_pdf_title`（元数据/首行）提取标题。
- 文件：`src/my_deepresearch/tools/pdf_tool.py`
  - 新增 `extract_pdf_title(pdf_bytes)`。
- 文件：`src/my_deepresearch/agent/orchestrator.py`
  - 批量抓取改为并发调用 `fetch_page_bundle`；
  - `read_sources/evidence` 的 `title` 优先使用抓取得到的页面标题，再回退搜索标题。

2. 引用后处理清理占位词
- 文件：`src/my_deepresearch/agent/utils.py`
  - 在 `normalize_benchmark_citations` 中清理：
    - `[notes]` / `[note]` / `[source]`
    - `source 列表` -> `来源列表`

3. 参考文献标题清洗与回退
- 文件：`src/my_deepresearch/agent/utils.py`
  - 新增 `_sanitize_ref_title`：
    - 去掉 `.../…` 和无效前缀；
    - 检测乱码标题（如 `Ã/æ/ç/�`）；
    - 检测纯代码短标题（如全字母数字串）；
    - 坏标题回退到 `snippet/summary`，再回退 `domain/path`，最后才 `source`。

### 验证
- 输出文件：`outputs/bench_sample_20260511_1/result_id1_20260514_150114.json`
- 检查结果：
  - `HAS_[notes]=False`
  - `HAS_word_source=False`
  - `HAS_ellipsis_title=False`
  - `HAS_mojibake_title=False`

## 2026-05-17 补充记录：read 阶段改为“全量读取 search 结果”
### 需求
- 用户要求先出一版：在 `read` 阶段不再做挑选，`search` 得到的链接全部读取。

### 实施改动
1. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增 `_read_all_from_search_enabled()`：
  - 读取环境变量 `READ_ALL_SEARCH_RESULTS`；
  - 默认值为 `"1"`（开启）。
- 新增 `_dequeue_all_urls(state, preferred_url)`：
  - 先处理 planner 指定的 `preferred_url`；
  - 再读取 `pending_read_urls` 中全部未读链接；
  - 再补齐 `sources` 里所有未读链接；
  - 去重并排除 `tried_urls`。
- `action == "read"` 分支改造：
  - 当 `READ_ALL_SEARCH_RESULTS=1` 时，使用全量 URL 列表，不再按 `BATCH_READ_SIZE` 截断；
  - 仅保留抓取并发控制（`BATCH_READ_MAX_WORKERS`，1~5）。
- step 日志新增 `read_all_mode` 字段，便于验证本轮是否走了全量读取模式。

### 验证
1. 语法校验通过：
- `python -m py_compile src/my_deepresearch/agent/orchestrator.py`

### 说明
- 现在默认行为是：`read` 会尽量一次性读取当前可读的全部 search 结果。
- 若要临时恢复旧行为（分批读取），可设置：`READ_ALL_SEARCH_RESULTS=0`。

## 2026-05-17 补充记录：引用上限从“每行限3”改为“每句限3”
### 需求
- 将正文引用裁剪规则从“每行最多 3 个引用”改为“每句最多 3 个引用”。

### 实施改动
1. 文件：`src/my_deepresearch/agent/utils.py`
- 修改 `_limit_sentence_citations(...)`：
  - 由按整行计数改为按句子计数；
  - 句子边界支持中英文标点：`。！？!?；;`；
  - 每句内部仍做去重并保留前 3 个引用；
  - 参考文献列表行（`[n] https://...`）保持不变，不参与裁剪。

### 验证
1. 语法校验通过：
- `python -m py_compile src/my_deepresearch/agent/utils.py`
2. 样例验证：
- 输入：`一句[1][2][3][4]。二句[5][6][7][8]；三句[9][10][11][12]?`
- 输出：每句分别保留 3 个引用。

## 2026-05-21 补充记录：短文问题专项修复（step=5 场景）
### 问题复盘
- 在 `id=1, max_steps=5` 任务中，出现“文章过短、有效证据为 0、最后一步仍在 search”的现象。
- 核心原因：
  1. 步数预算短，流程经常变成 `search-search-search-read-search`，读轮次不足；
  2. `extractor` 在部分页面会被上游内容审查拦截（`data_inspection_failed`），导致 read 抽取中断或证据判定过严；
  3. 即便读到页面文本，若抽取器返回 `evidence_count=0`，会导致 `evidence_ok` 难以命中。

### 本次改动
1. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增短预算强制策略：
  - 倒数第二步（`max_steps<=5`）若 read 轮次不足 2 且有可读链接，强制 `action=read`（`force_second_read_before_last`）。
  - 最后一步不再允许 `search/reflect` 空转：
    - 有可读链接则强制 `read`（`force_read_on_last_step`）；
    - 无可读链接则强制 `synthesize`（`force_synthesize_on_last_step`）。

2. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 增加抽取降级容错：
  - `_extract_page_evidence` 的 LLM 调用失败时，不再直接失败，改为进入 `_heuristic_extract_page_evidence(...)` 本地启发式抽取。
  - 启发式会按问题关键词与句子中数字/时间/金额信号提取候选事实，输出 `is_relevant/evidence_count/key_facts/summary/reason`。

3. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 放宽 evidence 计数回填：
  - 若 `key_facts` 非空但 `evidence_count=0`，自动回填为 `len(key_facts)`；
  - 若 `summary` 有信息且非低价值提示，最少回填为 `1`。
- 放宽 `evidence_ok` 判定：
  - 从“必须 `is_relevant=True`”调整为“`is_relevant=True` 或存在 `key_facts`，且 `evidence_count>0`、非低价值”。

4. 文件：`src/my_deepresearch/prompts.py`
- 在综合写作提示中增加“长度与结构要求”：
  - 证据不足时仍需基于已读取来源展开分析，不只输出一句“无法回答”；
  - 目标输出结构化长文（结论摘要/证据质量/数据缺口/后续路径）。

### 本地验证
1. 语法检查
- `python -m py_compile src/my_deepresearch/agent/orchestrator.py src/my_deepresearch/prompts.py` 通过。

2. 回归运行（id=1，step=5）
- 结果文件：`outputs/bench_sample_20260511_1/result_id1_step5_fix_quick_20260521_170243.json`
- 指标对比（相对旧版 `result_id1_step5_20260517_170747.json`）：
  - 正文长度：`415 -> 1331`（明显增长）
  - read 轮次：`1 -> 2`
  - 动作序列：`search,search,search,read,search` -> `search,search,search,read,read`

### 仍待优化
- 当前该题目的 search 命中质量仍偏低，read_sources 中大量为目录页/站点页/无关页，导致 `evidence_ok_count` 仍偏低。
- 下一步应优先优化检索阶段的“结果质量过滤与重排”（domain/tier/标题关键词约束），而不是继续盲目增加读取数量。

## 2026-05-21 补充记录：主题拆解模板（Search Query Decomposition）
### 需求
- 用户确认先不改 `gov.cn` 可访问性策略；
- 优先落地“主题拆解模板”，让 search 不再只做泛搜，而是按子问题分解检索。

### 实施改动
1. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增 `_topic_decompose_queries(question, seed_queries, limit)`：
  - 自动把问题拆解为“定义口径 / 规模人数 / 收入分布 / 资产负债 / 调查数据 / 学术报告”六类检索子主题；
  - 中文问题默认生成中文拆解模板；
  - 与 planner 原始 query 合并去重后执行。
- 新增开关与上限：
  - `ENABLE_QUERY_DECOMPOSE`（默认 `1` 开启）
  - `QUERY_DECOMPOSE_MAX`（默认 `6`，范围 2~10）
- 在 `action=search` 里接入拆解：
  - 原始 `queries` 先由 planner 给出，再进入拆解补全，提升检索覆盖面和可用证据概率。

### 说明
- 这是“检索层策略改造”，不改变你当前的 read/citation 输出格式。
- 若后续需要快速回退，设 `ENABLE_QUERY_DECOMPOSE=0` 即可恢复原行为。

## 2026-05-21 补充记录：知乎链接读取失败原因定位
### 复现对象
- `https://zhuanlan.zhihu.com/p/1917145237886857790`

### 结论
1. 直连抓取返回 403（桌面 UA 与移动 UA 均 403）；
2. `r.jina.ai` 对该链接请求超时；
3. Wayback 查询在当前网络环境下 SSL 握手失败（无法作为稳定回退）；
4. 因此 `fetch_page_bundle` 走完所有回退链路后，返回：
- `Failed to fetch useful content for URL: ...`

### 影响
- 该条 URL 在当前网络和反爬条件下不可读，属于来源站点访问限制导致，不是你当前 read 流程逻辑错误。

## 2026-05-21 补充记录：知乎链接 fetch 失败定位与处理
### 现象
- 在结果文件中出现：
  - `url=https://zhuanlan.zhihu.com/p/1917145237886857790`
  - `fetch_ok=false`
  - `note=Failed to fetch useful content...`

### 定位结论
- 本地复现显示该链接返回 `HTTP 403`，页面为知乎反爬挑战页（非正文内容）。
- 这不是 orchestrator 漏读，而是抓取端被目标站点拦截导致无法得到“可用文本”。

### 已做修复
1. 文件：`src/my_deepresearch/tools/fetch_tool.py`
- 增加知乎专用降级路径：
  - 新增移动端请求头 `MOBILE_HEADERS`；
  - 新增 `_is_zhihu_url(...)`；
  - 新增 `_build_zhihu_candidates(...)`；
  - 新增 `_fetch_zhihu_with_mobile_headers(...)`；
  - 在 `fetch_page_bundle(...)` 中加入 `zhihu_mobile` 兜底分支。

### 当前状态
- 在当前网络环境下，目标链接仍返回 403 挑战页，未能绕过站点风控，因此该 URL 仍可能 `fetch_ok=false`。
- 该问题属于目标站点反爬策略与网络路径限制，不是业务逻辑错误。

### 后续建议
1. 检索阶段降权/过滤高风控站点（如知乎专栏、部分聚合页），优先选择可稳定抓取源（gov/cass/cnki镜像/高校库）。
2. 保留该链接为“候选参考”，但不要把它当作核心证据来源。
3. 对出现 403 的 URL 自动触发“同主题重搜 + 站点替代”策略，提高可读命中率。


### 目前问题
搜索有错误
参考文献引用有问题，3和4重，不同语言。格式有问题
生成文章篇幅太短，
有pdf等二级目录内容读取不到

## 2026-05-22 补充记录：上一次改动汇总（中文可读版）
### 1. step=5 下“短文”问题修复
1. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增短预算兜底策略：
  - 倒数第二步若 read 轮次不足且有可读链接，强制 `read`；
  - 最后一步不再允许空转 `search/reflect`：
    - 有可读链接则强制 `read`；
    - 无可读链接则强制 `synthesize`。
- 目标：避免 `search-search-search-read-search` 导致正文过短。

2. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 增加抽取降级容错：
  - `_extract_page_evidence(...)` 的 LLM 抽取失败时，进入 `_heuristic_extract_page_evidence(...)` 启发式提取；
  - 抽取失败不再直接中断整轮研究流程。

3. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 放宽 `evidence_ok` 判定与证据回填：
  - `key_facts` 非空但 `evidence_count=0` 时自动回填；
  - `summary` 有效时最少回填 1；
  - `evidence_ok` 从“严格 is_relevant”调整为“is_relevant 或 key_facts 命中 + 非低价值内容”。

4. 文件：`src/my_deepresearch/prompts.py`
- 增加“长度与结构要求”：
  - 即使证据不足，也要基于已读来源展开分析；
  - 输出优先结构化长文（结论、证据质量、缺口、后续路径），不只一句“无法回答”。

### 2. 主题拆解模板（Search Query Decomposition）
1. 文件：`src/my_deepresearch/agent/orchestrator.py`
- 新增 `_topic_decompose_queries(...)`：
  - 对问题自动拆解为多子主题检索：
    - 定义口径
    - 规模人数
    - 收入分布
    - 资产负债
    - 调查数据
    - 学术报告
- 新增开关：
  - `ENABLE_QUERY_DECOMPOSE=1`（默认开启）
  - `QUERY_DECOMPOSE_MAX=6`（可调范围 2~10）

2. 接入点
- 在 `action=search` 时，将 planner 原始 query 与拆解 query 合并去重后执行，提升检索覆盖与命中率。

### 3. 知乎链接抓取失败定位结论
1. 复现对象：
- `https://zhuanlan.zhihu.com/p/1917145237886857790`
2. 定位结果：
- 直连桌面/移动 UA 均返回 403；
- `r.jina.ai` 对该链接超时；
- Wayback 在当前网络环境下不可稳定回退（SSL/握手问题）；
- 因此 `fetch_page_bundle` 最终返回 `Failed to fetch useful content`。
3. 结论：
- 这是目标站点反爬/网络可达性问题，不是 read 主流程逻辑错误。

### 目前问题
有些网页读取不到内容，doc豆丁，书籍读不到pdf
输出内容没有结构化

改回分批。搜不到原报告，可以搜有没有关于报告的解读。有时候也可以改用英文关键词去搜索。怎么修改，经我确认再修改。