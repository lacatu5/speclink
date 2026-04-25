from __future__ import annotations

from unittest.mock import patch

import pytest

from typer import Exit

from speclink.wizard import list_markdown_files, generate_workflow


def test_list_markdown_files_finds_md(tmp_path):
    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("# B")
    files = list_markdown_files(tmp_path)
    names = [f.name for f in files]
    assert "a.md" in names
    assert "b.md" in names


def test_list_markdown_files_respects_gitignore(tmp_path):
    (tmp_path / "keep.md").write_text("# keep")
    (tmp_path / "ignore.md").write_text("# ignore")
    (tmp_path / ".gitignore").write_text("ignore.md\n")
    files = list_markdown_files(tmp_path)
    names = [f.name for f in files]
    assert "keep.md" in names
    assert "ignore.md" not in names


def test_list_markdown_files_empty_dir(tmp_path):
    assert list_markdown_files(tmp_path) == []


def test_generate_workflow_creates_file(tmp_path):
    out = tmp_path / ".github" / "workflows" / "speclink-sync.yml"
    with patch("speclink.wizard.load_template_raw", return_value="workflow yaml content"):
        generate_workflow(out)
    assert out.exists()
    assert out.read_text() == "workflow yaml content"


def test_list_markdown_files_ignores_comments_in_gitignore(tmp_path):
    (tmp_path / "keep.md").write_text("# keep")
    (tmp_path / "commented.md").write_text("# commented")
    (tmp_path / ".gitignore").write_text("# this is a comment\n\n")
    files = list_markdown_files(tmp_path)
    names = [f.name for f in files]
    assert "keep.md" in names
    assert "commented.md" in names


def test_list_markdown_files_gitignore_read_error(tmp_path):
    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "b.md").write_text("# B")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.md\n")
    with patch("speclink.wizard.Path.read_text", side_effect=OSError("nope")):
        files = list_markdown_files(tmp_path)
    assert len(files) == 2


def test_init_wizard_no_markdown_files(tmp_path):
    from speclink.wizard import init_wizard

    with patch("speclink.wizard.list_markdown_files", return_value=[]):
        with pytest.raises(Exit):
            init_wizard(tmp_path)


def test_init_wizard_no_selection_exits(tmp_path):
    from speclink.wizard import init_wizard

    (tmp_path / "a.md").write_text("# A")
    with patch("speclink.wizard.select_multiple", return_value=[]):
        with pytest.raises(Exit):
            init_wizard(tmp_path)


def test_init_wizard_selects_files(tmp_path):
    from speclink.wizard import init_wizard

    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "b.md").write_text("# B")
    with (
        patch("speclink.wizard.select_multiple", return_value=["a.md"]),
        patch("speclink.wizard.save_docs") as mock_save,
        patch("speclink.wizard.generate_workflow"),
        patch("speclink.wizard.speclink_root", return_value=tmp_path / ".speclink"),
        patch("speclink.wizard.config_path", return_value=tmp_path / ".speclink" / "config.yaml"),
        patch("speclink.wizard.load_docs", return_value=[]),
    ):
        init_wizard(tmp_path)
        mock_save.assert_called_once()
