# Yao-DeepResearch

一个面向单问题交互的 DeepResearch 框架，整体流程对齐 Alibaba-NLP-DeepResearch 的执行风格。

核心流程：
`plan -> search -> read -> reflect -> synthesize`

## 项目特点

- 支持单问题交互式研究
- 兼容 OpenAI 接口
- 集成网页搜索、学术搜索、网页阅读
- `read` 支持分批并发抓取
- 支持来源聚合、引用归一化、正文内联引用
- 输出兼容 DeepResearch-Bench 风格的 JSON 结果

## 目录结构

- `main.py`：单问题 CLI 入口
- `scripts/run_single_research_windows.py`：Windows 单次运行脚本
- `src/my_deepresearch/config.py`：配置读取与环境变量兼容
- `src/my_deepresearch/engine.py`：兼容层入口
- `src/my_deepresearch/agent/`：状态、规划、反思、主循环
- `src/my_deepresearch/tools/search_tool.py`：网页搜索
- `src/my_deepresearch/tools/scholar_tool.py`：学术搜索
- `src/my_deepresearch/tools/fetch_tool.py`：网页抓取与阅读（Jina + requests/bs4 + fallback）
- `scripts/json_answer_to_md.py`：JSON 转 Markdown
- `Deep_Research_Bench/`：基准测试与数据子模块

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 复制环境文件

```bash
copy .env.example .env
```

3. 配置 `.env`

至少需要模型相关配置；搜索和阅读相关 key 建议一并配置。

4. 运行单问题

```bash
python main.py --question "帮我调研中国中产阶层现状"
```

或者：

```bash
python scripts/run_single_research_windows.py --question "帮我调研 DeepResearch 框架"
```

## 环境变量

模型优先项：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

兼容 Alibaba 的回退字段：

- `API_KEY`
- `API_BASE`
- `INFER_MODEL_NAME`
- `MODEL_PATH`

工具密钥：

- `SERPER_KEY_ID`
- `JINA_API_KEYS`


研究参数：

- `COST_MODE=low|standard|high`
- `MAX_STEPS`
- `MAX_SEARCH_RESULTS`
- `MAX_PAGE_CHARS`
- `MAX_SCHOLAR_RESULTS`
- `SEARCH_MODE=web|scholar|hybrid`
- `SOURCE_POLICY=balanced|strict`

阅读与查询策略：

- `READ_ALL_SEARCH_RESULTS=0`：默认分批阅读
- `ENABLE_INTERPRETATION_QUERY=1`：允许补充“解读/综述”类查询
- `ENABLE_EN_QUERY_FALLBACK=1`：对中文问题附加 1 条英文回退查询
- `QUERY_DECOMPOSE_MAX=6`

## 输出说明

每次运行会在 `outputs/` 下生成一个 JSON 文件，例如：

- `outputs/result_YYYYMMDD_HHMMSS.json`

主要字段：

- `prompt` / `question`
- `answer`
- `answer_tagged`
- `article`
- `steps`
- `notes`
- `sources`
- `read_sources`
- `reflections`

## 子模块

仓库包含 `Deep_Research_Bench/` 下的基准与数据子模块。

克隆后执行：

```bash
git submodule update --init --recursive
```

## 已知限制

1. 当前框架主要面向单问题研究，不是完整的生产级服务。
2. 部分网站可能有反爬、权限或网络限制，导致阅读失败。
3. 读取成功不等于高质量证据，证据抽取仍依赖模型判断。

## 许可

请遵守本仓库及各子模块/数据来源对应的许可协议。
