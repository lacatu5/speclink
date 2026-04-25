import contextlib
import os
import subprocess
import tempfile
from pathlib import Path

import structlog
import yaml

SPECLINK_DIR = ".speclink"
CONFIG_FILE = "config.yaml"
DOCMAP_FILE = "docmap.json"


log = structlog.get_logger()


def speclink_root(repo: Path) -> Path:
    return repo / SPECLINK_DIR


def config_path(repo: Path) -> Path:
    return speclink_root(repo) / CONFIG_FILE


def docmap_path(repo: Path) -> Path:
    return speclink_root(repo) / DOCMAP_FILE


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def get_head_sha(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()
    except subprocess.CalledProcessError as exc:
        log.warning("git rev-parse failed", error=str(exc))
        return "unknown"


def load_docs(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("docs", [])
    return []


def save_docs(path: Path, docs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text())
        if isinstance(loaded, dict):
            existing = loaded
    existing["docs"] = docs
    atomic_write(path, yaml.dump(existing, default_flow_style=False))
