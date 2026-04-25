import asyncio
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from speclink.core.config import PipelineConfig
from speclink.core.logging import log_error, log_warn
from speclink.core.models import (
    Classification,
    CodeElement,
    DocMap,
    Document,

    Section,
)
from speclink.preprocessing.code import CodePreprocessor, FilePreprocessor
from speclink.preprocessing.markdown import ParagraphChunker

from .classifier import ReasoningClassifier
from .reranker import Reranker


class PreprocessResult(NamedTuple):
    sections: list[Section]
    symbols: list[CodeElement]
    file_elements: list[CodeElement]


class PreprocessStats(NamedTuple):
    docs: int
    sections: int
    code_files: int
    symbols: int


class CandidateResult(NamedTuple):
    key: tuple[str, str, int]
    candidates: list[CodeElement]
    rerank_scores: dict[str, float]


class RetrieveResult(NamedTuple):
    heading_to_files: dict[tuple[str, str, int], list[str]]
    heading_to_rerank_scores: dict[tuple[str, str, int], dict[str, float]]
    heading_to_classifications: dict[tuple[str, str, int], list[Classification]]


async def preprocess(
    docs_path: str | Path,
    code_path: str | Path,
    text_preprocessor: ParagraphChunker,
    code_preprocessor: CodePreprocessor,
    file_preprocessor: FilePreprocessor,
    doc_files: list[Path],
) -> tuple[PreprocessResult, PreprocessStats]:
    sections = []
    for f in doc_files:
        chunks = text_preprocessor.process_markdown(f)
        rel = str(f.relative_to(docs_path))
        for chunk in chunks:
            chunk.file_path = rel
        sections.extend(chunks)

    loop = asyncio.get_running_loop()
    symbols, file_elements = await asyncio.gather(
        loop.run_in_executor(None, code_preprocessor.process_codebase, code_path),
        loop.run_in_executor(None, file_preprocessor.process_codebase, code_path),
    )

    stats = PreprocessStats(
        docs=len({s.file_path for s in sections if s.file_path}),
        sections=len(sections),
        code_files=len({f.file_path for f in file_elements}),
        symbols=len(symbols),
    )
    return PreprocessResult(
        sections=sections,
        symbols=symbols,
        file_elements=file_elements,
    ), stats


def _top_files_by_rerank(
    rerank_scores: dict[str, float],
    file_ids: list[str],
    heading: str,
    config: PipelineConfig,
) -> list[str]:
    if not rerank_scores:
        log_warn("reranker_empty", stats={"heading": heading, "fallback": "all_files"})
        return file_ids
    absolute_floor = config.rerank_floor
    gap_threshold = config.rerank_gap
    scored_candidates = [
        (fid, rerank_scores.get(fid, 0))
        for fid in file_ids
        if rerank_scores.get(fid, 0) >= absolute_floor
    ]
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    top_file_ids = []
    for i in range(len(scored_candidates)):
        fid, score = scored_candidates[i]
        top_file_ids.append(fid)
        if i + 1 < len(scored_candidates):
            next_score = scored_candidates[i + 1][1]
            if score - next_score > gap_threshold:
                break
    return top_file_ids


async def retrieve(
    heading_to_sections: dict[tuple[str, str, int], list[Section]],
    file_elements: list[CodeElement],
    file_ids: list[str],
    reranker: Reranker | None,
    config: PipelineConfig,
    sig_map: dict[str, list[str]] | None = None,
    variables_map: dict[str, list[str]] | None = None,
) -> tuple[list[CandidateResult], int, int]:
    max_concurrent = config.max_concurrent
    semaphore = asyncio.Semaphore(max_concurrent)

    async def retrieve_one(
        file_path: str, heading: str, chunk_index: int, section_group: list[Section]
    ) -> CandidateResult:
        query_section = section_group[0]
        rerank_scores: dict[str, float] = {}
        if reranker and file_ids:
            rerank_scores = await reranker.rerank(
                section=query_section,
                candidate_files=file_ids,
                sig_map=sig_map,
                variables_map=variables_map,
            )

        top_file_ids = _top_files_by_rerank(rerank_scores, file_ids, heading, config)
        top_file_elements = [
            f for f in file_elements if f.file_path in set(top_file_ids)
        ]
        return CandidateResult(
            key=(file_path, heading, chunk_index),
            candidates=top_file_elements,
            rerank_scores=rerank_scores,
        )

    async def limited_retrieve(
        file_path: str, heading: str, chunk_index: int, section_group: list[Section]
    ) -> CandidateResult:
        async with semaphore:
            return await retrieve_one(file_path, heading, chunk_index, section_group)

    results = await asyncio.gather(
        *(
            limited_retrieve(fp, h, ci, sg)
            for (fp, h, ci), sg in heading_to_sections.items()
        ),
        return_exceptions=True,
    )
    candidate_results: list[CandidateResult] = []
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
            log_error("retrieve_failed", stats={"error": str(r)})
        else:
            candidate_results.append(r)
    total_candidates = sum(len(c.candidates) for c in candidate_results)
    if errors:
        log_warn("retrieve", stats={"errors": errors})
    return candidate_results, len(heading_to_sections), total_candidates


