from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from speclink.rewrite.diff import (
    FileChange,
    get_diff_context,
    get_file_changes,
    get_renamed_diff,
)


def test_get_file_changes_parses_git_diff():
    mock_result = MagicMock()
    mock_result.stdout = "M\tsrc/api.py\nD\tsrc/old.py\nR100\tsrc/old.py\tsrc/new.py\n"
    with patch("speclink.rewrite.diff.subprocess.run", return_value=mock_result):
        changes = get_file_changes("abc", "HEAD", Path("/repo"))
    assert len(changes) == 3
    assert changes[0] == FileChange("src/api.py", "modified")
    assert changes[1] == FileChange("src/old.py", "deleted")
    assert changes[2] == FileChange("src/new.py", "renamed", "src/old.py")


def test_get_file_changes_returns_empty_on_error():
    with patch(
        "speclink.rewrite.diff.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "git"),
    ):
        changes = get_file_changes("abc", "def", Path("/repo"))
    assert changes == []


@pytest.mark.asyncio
async def test_get_diff_context_returns_empty_for_no_files():
    result = await get_diff_context([], Path("/repo"))
    assert result == ""


@pytest.mark.asyncio
async def test_get_diff_context_with_base_sha(git_repo):
    (git_repo / "src.py").write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=git_repo, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True).stdout.strip()
    (git_repo / "src.py").write_text("x = 2")
    result = await get_diff_context(["src.py"], git_repo, base_sha=sha)
    assert "src.py" in result


def test_get_file_changes_skips_malformed_lines():
    mock_result = MagicMock()
    mock_result.stdout = "M\n\nonlyone\n"
    with patch("speclink.rewrite.diff.subprocess.run", return_value=mock_result):
        changes = get_file_changes("abc", "HEAD", Path("/repo"))
    assert changes == []


@pytest.mark.asyncio
async def test_get_renamed_diff(git_repo):
    (git_repo / "old.py").write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=git_repo, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True).stdout.strip()
    result = await get_renamed_diff("old.py", "new.py", sha, "HEAD", git_repo, {})
    assert isinstance(result, str)
