import json
import time
from pathlib import Path
from typing import Any

import structlog

from .models import DocMap
from .paths import SPECLINK_DIR, atomic_write

log = structlog.get_logger()


class Store:
    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root / SPECLINK_DIR

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            atomic_write(path, json.dumps(payload, indent=2))
        except (OSError, ValueError) as e:
            log.error("store_write_failed", error_type=type(e).__name__, file=str(path))
            raise

    def persist_doc_map(
        self, doc_map: DocMap, path: Path, codebase_sha: str | None = None
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if codebase_sha:
            doc_map.codebase_sha = codebase_sha
        raw = doc_map.model_dump(exclude_defaults=True)
        for mapping in raw.get("mappings", []):
            mapping["sections"].sort(
                key=lambda s: (s.get("heading", ""), s.get("chunk_index", 0))
            )
            for section in mapping.get("sections", []):
                section["files"] = sorted(
                    section.get("files", [])
                )
        raw["mappings"].sort(key=lambda m: m.get("doc_file", ""))
        self._write_json(path, raw)

    def save_eval(
        self,
        kind: str,
        model: str,
        entries: list[dict[str, Any]],
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        eval_mode: bool = False,
    ) -> None:
        if not eval_mode:
            return
        run_dir = self.root / "runs" / kind
        run_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "model": model,
            "entries": entries,
        }
        if kind == "reranker":
            data["tokens"] = input_tokens
        else:
            data["input_tokens"] = input_tokens
            data["output_tokens"] = output_tokens
        self._write_json(run_dir / f"{int(time.time())}.json", data)
