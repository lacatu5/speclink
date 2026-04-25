import contextlib
from collections.abc import Iterator
from pathlib import Path

import pathspec
import structlog

from speclink.core.models import CodeElement

from .code_extraction import EXTRACTORS, LANG_MAP

_INCLUDE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}

log = structlog.get_logger()


def collect_signatures_and_bodies(
    symbols: list[CodeElement],
) -> list[dict[str, str | None]]:
    code_entries = []
    for s in symbols:
        if not s.signature and not s.code:
            continue
        sig_entry = {
            "name": s.name,
            "signature": s.signature or s.name,
        }
        if s.code:
            sig_entry["body_sample"] = s.code.strip()
        code_entries.append(sig_entry)
    return code_entries


class _Scanner:
    def __init__(self, extension_lang_map: dict[str, str]) -> None:
        self.lang_map = extension_lang_map
        self.root: Path | None = None
        self.root_spec: pathspec.PathSpec | None = None
        self.ignore_specs: dict[str, list[tuple[Path, pathspec.PathSpec]]] = {}

    def _load_dir_specs(
        self, current_dir: Path
    ) -> list[tuple[Path, pathspec.PathSpec]]:
        dir_key = str(current_dir)
        if dir_key in self.ignore_specs:
            return self.ignore_specs[dir_key]
        specs: list[tuple[Path, pathspec.PathSpec]] = []
        ignore_file = current_dir / ".gitignore"
        if ignore_file.exists():
            try:
                patterns = [
                    p
                    for p in ignore_file.read_text(encoding="utf-8").splitlines()
                    if p and not p.startswith("#")
                ]
                if patterns:
                    specs.append(
                        (
                            ignore_file.parent,
                            pathspec.PathSpec.from_lines("gitwildmatch", patterns),
                        ),
                    )
            except (OSError, ValueError):
                pass
        self.ignore_specs[dir_key] = specs
        return specs

    def is_ignored(self, root: Path, file_path: Path) -> bool:
        rel_path = file_path.relative_to(root)

        if self.root is None or self.root != root:
            self.root = root
            self.root_spec = load_gitignore(root)

        if self.root_spec.match_file(str(rel_path)):
            return True

        current_dir = file_path.parent

        while current_dir not in (root, root.parent):
            for ignore_parent, spec in self._load_dir_specs(current_dir):
                path_relative_to_gitignore = file_path.relative_to(ignore_parent)
                if spec.match_file(str(path_relative_to_gitignore)):
                    return True

            current_dir = current_dir.parent

        return False

    def scan(self, root: Path) -> Iterator[tuple[Path, str]]:
        for dir_path, dirnames, filenames in root.walk():

            filtered_dirs = []
            for d in dirnames:
                dir_full_path = dir_path / d
                if self.is_ignored(root, dir_full_path):
                    continue
                filtered_dirs.append(d)
            dirnames[:] = filtered_dirs

            for fname in filenames:
                file_path = dir_path / fname

                if self.is_ignored(root, file_path):
                    continue

                lang = self.lang_map.get(Path(fname).suffix.lower())
                if lang:
                    yield file_path, lang


def scan(root: Path) -> Iterator[tuple[Path, str]]:
    scanner = _Scanner(extension_lang_map=LANG_MAP)
    yield from scanner.scan(root)


def load_gitignore(
    root: Path,
) -> pathspec.PathSpec:
    patterns: list[str] = []

    gitignore = root / ".gitignore"
    with contextlib.suppress(OSError):
        patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


class CodePreprocessor:
    def __init__(self) -> None:
        self.variables_map: dict[str, list[str]] = {}

    def process_codebase(self, root: str | Path) -> list[CodeElement]:
        root_path = Path(root)
        elements: list[CodeElement] = []
        self.variables_map = {}

        for abs_path, lang in scan(root_path):
            rel_path = str(abs_path.relative_to(root_path))

            extractor = EXTRACTORS.get(lang)
            if not extractor:
                continue

            try:
                source_bytes = abs_path.read_bytes()
                extraction = extractor(source_bytes, abs_path, root_path)
                symbols = extraction.get("symbols", [])
                file_vars = extraction.get("variables")
                if file_vars:
                    self.variables_map[rel_path] = file_vars
            except FileNotFoundError:
                log.warning("file_not_found", file=str(abs_path))
                continue
            except PermissionError:
                log.warning("permission_denied", file=str(abs_path))
                continue
            except (OSError, ValueError) as e:
                log.error("extraction_failed", file=str(abs_path), error=str(e))
                continue

            for symbol in symbols:
                elements.append(
                    CodeElement(
                        id=f"{rel_path}::{symbol['name']}",
                        name=symbol["name"],
                        signature=symbol["signature"],
                        code=symbol.get("code") or "",
                        file_path=rel_path,
                    ),
                )

        return elements


class FilePreprocessor:
    def process_codebase(self, root: str | Path) -> list[CodeElement]:
        root_path = Path(root)
        elements: list[CodeElement] = []

        spec = load_gitignore(root_path)

        for dir_path, dirnames, filenames in root_path.walk():
            rel_dir = dir_path.relative_to(root_path)
            dirnames[:] = [
                d for d in sorted(dirnames) if not spec.match_file(str(rel_dir / d))
            ]

            for fname in sorted(filenames):
                rel_file = str(rel_dir / fname)
                if spec.match_file(rel_file):
                    continue
                ext = Path(fname).suffix
                if ext not in _INCLUDE_EXTENSIONS:
                    continue

                abs_file = dir_path / fname
                try:
                    content = abs_file.read_text(encoding="utf-8", errors="ignore")
                except FileNotFoundError:
                    log.warning("file_not_found", file=str(abs_file))
                    continue
                except PermissionError:
                    log.warning("permission_denied", file=str(abs_file))
                    continue
                except (OSError, ValueError):
                    continue

                elements.append(
                    CodeElement(
                        id=f"file:{rel_file}",
                        name=abs_file.name,
                        signature="",
                        code=content,
                        file_path=rel_file,
                    ),
                )

        return elements
