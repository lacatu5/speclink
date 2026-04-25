import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from speclink._prompts import load_prompt
from speclink.core.models import CodeElement, DocMap, Section
from speclink.preprocessing.code import collect_signatures_and_bodies
from speclink.preprocessing.code_extraction import EXTRACTORS, LANG_MAP
from speclink.preprocessing.markdown import get_section, replace_section

from .diff import FileChange, get_renamed_diff
from .rewriter import SectionRewriter

_BATCH_PROMPTS = load_prompt("batch")
_DELETED_INSTRUCTION = _BATCH_PROMPTS["deleted_instruction"]
_RENAMED_INSTRUCTION = _BATCH_PROMPTS["renamed_instruction"]


@dataclass
class SyncResult:
    doc_file: str
    heading: str
    file_path: str
    action: Literal["rewrite", "no_change", "error"]
    reason: str
    error: str | None = None


def extract_current_symbols(file_path: Path, repo_root: Path) -> list[CodeElement]:
    lang = LANG_MAP.get(file_path.suffix.lower())
    extractor = EXTRACTORS.get(lang) if lang else None
    if not extractor:
        return []
    source = file_path.read_bytes()
    extraction = extractor(source, file_path, repo_root)
    rel = str(file_path.relative_to(repo_root))
    return [
        CodeElement(
            id=s["id"],
            name=s["name"],
            signature=s.get("signature", ""),
            code=s.get("code", ""),
            file_path=rel,
        )
        for s in extraction.get("symbols", [])
    ]


def find_section_mapping(
    section_index: dict[tuple[str, str, int], Section],
    doc_file: str,
    heading: str,
) -> Section | None:
    return next(
        (
            sec
            for (df, sh, _), sec in section_index.items()
            if df == doc_file and sh == heading
        ),
        None,
    )


def update_section_hash(
    section_index: dict[tuple[str, str, int], Section],
    doc_file: str,
    heading: str,
    repo_root: Path,
) -> None:
    mapping = find_section_mapping(section_index, doc_file, heading)
    if mapping:
        doc_path = repo_root / doc_file
        body = get_section(doc_path, heading)
        mapping.hash = hashlib.sha256(f"{heading}\n{body}".encode("utf-8")).hexdigest()


def remove_file_from_doc_map(
    doc_map: DocMap | None,
    doc_file: str,
    heading: str,
    file_path: str,
) -> None:
    if not doc_map:
        return
    for doc_mapping in doc_map.mappings:
        if doc_mapping.doc_file != doc_file:
            continue
        for section in doc_mapping.sections:
            if section.heading != heading:
                continue
            section.files = [fm for fm in section.files if fm != file_path]
            break
        break


async def collect_batch_diffs(
    other_changes: list[FileChange],
    base_sha: str,
    head_sha: str,
    repo_root: Path,
    diff_cache: dict[str, str],
) -> str:
    diffs = []
    for change in other_changes:
        if change.change_type == "renamed" and change.old_path:
            diff = await get_renamed_diff(
                change.old_path,
                change.path,
                base_sha,
                head_sha,
                repo_root,
                diff_cache,
            )
        else:
            diff = diff_cache.get(change.path, "")
        if diff:
            diffs.append(f"[File: {change.path}]\n{diff}")
    return "\n\n".join(diffs) if diffs else ""


def build_explicit_instructions(changes: list[FileChange]) -> str | None:
    explicit_parts = []
    for change in changes:
        match change.change_type:
            case "deleted":
                explicit_parts.append(_DELETED_INSTRUCTION.format(path=change.path))
            case "renamed" if change.old_path:
                explicit_parts.append(
                    _RENAMED_INSTRUCTION.format(
                        old_path=change.old_path,
                        new_path=change.path,
                    )
                )
    return "\n\n".join(explicit_parts) if explicit_parts else None


def collect_batch_code_context(
    other_changes: list[FileChange],
    max_context_items: int,
    repo_root: Path,
) -> str | None:
    code_parts = []
    for change in other_changes:
        fp = repo_root / change.path
        if not fp.exists():
            continue
        symbols = extract_current_symbols(fp, repo_root)
        if not symbols:
            continue
        sig_entries = collect_signatures_and_bodies(symbols)
        if not sig_entries:
            continue
        lines = [f"[File: {change.path}]"]
        for sym in sig_entries[:max_context_items]:
            lines.append(f"- {sym.get('signature', sym['name'])}")
        code_parts.append("\n".join(lines))
    return "\n\n".join(code_parts) if code_parts else None


async def process_section_batch(
    section_key: tuple[str, str],
    changes: list[FileChange],
    base_sha: str,
    head_sha: str,
    section_index: dict[tuple[str, str, int], Section],
    diff_cache: dict[str, str],
    section_cache: dict[tuple[str, str], str],
    rewriter: SectionRewriter,
    max_context_items: int,
    repo_root: Path,
    doc_map: DocMap | None = None,
) -> list[SyncResult]:
    doc_file, heading = section_key
    section_body = section_cache.get((doc_file, heading), "")
    deleted_paths = {c.path for c in changes if c.change_type == "deleted"}

    combined_diff = await collect_batch_diffs(
        changes,
        base_sha,
        head_sha,
        repo_root,
        diff_cache,
    )
    explicit_changes = build_explicit_instructions(changes)
    code_context = collect_batch_code_context(changes, max_context_items, repo_root)

    new_content = await rewriter.rewrite_section(
        heading,
        section_body,
        diff_context=combined_diff,
        code_context=code_context,
        explicit_changes=explicit_changes,
    )

    if new_content.strip() != section_body.strip():
        doc_path = repo_root / doc_file
        replace_section(doc_path, heading, new_content)
        update_section_hash(section_index, doc_file, heading, repo_root)
        action = "rewrite"
    else:
        action = "no_change"

    for path in deleted_paths:
        remove_file_from_doc_map(doc_map, doc_file, heading, path)

    results: list[SyncResult] = []
    for change in changes:
        reason = "No changes needed"
        if action == "rewrite":
            match change.change_type:
                case "deleted":
                    reason = "File deleted — removed references from section"
                case "renamed":
                    reason = "File renamed — section reviewed/rewritten"
                case _:
                    reason = "Code changes — section rewritten"
        results.append(
            SyncResult(
                doc_file=doc_file,
                heading=heading,
                file_path=change.path,
                action=action,
                reason=reason,
            )
        )
    return results
