from __future__ import annotations

from pathlib import Path

from speclink.core.config import PipelineConfig
from speclink.preprocessing.markdown import ParagraphChunker, get_section, parse_markdown, replace_section


class TestMarkdownPipeline:
    def test_parse_markdown_extracts_sections(self, tmp_path: Path):
        md_file = tmp_path / "doc.md"
        md_file.write_text(
            "# Title\n\nIntro text.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n"
        )
        sections = parse_markdown(str(md_file))
        headings = [s.heading for s in sections]
        assert "Title" in headings
        assert "Section A" in headings
        assert "Section B" in headings
        assert any("Content A" in s.content for s in sections)

    def test_get_and_replace_section(self, tmp_path: Path):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Title\n\nOriginal content.\n\n## Other\n\nKeep.\n")
        body = get_section(md_file, "Title")
        assert "Original content" in body
        replace_section(md_file, "Title", "New content.")
        updated = md_file.read_text()
        assert "New content" in updated
        assert "Keep" in updated

    def test_chunker_process_markdown(self, tmp_path: Path, mock_config: PipelineConfig):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Title\n\nParagraph one.\n\n## Details\n\nParagraph two.\n")
        chunker = ParagraphChunker(config=mock_config)
        sections = chunker.process_markdown(md_file)
        assert len(sections) >= 2
        assert all(s.chunk_index is not None for s in sections)
        assert all(s.hash for s in sections)

    def test_chunker_splits_oversized_content(self, tmp_path: Path, mock_config: PipelineConfig):
        md_file = tmp_path / "doc.md"
        sentences = [f"This is sentence number {i}." for i in range(200)]
        long_para = " ".join(sentences)
        md_file.write_text(f"# Big Section\n\n{long_para}\n")
        chunker = ParagraphChunker(config=mock_config, max_tokens=50)
        sections = chunker.process_markdown(md_file)
        assert len(sections) > 1
