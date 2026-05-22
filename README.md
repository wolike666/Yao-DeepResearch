# My-DeepResearch-2

面向单问题交互的 DeepResearch 框架，参考 Alibaba-NLP-DeepResearch 的执行思路做了中度对齐。

## 本次对齐范围

1. 模块拆分：核心循环由单体 engine 拆分为 state、planner、reflector、orchestrator。
2. 工具体系：保留 web search、web read、scholar search 三类工具。
3. 接口模式：继续使用 OpenAI 兼容接口。
4. 运行方式：只做单问题交互，不包含评测链路。
5. 输出策略：主输出为 answer，同时保留 answer_tagged 便于调试。
6. 配置复用：可直接复用 Alibaba 项目的 .env 与密钥字段。

## 目录结构

- main.py: 兼容入口（单问题）
- scripts/run_single_research_windows.py: Windows 单问题运行脚本（对齐 Alibaba 风格）
- src/my_deepresearch/config.py: 配置读取与字段兼容
- src/my_deepresearch/engine.py: 兼容层，转发到 orchestrator
- src/my_deepresearch/agent/state.py: 研究状态数据结构
- src/my_deepresearch/agent/planner.py: 规划提示与状态压缩
- src/my_deepresearch/agent/reflector.py: 反思阶段逻辑
- src/my_deepresearch/agent/orchestrator.py: 主循环编排
- src/my_deepresearch/tools/search_tool.py: Web 搜索（Serper/DDGS）
- src/my_deepresearch/tools/scholar_tool.py: Scholar 搜索（Serper Scholar）
- src/my_deepresearch/tools/fetch_tool.py: 网页读取（Jina/requests+bs4）

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配置环境变量

```bash
copy .env.example .env
```

3. 运行单问题

```bash
python main.py --question "2026年佛山大学有几项成果获评广东省高校党建研究优秀成果奖？"
```

或使用对齐脚本：

```bash
python scripts/run_single_research_windows.py --question "帮我调研DeepResearch"
```

## 环境变量说明

优先读取字段：

- OPENAI_API_KEY
- OPENAI_BASE_URL
- OPENAI_MODEL

回退读取字段（兼容 Alibaba 配置）：

- API_KEY
- API_BASE
- INFER_MODEL_NAME
- MODEL_PATH

工具密钥：

- SERPER_KEY_ID
- JINA_API_KEYS

可选复用 Alibaba 项目 .env：

- ALIBABA_ENV_PATH=F:/Code/LLM/Alibaba-NLP-DeepResearch/.env

## 输出说明

每次运行会生成 outputs/result_YYYYMMDD_HHMMSS.json，主要字段：

- question: 原问题
- answer: 最终答案正文
- answer_tagged: 带 think/answer 标签的完整内容
- steps: 每轮动作日志
- notes: 网页摘要与异常记录
- sources: 去重后的来源
- reflections: 每轮反思结果

## 已知边界

1. 仅支持单问题流程，不包含批量评测脚本。
2. 某些页面存在反爬限制，read 阶段可能失败。
3. 当前未接入文件解析工具（PDF/Office），后续可扩展。
