from __future__ import annotations

from pathlib import Path


from speclink.preprocessing.markdown import (
    ParagraphChunker,
    get_section,
    is_code_label,
    parse_headings,
    parse_markdown,
)


class TestParseHeadings:
    def test_extracts_heading_level_and_text(self):
        text = "# Title\n## Subtitle\n### Deep"
        headings = parse_headings(text)
        assert len(headings) == 3
        assert headings[0][0] == 1 and headings[0][1] == "Title"
        assert headings[1][0] == 2 and headings[1][1] == "Subtitle"
        assert headings[2][0] == 3 and headings[2][1] == "Deep"


class TestIsCodeLabel:
    def test_backtick_wrapped_returns_true(self):
        assert is_code_label("`my_function()`") is True

    def test_normal_heading_returns_false(self):
        assert is_code_label("API Overview") is False

    def test_double_backticks_returns_false(self):
        assert is_code_label("``not this``") is False

    def test_no_backticks_returns_false(self):
        assert is_code_label("plain text") is False


class TestParseMarkdown:
    def test_parses_real_markdown_file(self, tmp_path: Path):
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nSome content.\n\n## Section\n\nMore content.\n")
        sections = parse_markdown(str(md))
        assert len(sections) == 2
        assert sections[0].heading == "Title"
        assert sections[0].file_path == str(md)
        assert "Some content" in sections[0].content
        assert sections[1].heading == "Section"
        assert "More content" in sections[1].content


class TestGetSection:
    def test_returns_content_under_heading(self, tmp_path: Path):
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nSome content.\n\n## Section\n\nMore content.\n")
        result = get_section(md, "Section")
        assert "More content" in result

    def test_returns_empty_for_missing_heading(self, tmp_path: Path):
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nContent.\n")
        result = get_section(md, "Nonexistent")
        assert result == ""


class TestParagraphChunker:
    def test_split_into_paragraphs(self, mock_config):
        chunker = ParagraphChunker(mock_config)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 3
        assert result[0] == "First paragraph."
        assert result[2] == "Third paragraph."

    def test_estimate_tokens_returns_int(self, mock_config):
        chunker = ParagraphChunker(mock_config)
        tokens = chunker.estimate_tokens("Hello world")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_split_oversized_returns_single_when_within_limit(self, mock_config):
        chunker = ParagraphChunker(mock_config, max_tokens=1000)
        result = chunker.split_oversized_paragraph("Short text. Nothing big.")
        assert result == ["Short text. Nothing big."]

    def test_chunk_paragraphs_merges_small_paragraphs(self, mock_config):
        chunker = ParagraphChunker(mock_config, max_tokens=10000, max_paragraph_length=1000)
        paras = ["Short one.", "Also short.", "Me too."]
        result = chunker.chunk_paragraphs(paras)
        assert len(result) >= 1
        assert "Short one." in result[0]
