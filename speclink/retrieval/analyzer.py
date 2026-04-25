import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from speclink.core.config import PipelineConfig
from speclink.core.logging import log_stage
from speclink.core.models import DocMap, Section
from speclink.core.paths import (
    config_path,
    docmap_path,
    get_head_sha,
    load_docs,
)
from speclink.core.store import Store
from speclink.preprocessing.code import CodePreprocessor, FilePreprocessor
from speclink.preprocessing.markdown import ParagraphChunker

from .classifier import ReasoningClassifier
from .incremental import (
    ChangeDetection,
    detect_changes,
    merge_unchanged,
    resolve_from_cache,
)
from .reranker import Reranker
from .stages import (
    CandidateResult,
    PreprocessResult,
    RetrieveResult,
    _build_sig_map,
    build_doc_map,
    classify,
    group_by_heading,
    preprocess,
    retrieve,
)



class AnalysisReport(NamedTuple):
    total_sections: int
    doc_files: int
    cached_sections: int
    new_sections: int
    input_tokens: int
    output_tokens: int
    reranker_tokens: int = 0


@dataclass
class AnalysisContext:
    docs_path: Path
    code_path: Path
    repo_root: Path
    doc_files: list[Path]
    existing_doc_map: DocMap | None
    skip_cache: bool
    eval_mode: bool
    codebase_sha: str
    config: PipelineConfig
    store: Store
    text_preprocessor: ParagraphChunker
    code_preprocessor: CodePreprocessor
    file_preprocessor: FilePreprocessor
    reranker: Reranker
    classifier: ReasoningClassifier
    on_step: Callable[[str, str], None] | None = None

    t_start: float = 0.0
    pre: PreprocessResult | None = None
    change: ChangeDetection | None = None
    variables_map: dict[str, list[str]] = field(default_factory=dict)
    sections_to_process: list[Section] = field(default_factory=list)
    heading_to_sections: dict[tuple[str, str, int], list[Section]] = field(
        default_factory=dict
    )
    file_ids: list[str] = field(default_factory=list)
    candidate_results: list[CandidateResult] = field(default_factory=list)
    retrieval: RetrieveResult | None = None
    doc_map: DocMap | None = None
    all_sections: list[Section] = field(default_factory=list)
    cached_sections: int = 0
    new_sections: int = 0


async def _preprocess(ctx: AnalysisContext) -> None:
    pre, stats = await preprocess(
        ctx.docs_path,
        ctx.code_path,
        ctx.text_preprocessor,
        ctx.code_preprocessor,
        ctx.file_preprocessor,
        doc_files=ctx.doc_files,
    )
    ctx.pre = pre
    log_stage(
        "scanning",
        elapsed=f"{time.monotonic() - ctx.t_start:.1f}s",
        stats={
            "docs": stats.docs,
            "files": stats.code_files,
            "sections": stats.sections,
        },
    )


async def _classify_levels(ctx: AnalysisContext) -> bool:
    ctx.change = detect_changes(ctx.pre, ctx.existing_doc_map, ctx.skip_cache)

    ctx.file_ids = sorted({fe.file_path for fe in ctx.pre.file_elements})

    ctx.sections_to_process = ctx.change.changed_sections
    if not ctx.sections_to_process:
        if ctx.on_step:
            ctx.on_step("2/5", "All cached, skipping...")
        doc_map, cached, new = resolve_from_cache(ctx.change)
        ctx.doc_map = doc_map
        ctx.cached_sections = cached
        ctx.new_sections = new
        return True
    return False


async def _retrieve(ctx: AnalysisContext) -> None:
    ctx.heading_to_sections = group_by_heading(ctx.sections_to_process)
    sig_map = _build_sig_map(ctx.pre.symbols)
    ctx.variables_map = ctx.code_preprocessor.variables_map
    candidates, headings, total_candidates = await retrieve(
        ctx.heading_to_sections,
        ctx.pre.file_elements,
        ctx.file_ids,
        ctx.reranker,
        ctx.config,
        sig_map=sig_map,
        variables_map=ctx.variables_map,
    )
    ctx.candidate_results = candidates


