import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from speclink.core.config import PipelineConfig
from speclink.core.logging import log_stage
from speclink.core.models import DocMap
from speclink.core.paths import docmap_path
from speclink.core.store import Store

from .batch import SyncResult
from .diff import FileChange
from .rewriter import SectionRewriter
from .stages import (
    ChangeSet,
    LoadState,
    build_section_groups,
    detect_code_changes,
    load_state,
    prepopulate_caches,
    process_batches,
    update_and_persist,
)


class SyncReport(NamedTuple):
    actions: list[SyncResult]
    total_errors: int


@dataclass
class SyncContext:
    repo_root: Path
    config: PipelineConfig
    store: Store
    rewriter: SectionRewriter
    base_sha: str
    on_step: Callable[[str, str], None] | None = None

    t_start: float = 0.0
    state: LoadState | None = None
    change: ChangeSet | None = None
    section_groups: dict[tuple[str, str], list[FileChange]] = field(
        default_factory=dict
    )
    diff_cache: dict[str, str] = field(default_factory=dict)
    section_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    results: list[SyncResult] = field(default_factory=list)


async def _load(ctx: SyncContext) -> None:
    ctx.state = await load_state(ctx.base_sha, "HEAD", ctx.repo_root)


async def _detect_changes(ctx: SyncContext) -> None:
    ctx.change = await detect_code_changes(
        ctx.base_sha,
        ctx.state.head_query,
        ctx.repo_root,
        t_start=ctx.t_start,
    )
    ctx.section_groups = build_section_groups(
        ctx.state.doc_map,
        ctx.change.file_changes,
    )


async def _prepopulate(ctx: SyncContext) -> None:
    ctx.diff_cache, ctx.section_cache = await prepopulate_caches(
        ctx.section_groups,
        ctx.repo_root,
        ctx.base_sha,
    )


async def _process(ctx: SyncContext) -> None:
    ctx.results = await process_batches(
        ctx.section_groups,
        ctx.state.section_index,
        ctx.diff_cache,
        ctx.section_cache,
        ctx.rewriter,
        ctx.config.max_context_items,
        ctx.repo_root,
        ctx.base_sha,
        ctx.state.head_sha,
        ctx.config.max_concurrent,
        doc_map=ctx.state.doc_map,
    )


async def _update(ctx: SyncContext) -> None:
    await update_and_persist(
        ctx.state.doc_map,
        ctx.change.file_changes,
        ctx.state.head_sha,
        ctx.repo_root,
        ctx.results,
        ctx.rewriter,
        ctx.store,
        t_start=ctx.t_start,
    )


class Synchronizer:
    def __init__(
        self,
        repo_root: Path,
        config: PipelineConfig,
        store: Store,
        rewriter: SectionRewriter,
        on_step: Callable[[str, str], None] | None = None,
    ) -> None:
        self.repo_root, self.config, self.store = repo_root, config, store
        self.on_step, self.rewriter = on_step, rewriter

    async def sync(self, base_sha: str) -> SyncReport:
        ctx = SyncContext(
            t_start=time.monotonic(),
            repo_root=self.repo_root,
            config=self.config,
            store=self.store,
            rewriter=self.rewriter,
            base_sha=base_sha,
            on_step=self.on_step,
        )

        await _load(ctx)
        await _detect_changes(ctx)
        await _prepopulate(ctx)
        await _process(ctx)
        await _update(ctx)

        return self._finalize(ctx)

    def _finalize(self, ctx: SyncContext) -> SyncReport:
        errors = sum(1 for r in ctx.results if r.action == "error")
        log_stage(
            "sync_complete",
            elapsed=f"{time.monotonic() - ctx.t_start:.1f}s",
            stats={"tasks": len(ctx.results), "errors": errors},
        )
        return SyncReport(actions=ctx.results, total_errors=errors)


def sync_repo(
    repo_root: Path,
    config: PipelineConfig | None = None,
    *,
    base_sha: str | None = None,
    on_step: Callable | None = None,
    store: Store | None = None,
    rewriter: SectionRewriter | None = None,
) -> SyncReport:
    doc_map_file = docmap_path(repo_root)
    doc_map = DocMap.from_json(doc_map_file)
    config = config or PipelineConfig()
    base = base_sha or doc_map.codebase_sha or "HEAD"

    store = store or Store(repo_root)
    rewriter = rewriter or SectionRewriter(config=config, model=config.llm_model)

    syncer = Synchronizer(
        repo_root=repo_root,
        config=config,
        store=store,
        rewriter=rewriter,
        on_step=on_step,
    )
    return asyncio.run(syncer.sync(base))
