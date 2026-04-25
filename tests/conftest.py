from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from speclink.core.config import PipelineConfig
    from speclink.core.models import CodeElement, DocMap, Section

os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("RERANK_MODEL", "test-rerank")
os.environ.setdefault("RERANK_API_KEY", "test-rerank-key")


def git_init(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )


def git_commit(tmp_path: Path, msg: str = "commit") -> str:
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", msg], cwd=tmp_path, capture_output=True, check=True
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_doc_map(tmp_path: Path, base_sha: str, mappings: list[dict]) -> Path:
    speclink = tmp_path / ".speclink"
    speclink.mkdir(parents=True, exist_ok=True)
    doc_map = {"codebase_sha": base_sha, "mappings": mappings}
    path = speclink / "docmap.json"
    path.write_text(json.dumps(doc_map))
    return path


def section_hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    git_init(tmp_path)
    return tmp_path


@pytest.fixture
def mock_config() -> PipelineConfig:
    from speclink.core.config import PipelineConfig
    return PipelineConfig(
        llm_model="test-model",
        llm_api_key="test-key",
        rerank_model="test-rerank",
        rerank_api_key="test-rerank-key",
    )


@pytest.fixture
def sample_section() -> Section:
    from speclink.core.models import Section
    return Section(
        heading="API Overview",
        content="This section describes the API.",
        file_path="docs/api.md",
        hash="abc123",
        chunk_index=0,
    )


@pytest.fixture
def sample_code_element() -> CodeElement:
    from speclink.core.models import CodeElement
    return CodeElement(
        id="src/api.py::get_user",
        name="get_user",
        signature="def get_user(user_id: int) -> User",
        code="def get_user(user_id: int) -> User:\n    return User(user_id)",
        file_path="src/api.py",
    )


@pytest.fixture
def sample_doc_map() -> DocMap:
    from speclink.core.models import DocMap, Document, Section
    return DocMap(
        codebase_sha="abc123",
        mappings=[
            Document(
                doc_file="docs/api.md",
                sections=[
                    Section(
                        heading="API Overview",
                        files=["src/api.py"],
                        hash="hash1",
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def mini_project(git_repo: Path) -> Path:
    docs = git_repo / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(
        "# API Overview\n\nThis describes the API.\n\n## Endpoints\n\nGET /users\n"
    )

    src = git_repo / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "api.py").write_text(
        'def get_user(user_id: int) -> dict:\n    return {"id": user_id}\n\ndef create_user(name: str) -> dict:\n    return {"name": name}\n'
    )

    git_commit(git_repo, "initial")
    return git_repo