async def _classify(ctx: AnalysisContext) -> None:
    retrieval, headings, matches = await classify(
        ctx.candidate_results,
        ctx.heading_to_sections,
        ctx.classifier,
        ctx.config,
        symbols=ctx.pre.symbols,
        variables_map=ctx.variables_map,
    )
    ctx.retrieval = retrieval
    log_stage(
        "linking",
        elapsed=f"{time.monotonic() - ctx.t_start:.1f}s",
        stats={"sections": headings, "connections": matches},
    )


async def _build(ctx: AnalysisContext) -> None:
    merge_unchanged(ctx.retrieval, ctx.change)
    ctx.all_sections = ctx.change.changed_sections + ctx.change.unchanged_sections
    ctx.doc_map = build_doc_map(
        ctx.retrieval.heading_to_files,
        ctx.all_sections,
        ctx.retrieval.heading_to_classifications,
    )
    if ctx.eval_mode:
        _save_eval_data(ctx)


def _save_eval_data(ctx: AnalysisContext) -> None:
    reranker_entries = []
    for (doc_file, heading, _), scores in {
        cr.key: cr.rerank_scores for cr in ctx.candidate_results
    }.items():
        for file_path, score in scores.items():
            reranker_entries.append(
                {
                    "doc_file": doc_file,
                    "heading": heading,
                    "file": file_path,
                    "score": round(score, 2),
                }
            )
    ctx.store.save_eval(
        "reranker",
        ctx.config.rerank_model,
        reranker_entries,
        input_tokens=getattr(ctx.reranker, "total_tokens", 0),
        eval_mode=True,
    )

    classifier_entries = []
    for (
        doc_file,
        heading,
        _,
    ), classifs in ctx.retrieval.heading_to_classifications.items():
        for clf in classifs:
            classifier_entries.append(
                {
                    "doc_file": doc_file,
                    "heading": heading,
                    "file": clf.target_id.removeprefix("file:"),
                    "match": clf.is_match,
                }
            )
    ctx.store.save_eval(
        "classifier",
        ctx.config.llm_model,
        classifier_entries,
        input_tokens=ctx.classifier.total_input_tokens,
        output_tokens=ctx.classifier.total_output_tokens,
        eval_mode=True,
    )


