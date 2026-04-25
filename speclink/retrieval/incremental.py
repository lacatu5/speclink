from typing import NamedTuple

from speclink.core.models import Classification, DocMap, Section

from .stages import PreprocessResult, RetrieveResult, build_doc_map


class ChangeDetection(NamedTuple):
    changed_sections: list[Section]
    unchanged_sections: list[Section]
    cached_index: dict[tuple[str, str, int], Section]


def detect_changes(
    pre: PreprocessResult,
    existing_doc_map: DocMap | None,
    skip_cache: bool = False,
) -> ChangeDetection:
    cached_index: dict[tuple[str, str, int], Section] = {}
    if existing_doc_map and not skip_cache:
        for dm in existing_doc_map.mappings:
            for sec in dm.sections:
                cached_index[(dm.doc_file, sec.heading, sec.chunk_index)] = sec

    unchanged_sections: list[Section] = []
    changed_sections: list[Section] = []
    for section in pre.sections:
        key = (section.file_path, section.heading, section.chunk_index)
        cached = cached_index.get(key)
        if cached and cached.hash == section.hash:
            unchanged_sections.append(section)
            continue
        changed_sections.append(section)

    return ChangeDetection(
        changed_sections=changed_sections,
        unchanged_sections=unchanged_sections,
        cached_index=cached_index,
    )


def resolve_from_cache(
    change: ChangeDetection,
) -> tuple[DocMap, int, int]:
    all_sections = change.changed_sections + change.unchanged_sections
    cached_files: dict[tuple[str, str, int], list[str]] = {}
    cached_classifications: dict[tuple[str, str, int], list[Classification]] = {}
    for section in all_sections:
        key = (section.file_path, section.heading, section.chunk_index)
        cached = change.cached_index.get(key)
        if cached:
            cached_files[key] = list(cached.files)
            cached_classifications[key] = [
                Classification(
                    target_id=f"file:{fm}",
                    is_match=True,
                )
                for fm in cached.files
            ]
    doc_map = build_doc_map(cached_files, all_sections, cached_classifications)
    return doc_map, len(change.unchanged_sections), len(change.changed_sections)


def merge_unchanged(
    retrieval: RetrieveResult,
    change: ChangeDetection,
) -> None:
    for section in change.unchanged_sections:
        key = (section.file_path, section.heading, section.chunk_index)
        cached = change.cached_index[key]
        retrieval.heading_to_files[key] = list(cached.files)
        retrieval.heading_to_rerank_scores[key] = {}
        retrieval.heading_to_classifications[key] = [
            Classification(
                target_id=f"file:{fm}",
                is_match=True,
            )
            for fm in cached.files
        ]
