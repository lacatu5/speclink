import hashlib
import re
from pathlib import Path
from typing import NamedTuple

import tiktoken
from markdown_it import MarkdownIt

from speclink.core.config import PipelineConfig
from speclink.core.models import Section
from speclink.core.paths import atomic_write

_SEPARATOR_LEN = len("\n\n")


class MarkdownSection(NamedTuple):
    heading: str
    content: str
    file_path: str


markdown_parser = MarkdownIt()


def parse_headings(text: str) -> list[tuple[int, str, int, int]]:
    tokens = markdown_parser.parse(text)
    headings: list[tuple[int, str, int, int]] = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1])
            ls = token.map[0] if token.map else 0
            le = token.map[1] if token.map else ls + 1
            heading_text = tokens[i + 1].content.strip()
            headings.append((level, heading_text, ls, le))
    return headings


_CODE_LABEL_RE = re.compile(r"^`[^`]+`$")


def is_code_label(heading_text: str) -> bool:
    return bool(_CODE_LABEL_RE.match(heading_text.strip()))


def parse_markdown(file_path: str) -> list[MarkdownSection]:
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    headings = _filtered_headings(text)

    sections: list[MarkdownSection] = []

    for idx, (_, heading_text, _, content_start) in enumerate(headings):
        content_end = headings[idx + 1][2] if idx + 1 < len(headings) else len(lines)
        content = "\n".join(lines[content_start:content_end]).strip()
        sections.append(
            MarkdownSection(
                heading=heading_text,
                content=content,
                file_path=file_path,
            ),
        )

    return sections


def find_heading_index(
    headings: list[tuple[int, str, int, int]], heading: str
) -> int | None:
    for i, (_, txt, _, _) in enumerate(headings):
        if txt == heading:
            return i
    return None


def _filtered_headings(text: str) -> list[tuple[int, str, int, int]]:
    return [h for h in parse_headings(text) if not is_code_label(h[1])]


def get_section(file_path: Path, heading: str) -> str:
    text = file_path.read_text()
    headings = _filtered_headings(text)

    target_idx = find_heading_index(headings, heading)
    if target_idx is None:
        return ""

    heading_end = headings[target_idx][3]

    section_end = len(text.splitlines())
    if target_idx + 1 < len(headings):
        section_end = headings[target_idx + 1][2]

    lines = text.splitlines(keepends=True)
    return "".join(lines[heading_end:section_end]).strip()


def replace_section(file_path: Path, heading: str, new_body: str) -> None:
    text = file_path.read_text()
    lines = text.splitlines(keepends=True)
    headings = _filtered_headings(text)

    target_idx = find_heading_index(headings, heading)
    if target_idx is None:
        return

    heading_start = headings[target_idx][2]
    heading_end = headings[target_idx][3]

    next_start = len(lines)
    if target_idx + 1 < len(headings):
        next_start = headings[target_idx + 1][2]

    heading_line = "".join(lines[heading_start:heading_end])
    new_text = (
        "".join(lines[:heading_start])
        + heading_line
        + "\n"
        + new_body
        + "\n\n"
        + "".join(lines[next_start:])
    )

    if new_text != text:
        atomic_write(file_path, new_text)


class ParagraphChunker:
    def __init__(
        self,
        config: PipelineConfig,
        max_paragraph_length: int | None = None,
        max_tokens: int | None = None,
        encoding_name: str = "cl100k_base",
    ) -> None:
        self.max_paragraph_length = max_paragraph_length or config.max_paragraph_length
        self.max_tokens = max_tokens or config.max_paragraph_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

    def estimate_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def split_into_paragraphs(self, text: str) -> list[str]:
        paragraphs = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in paragraphs if p.strip()]

    def split_oversized_paragraph(self, text: str) -> list[str]:
        if self.estimate_tokens(text) <= self.max_tokens:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current: list[str] = []
        current_tokens = 0
        for sent in sentences:
            sent_tokens = self.estimate_tokens(sent)
            if current_tokens + sent_tokens > self.max_tokens and current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            current.append(sent)
            current_tokens += sent_tokens
        chunks.append(" ".join(current))

        return chunks

    def chunk_paragraphs(self, paragraphs: list[str]) -> list[str]:
        final_chunks = []
        for para in paragraphs:
            if self.estimate_tokens(para) > self.max_tokens:
                final_chunks.extend(self.split_oversized_paragraph(para))
            else:
                final_chunks.append(para)

        merged_chunks = []
        current_chunk = []
        current_length = 0
        for chunk in final_chunks:
            chunk_len = len(chunk)
            if current_length + chunk_len > self.max_paragraph_length and current_chunk:
                merged_chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(chunk)
            current_length += chunk_len + _SEPARATOR_LEN
        if current_chunk:
            merged_chunks.append("\n\n".join(current_chunk))
        return merged_chunks

    def process_markdown(self, file_path: str | Path) -> list[Section]:
        sections = parse_markdown(str(file_path))
        chunks: list[Section] = []
        heading_counts: dict[str, int] = {}

        for section in sections:
            section_hash = hashlib.sha256(f"{section.heading}\n{section.content}".encode("utf-8")).hexdigest()
            paragraphs = self.split_into_paragraphs(section.content)
            if not paragraphs:
                if section.heading:
                    paragraphs = [section.heading]
                else:
                    continue
            paragraph_chunks = self.chunk_paragraphs(paragraphs)

            heading_occurrence = heading_counts.get(section.heading, 0)
            for index, chunk in enumerate(paragraph_chunks):
                chunk_index = heading_occurrence + index
                chunks.append(
                    Section(
                        heading=section.heading,
                        content=chunk,
                        hash=section_hash,
                        file_path=section.file_path,
                        chunk_index=chunk_index,
                    ),
                )
            heading_counts[section.heading] = heading_occurrence + len(paragraph_chunks)

        return chunks