def _build_sig_map(symbols: list[CodeElement] | None) -> dict[str, list[str]]:
    if not symbols:
        return {}
    by_file: dict[str, list[str]] = defaultdict(list)
    for sym in symbols:
        if not sym.signature:
            continue
        if not sym.code:
            by_file[sym.file_path].append(sym.signature)
            continue
        code = sym.code.strip()
        body = code[len(sym.signature):].strip() if code.startswith(sym.signature) else ""
        lines = [line for line in body.splitlines() if line.strip()][:2]
        entry = sym.signature
        if lines:
            entry += "\n" + "\n".join(lines)
        by_file[sym.file_path].append(entry)
    return dict(by_file)


def _collect_classify_results(
    results: list[
        tuple[tuple[str, str, int], list[str], list[Classification]] | Exception
    ],
    candidate_results: list[CandidateResult],
) -> tuple[
    int,
    dict[tuple[str, str, int], list[str]],
    dict[tuple[str, str, int], dict[str, float]],
    dict[tuple[str, str, int], list[Classification]],
]:
    heading_to_files: dict[tuple[str, str, int], list[str]] = {}
    heading_to_classifications: dict[tuple[str, str, int], list[Classification]] = {}
    heading_to_rerank_scores: dict[tuple[str, str, int], dict[str, float]] = {}
    errors = 0
    total_matched = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
            log_error("classify_failed", stats={"error": str(r)})
            continue
        key, matched_files, classified = r
        heading_to_files[key] = matched_files
        heading_to_classifications[key] = classified
        total_matched += len(matched_files)
    for cr in candidate_results:
        heading_to_rerank_scores[cr.key] = cr.rerank_scores
        if cr.key not in heading_to_files:
            heading_to_files[cr.key] = []
            heading_to_classifications[cr.key] = []
    if errors:
        log_warn("classify", stats={"errors": errors})
    return (
        total_matched,
        heading_to_files,
        heading_to_rerank_scores,
        heading_to_classifications,
    )


async def classify(
    candidate_results: list[CandidateResult],
    heading_to_sections: dict[tuple[str, str, int], list[Section]],
    classifier: ReasoningClassifier,
    config: PipelineConfig,
    symbols: list[CodeElement] | None = None,
    variables_map: dict[str, list[str]] | None = None,
) -> tuple[RetrieveResult, int, int]:
    max_concurrent = config.max_concurrent
    sig_map = _build_sig_map(symbols)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def classify_one(
        cr: CandidateResult,
    ) -> tuple[tuple[str, str, int], list[str], list[Classification]]:
        file_path = cr.key[0]
        section_group = heading_to_sections[cr.key]
        query_section = section_group[0]
        doc_filename = Path(file_path).name
        classified = await classifier.classify_candidates(
            query_section, cr.candidates, doc_filename, sig_map=sig_map,
            variables_map=variables_map,
        )
        matched_files = [
            res.target_id.removeprefix("file:") for res in classified if res.is_match
        ]
        return cr.key, matched_files, classified

    async def limited_classify(
        cr: CandidateResult,
    ) -> tuple[tuple[str, str, int], list[str], list[Classification]]:
        async with semaphore:
            return await classify_one(cr)

    results = await asyncio.gather(
        *(limited_classify(cr) for cr in candidate_results if cr.candidates),
        return_exceptions=True,
    )
    (
        total_matched,
        heading_to_files,
        heading_to_rerank_scores,
        heading_to_classifications,
    ) = _collect_classify_results(results, candidate_results)
    retrieval = RetrieveResult(
        heading_to_files=heading_to_files,
        heading_to_rerank_scores=heading_to_rerank_scores,
        heading_to_classifications=heading_to_classifications,
    )
    return retrieval, len(candidate_results), total_matched


def build_doc_map(
    heading_to_files: dict[tuple[str, str, int], list[str]],
    all_sections: list[Section],
    heading_to_classifications: dict[tuple[str, str, int], list[Classification]],
) -> DocMap:
    doc_sections: dict[str, list[Section]] = defaultdict(list)

    for section in all_sections:
        key = (section.file_path, section.heading, section.chunk_index)
        files = heading_to_files.get(key, [])

        section.files = []
        for f_path in files:
            section.files.append(f_path)
        doc_sections[section.file_path].append(section)

    doc_mappings = []
    for doc_file, sections in doc_sections.items():
        sections.sort(key=lambda x: (x.heading, x.chunk_index))
        doc_mappings.append(Document(doc_file=doc_file, sections=sections))

    return DocMap(mappings=doc_mappings)


def group_by_heading(
    sections: list[Section],
) -> dict[tuple[str, str, int], list[Section]]:
    heading_to_sections: dict[tuple[str, str, int], list[Section]] = defaultdict(list)
    for section in sections:
        heading_to_sections[
            section.file_path, section.heading, section.chunk_index
        ].append(section)
    return heading_to_sections
