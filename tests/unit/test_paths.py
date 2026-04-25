from __future__ import annotations


import subprocess

import pytest

from speclink.core.paths import (
    atomic_write,
    config_path,
    docmap_path,
    get_head_sha,
    load_docs,
    save_docs,
    speclink_root,
)


def test_speclink_root(tmp_path):
    assert speclink_root(tmp_path) == tmp_path / ".speclink"


def test_config_path(tmp_path):
    assert config_path(tmp_path) == tmp_path / ".speclink" / "config.yaml"


def test_docmap_path(tmp_path):
    assert docmap_path(tmp_path) == tmp_path / ".speclink" / "docmap.json"


def test_atomic_write(tmp_path):
    target = tmp_path / "out.txt"
    atomic_write(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "out.txt"
    atomic_write(target, "data")
    assert target.read_text() == "data"


def test_atomic_write_cleanup_on_error(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    tmp_files_before = set(tmp_path.glob("*.tmp"))
    monkeypatch.setattr("os.replace", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        atomic_write(target, "x")
    tmp_files_after = set(tmp_path.glob("*.tmp"))
    assert tmp_files_after == tmp_files_before


def test_get_head_sha(git_repo):
    (git_repo / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=git_repo, capture_output=True, check=True
    )
    sha = get_head_sha(git_repo)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_load_docs_nonexistent(tmp_path):
    assert load_docs(tmp_path / "nope.yaml") == []


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "docs.yaml"
    docs = ["docs/a.md", "docs/b.md"]
    save_docs(path, docs)
    assert load_docs(path) == docs
