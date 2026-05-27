# My-DeepResearch-2

A single-question DeepResearch framework aligned to the execution style of Alibaba-NLP-DeepResearch.

This project focuses on an iterative research loop:
`plan -> search -> read -> reflect -> synthesize`

## Highlights

- Single-question interactive research pipeline
- OpenAI-compatible model interface
- Web search + scholar search + web reading toolchain
- Batched read with configurable concurrency
- Citation catalog + inline citation normalization
- Benchmark-friendly JSON output format

## Project Structure

- `main.py`: CLI entry for one research question
- `scripts/run_single_research_windows.py`: Windows-friendly single-run script
- `src/my_deepresearch/config.py`: environment/config loading with fallback fields
- `src/my_deepresearch/engine.py`: compatibility wrapper
- `src/my_deepresearch/agent/`: state/planner/reflector/orchestrator
- `src/my_deepresearch/tools/search_tool.py`: web search
- `src/my_deepresearch/tools/scholar_tool.py`: scholar search
- `src/my_deepresearch/tools/fetch_tool.py`: page reading (Jina + requests/bs4 + fallbacks)
- `scripts/json_answer_to_md.py`: export JSON answer to Markdown
- `Deep_Research_Bench/`: benchmark and dataset submodules

## Quick Start

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Create env file

```bash
copy .env.example .env
```

3. Fill required keys in `.env` (model key is required; search/read keys are recommended)

4. Run one question

```bash
python main.py --question "Help me research the current state of China's middle class"
```

or

```bash
python scripts/run_single_research_windows.py --question "Help me research DeepResearch frameworks"
```

## Key Environment Variables

Model (priority):

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

Fallback model fields (Alibaba-compatible):

- `API_KEY`
- `API_BASE`
- `INFER_MODEL_NAME`
- `MODEL_PATH`

Tool keys:

- `SERPER_KEY_ID`
- `JINA_API_KEYS`

Optional shared env:

- `ALIBABA_ENV_PATH=F:/Code/LLM/Alibaba-NLP-DeepResearch/.env`

Research controls:

- `COST_MODE=low|standard|high`
- `MAX_STEPS`
- `MAX_SEARCH_RESULTS`
- `MAX_PAGE_CHARS`
- `MAX_SCHOLAR_RESULTS`
- `SEARCH_MODE=web|scholar|hybrid`
- `SOURCE_POLICY=balanced|strict`

Read and query strategy:

- `READ_ALL_SEARCH_RESULTS=0` (default batched read)
- `ENABLE_INTERPRETATION_QUERY=1` (allow interpretation-summary queries)
- `ENABLE_EN_QUERY_FALLBACK=1` (append one English fallback query)
- `QUERY_DECOMPOSE_MAX=6`

## Output

Each run writes a JSON file to `outputs/`, for example:

- `outputs/result_YYYYMMDD_HHMMSS.json`

Main fields:

- `prompt` / `question`
- `answer`
- `answer_tagged`
- `article`
- `steps`
- `notes`
- `sources`
- `read_sources`
- `reflections`

## Submodules

This repository includes benchmark/data submodules under `Deep_Research_Bench/`.

After clone:

```bash
git submodule update --init --recursive
```

## Known Limitations

1. The framework is optimized for single-question workflow, not full production serving.
2. Some websites may block automated readers (anti-bot, auth gate, or network restrictions).
3. Read success does not always mean high-value evidence; extraction quality still depends on model judgment.

## License

Please follow the license terms of this repository and each included submodule/dataset source.
