# Speclink Test Plan — 75/20/5 Distribution

## Distribution Rule

| Type   | Ratio | Target Count | Location                    |
|--------|-------|-------------|-----------------------------|
| Unit   | 75%   | ~90 tests   | `tests/unit/`               |
| Integration | 20% | ~24 tests   | `tests/integration/`        |
| E2E    | 5%    | ~6 tests    | `tests/e2e/`                |
| **Total** |      | **~120**    |                             |

## What Each Type Covers

### Unit Tests (75%) — Isolated Logic
- Pure functions: path construction, markdown parsing, code extraction, diff computation
- Data models: PipelineConfig, CodeElement, Section, DocMap construction + validation
- Individual functions with mocked deps: LLMClient (mock API), Store (mock fs), Classifier (mock LLM)
- Edge cases, error handling, boundary conditions per function
- No I/O, no network, no filesystem — all mocked or pure

**Modules to test:**
- `core/models.py` — model construction, from_json, Section.id property
- `core/config.py` — PipelineConfig defaults, env overrides
- `core/paths.py` — speclink_root, config_path, docmap_path, atomic_write, get_head_sha
- `core/logging.py` — format_stats
- `preprocessing/code_extraction.py` — extract, signature, make_symbol
- `preprocessing/code.py` — collect_signatures_and_bodies, scan, load_gitignore
- `preprocessing/markdown.py` — parse_markdown, get_section, replace_section, ParagraphChunker methods
- `retrieval/classifier.py` — build_prompt logic
- `retrieval/reranker.py` — rerank with mock API
- `retrieval/incremental.py` — detect_changes, resolve_from_cache, merge_unchanged
- `retrieval/stages.py` — group_by_heading, _top_files_by_rerank, _build_sig_map, build_doc_map
- `rewrite/batch.py` — change type logic (match/case), reason mapping
- `rewrite/diff.py` — git status char parsing, diff parsing logic
- `rewrite/rewriter.py` — rewrite logic with mocked LLM
- `core/llm.py` — LLMClient with mock responses
- `core/store.py` — Store with mock filesystem
- `wizard.py` — list_markdown_files, generate_workflow
- `cli.py` — CLI command registration

### Integration Tests (20%) — Module Interactions
- Preprocessing pipeline: code.py + code_extraction.py together on real files
- Markdown pipeline: parse + chunk + Section creation on real markdown files
- Retrieval pipeline: stages.preprocess → stages.retrieve → stages.classify with mocked LLM
- Store + filesystem: real temp dirs, real JSON read/write
- CLI commands: typer CliRunner with mocked deps, verifying output
- Incremental change detection with real DocMap structures
- Rewrite diff + batch pipeline interaction

### E2E Tests (5%) — Full User Workflows
- `speclink sync` on a temp git repo with docs + code → verify docmap output
- `speclink analyze` on a temp repo → verify analysis report
- Full pipeline: create repo → add docs → add code → sync → verify mappings

## Directory Structure

```
tests/
├── conftest.py              # Shared fixtures (git helpers, mock configs)
├── unit/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_paths.py
│   ├── test_logging.py
│   ├── test_code_extraction.py
│   ├── test_code.py
│   ├── test_markdown.py
│   ├── test_classifier.py
│   ├── test_reranker.py
│   ├── test_incremental.py
│   ├── test_stages.py
│   ├── test_batch.py
│   ├── test_diff.py
│   ├── test_rewriter.py
│   ├── test_llm.py
│   ├── test_store.py
│   ├── test_wizard.py
│   └── test_cli.py
├── integration/
│   ├── __init__.py
│   ├── test_preprocessing_pipeline.py
│   ├── test_markdown_pipeline.py
│   ├── test_retrieval_pipeline.py
│   ├── test_store_filesystem.py
│   ├── test_cli_commands.py
│   ├── test_incremental_pipeline.py
│   └── test_rewrite_pipeline.py
└── e2e/
    ├── __init__.py
    ├── test_sync_flow.py
    └── test_analyze_flow.py
```
