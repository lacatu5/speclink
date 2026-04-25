import asyncio
import time
from pathlib import Path
from typing import NamedTuple

import structlog

from speclink.core.logging import log_stage
from speclink.core.models import DocMap, Section
from speclink.core.paths import docmap_path, get_head_sha
from speclink.core.store import Store
from speclink.preprocessing.markdown import get_section

from .batch import SyncResult, process_section_batch
from .diff import (
    FileChange,
    find_stale_sections,
    get_diff_context,
    get_file_changes,
)
from .rewriter import SectionRewriter

log = structlog.get_logger()


class LoadState(NamedTuple):
    doc_map: DocMap | None
    section_index: dict[tuple[str, str, int], Section]
    head_sha: str
    head_query: str


class ChangeSet(NamedTuple):
    file_changes: list[FileChange]


async def load_state(
    base_sha: str,
    head_query: str,
    repo_root: Path,
) -> LoadState:
    if head_query == "HEAD":
        sha = get_head_sha(repo_root)
        resolved_sha = sha if sha != "unknown" else head_query
    else:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                head_query,
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            resolved_sha = stdout.decode().strip()
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("git_rev_parse_failed", sha=head_query, error=str(exc))
            resolved_sha = head_query

    doc_map_file = docmap_path(repo_root)
    doc_map = DocMap.from_json(doc_map_file)

    section_index: dict[tuple[str, str, int], Section] = {}
    for dm in doc_map.mappings:
        for sec in dm.sections:
            section_index[(dm.doc_file, sec.heading, sec.chunk_index)] = sec

    return LoadState(
        doc_map=doc_map,
        section_index=section_index,
        head_sha=resolved_sha,
        head_query=head_query,
    )


async def detect_code_changes(
    base_sha: str,
    head_sha: str,
    repo_root: Path,
    t_start: float | None = None,
) -> ChangeSet:
    file_changes = get_file_changes(base_sha, head_sha, repo_root)

    elapsed = f"{time.monotonic() - t_start:.1f}s" if t_start else None
    log_stage(
        "scanning",
        elapsed=elapsed,
        stats={"updates": len(file_changes)},
    )

    return ChangeSet(
        file_changes=file_changes,
    )


def build_section_groups(
    doc_map: DocMap | None,
    file_changes: list[FileChange],
) -> dict[tuple[str, str], list[FileChange]]:
    section_groups: dict[tuple[str, str], list[FileChange]] = {}
    for change in file_changes:
        lookup_paths = [change.path]
        if change.change_type == "renamed" and change.old_path:
            lookup_paths.append(change.old_path)

        stale = find_stale_sections(doc_map, lookup_paths)
        for s in stale:
            key = (s.doc_file, s.heading)
            section_groups.setdefault(key, []).append(change)

    return section_groups


async def prepopulate_caches(
    section_groups: dict[tuple[str, str], list[FileChange]],
    repo_root: Path,
    base_sha: str,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    diff_cache: dict[str, str] = {}
    section_cache: dict[tuple[str, str], str] = {}

    seen_files: set[str] = set()
    for changes in section_groups.values():
        for change in changes:
            if change.path not in seen_files:
                diff_cache[change.path] = await get_diff_context(
                    [change.path],
                    repo_root,
                    base_sha,
                )
                seen_files.add(change.path)

    for doc_file, heading in section_groups:
        doc_path = repo_root / doc_file
        section_cache[(doc_file, heading)] = get_section(doc_path, heading)

    return diff_cache, section_cache


async def process_batches(
    section_groups: dict[tuple[str, str], list[FileChange]],
    section_index: dict[tuple[str, str, int], Section],
    diff_cache: dict[str, str],
    section_cache: dict[tuple[str, str], str],
    rewriter: SectionRewriter,
    max_context_items: int,
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    max_concurrent: int,
    doc_map: DocMap | None = None,
) -> list[SyncResult]:
    results: list[SyncResult] = []
    batch_keys = list(section_groups.keys())
    if batch_keys:
        log_stage("syncing", stats={"tasks": len(batch_keys)})
    semaphore = asyncio.Semaphore(max_concurrent)

    async def limited_batch(key):
        async with semaphore:
            return await process_section_batch(
                key,
                section_groups[key],
                base_sha,
                head_sha,
                section_index,
                diff_cache,
                section_cache,
                rewriter,
                max_context_items,
                repo_root,
                doc_map,
            )

    if batch_keys:
        batch_results = await asyncio.gather(
            *(limited_batch(key) for key in batch_keys), return_exceptions=True
        )
        for i, batch_result in enumerate(batch_results):
            if isinstance(batch_result, Exception):
                key = batch_keys[i]
                results.append(
                    SyncResult(
                        doc_file=key[0],
                        heading=key[1],
                        file_path="",
                        action="error",
                        reason=str(batch_result),
                        error=str(batch_result),
                    )
                )
            else:
                results.extend(batch_result)

    return results


async def update_and_persist(
    doc_map: DocMap | None,
    file_changes: list[FileChange],
    head_sha: str,
    repo_root: Path,
    results: list[SyncResult],
    rewriter: SectionRewriter,
    store: Store | None = None,
    t_start: float | None = None,
) -> None:
    for change in file_changes:
        if change.change_type == "renamed" and change.old_path:
            _update_memory_path(doc_map, change.old_path, change.path)

    if doc_map and store:
        store.persist_doc_map(doc_map, docmap_path(repo_root), codebase_sha=head_sha)

    rewrites = sum(1 for r in results if r.action == "rewrite")
    errors = sum(1 for r in results if r.action == "error")
    elapsed = f"{time.monotonic() - t_start:.1f}s" if t_start else None
    log_stage(
        "success",
        elapsed=elapsed,
        stats={"rewrites": rewrites, "errors": errors},
    )
    if rewriter.total_input_tokens or rewriter.total_output_tokens:
        log_stage(
            "tokens",
            stats={
                "input": rewriter.total_input_tokens,
                "output": rewriter.total_output_tokens,
            },
        )


def _update_memory_path(
    doc_map: DocMap | None,
    old_path: str,
    new_path: str,
) -> None:
    if not doc_map:
        return
    for doc_mapping in doc_map.mappings:
        for section in doc_mapping.sections:
            for i, fm in enumerate(section.files):
                if fm == old_path:
                    section.files[i] = new_path