class Analyzer:
    def __init__(
        self,
        repo_root: Path,
        config: PipelineConfig,
        text_preprocessor: ParagraphChunker,
        code_preprocessor: CodePreprocessor,
        file_preprocessor: FilePreprocessor,
        classifier: ReasoningClassifier,
        reranker: Reranker,
        store: Store,
        on_step: Callable[[str, str], None] | None = None,
    ) -> None:
        self.repo_root, self.config, self.store, self.on_step = (
            repo_root,
            config,
            store,
            on_step,
        )
        self.text_preprocessor, self.code_preprocessor = (
            text_preprocessor,
            code_preprocessor,
        )
        self.file_preprocessor, self.reranker = file_preprocessor, reranker
        self.classifier = classifier

    async def run(
        self,
        docs_path: str | Path,
        code_path: str | Path,
        doc_files: list[Path] | None = None,
        existing_doc_map: DocMap | None = None,
        skip_cache: bool = False,
        eval_mode: bool = False,
        codebase_sha: str | None = None,
    ) -> AnalysisReport:
        docs_path = Path(docs_path)
        code_path = Path(code_path)
        if doc_files is None:
            doc_files = []
        if not docs_path.is_dir():
            raise FileNotFoundError(
                f"docs_path does not exist or is not a directory: {docs_path}"
            )
        if not code_path.is_dir():
            raise FileNotFoundError(
                f"code_path does not exist or is not a directory: {code_path}"
            )

        ctx = AnalysisContext(
            t_start=time.monotonic(),
            docs_path=docs_path,
            code_path=code_path,
            repo_root=self.repo_root,
            doc_files=doc_files,
            existing_doc_map=existing_doc_map,
            skip_cache=skip_cache,
            eval_mode=eval_mode,
            codebase_sha=codebase_sha or get_head_sha(self.repo_root),
            config=self.config,
            store=self.store,
            text_preprocessor=self.text_preprocessor,
            code_preprocessor=self.code_preprocessor,
            file_preprocessor=self.file_preprocessor,
            reranker=self.reranker,
            classifier=self.classifier,
            on_step=self.on_step,
        )

        await _preprocess(ctx)
        if not await _classify_levels(ctx):
            await _retrieve(ctx)
            await _classify(ctx)
            await _build(ctx)

        input_tokens = self.classifier.total_input_tokens
        output_tokens = self.classifier.total_output_tokens
        reranker_tokens = getattr(self.reranker, "total_tokens", 0)

        return self._finalize(
            ctx.doc_map,
            ctx.codebase_sha,
            cached=ctx.cached_sections,
            new=ctx.new_sections,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reranker_tokens=reranker_tokens,
        )

    def _finalize(
        self,
        doc_map: DocMap,
        codebase_sha: str,
        cached: int = 0,
        new: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        reranker_tokens: int = 0,
    ) -> AnalysisReport:
        dm_path = docmap_path(self.repo_root)
        self.store.persist_doc_map(doc_map, dm_path, codebase_sha=codebase_sha)

        total_sections = sum(len(m.sections) for m in doc_map.mappings)

        if input_tokens or output_tokens or reranker_tokens:
            log_stage("tokens", stats={
                "llm_input": input_tokens,
                "llm_output": output_tokens,
                "reranker": reranker_tokens,
            })

        log_stage(
            "success",
            stats={
                "docs": len(doc_map.mappings),
                "sections": total_sections,
                "cached": cached,
            },
        )

        return AnalysisReport(
            total_sections=total_sections,
            doc_files=len(doc_map.mappings),
            cached_sections=cached,
            new_sections=new,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reranker_tokens=reranker_tokens,
        )


def analyze_repo(
    repo_root: Path,
    *,
    full: bool = False,
    eval_mode: bool = False,
    on_step: Callable[[str, str], None] | None = None,
    config: PipelineConfig | None = None,
    store: Store | None = None,
    text_preprocessor: ParagraphChunker | None = None,
    code_preprocessor: CodePreprocessor | None = None,
    file_preprocessor: FilePreprocessor | None = None,
    reranker: Reranker | None = None,
    classifier: ReasoningClassifier | None = None,
) -> AnalysisReport:
    docs_list = load_docs(config_path(repo_root))
    doc_files = [repo_root / f for f in docs_list if (repo_root / f).exists()]

    config = config or PipelineConfig()
    store = store or Store(repo_root)
    existing_doc_map = None
    dm_path = docmap_path(repo_root)

    if not full and dm_path.exists():
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            existing_doc_map = DocMap.from_json(dm_path)

    existing_sha = existing_doc_map.codebase_sha if existing_doc_map else ""

    text_preprocessor = text_preprocessor or ParagraphChunker(
        config=config, max_paragraph_length=config.max_paragraph_length
    )
    code_preprocessor = code_preprocessor or CodePreprocessor()
    file_preprocessor = file_preprocessor or FilePreprocessor()
    reranker = reranker or Reranker(
        config=config, model=config.rerank_model, api_key=config.rerank_api_key
    )
    classifier = classifier or ReasoningClassifier(
        config=config,
        model=config.llm_model,
        max_retries=config.max_retries,
        timeout=config.timeout,
    )

    analyzer = Analyzer(
        repo_root=repo_root,
        config=config,
        store=store,
        on_step=on_step,
        text_preprocessor=text_preprocessor,
        code_preprocessor=code_preprocessor,
        file_preprocessor=file_preprocessor,
        reranker=reranker,
        classifier=classifier,
    )
    return asyncio.run(
        analyzer.run(
            docs_path=repo_root,
            code_path=repo_root,
            doc_files=doc_files,
            existing_doc_map=existing_doc_map,
            skip_cache=full,
            eval_mode=eval_mode,
            codebase_sha=existing_sha or None,
        )
    )
