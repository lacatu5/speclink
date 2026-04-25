import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

from speclink.core.models import DocMap

log = structlog.get_logger()

@dataclass
class FileChange:
    path: str
    change_type: str
    old_path: str | None = None


@dataclass
class StaleSection:
    doc_file: str
    heading: str
    changed_files: list[str]


async def get_diff_context(
    changed_files: list[str],
    repo_root: Path,
    base_sha: str | None = None,
) -> str:
    if not changed_files:
        return ""

    try:
        args = ["git", "diff"]
        if base_sha:
            args.append(base_sha)
        else:
            args.append("HEAD")
        args.append("--")
        args.extend(changed_files)

        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        if output:
            return output
        return "[No diff - files may be new or untracked]"
    except FileNotFoundError:
        return "[Error getting diff: git not found]"
    except PermissionError:
        return "[Error getting diff: permission denied]"
    except (OSError, ValueError) as e:
        return f"[Error getting diff: {e}]"


def get_file_changes(base_sha: str, head_sha: str, repo_root: Path) -> list[FileChange]:
    try:
        diff_spec = base_sha if head_sha == "HEAD" else f"{base_sha}..{head_sha}"
        git_name_status = subprocess.run(  # noqa: S603
            [
                "git",
                "diff",
                "--find-renames",
                "--name-status",
                "--relative",
                diff_spec,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    changes = []
    for line in git_name_status.stdout.strip().split("\n"):
        if not line.strip():
            continue

        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue

        status = parts[0][0]
        path = parts[1]

        match status:
            case "D":
                changes.append(FileChange(path, "deleted"))
            case "M":
                changes.append(FileChange(path, "modified"))
            case "R":
                old_path = parts[1]
                new_path = parts[2] if len(parts) >= 3 else parts[1]
                changes.append(FileChange(new_path, "renamed", old_path))

    return changes


def find_stale_sections(
    doc_map: DocMap,
    changed_files: list[str],
) -> list[StaleSection]:
    changed_set = set(changed_files)
    stale = []

    for doc_mapping in doc_map.mappings:
        doc_file = doc_mapping.doc_file
        for section in doc_mapping.sections:
            section_files = set(section.files)

            overlap = changed_set & section_files
            if overlap:
                stale.append(
                    StaleSection(
                        doc_file=doc_file,
                        heading=section.heading,
                        changed_files=list(overlap),
                    ),
                )

    return stale


async def get_renamed_diff(
    old_path: str,
    new_path: str,
    base_sha: str,
    head_sha: str,
    repo_root: Path,
    diff_cache: dict[str, str],
) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--show-prefix",
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        prefix = stdout.decode().strip()

        if head_sha == "HEAD":
            args = ["git", "diff", f"{base_sha}:{prefix}{old_path}", "--", new_path]
        else:
            args = [
                "git",
                "diff",
                f"{base_sha}:{prefix}{old_path}",
                f"{head_sha}:{prefix}{new_path}",
            ]

        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        return output or ""
    except (OSError, UnicodeDecodeError) as exc:
        log.warning(
            "git_renamed_diff_failed", old=old_path, new=new_path, error=str(exc)
        )
        return diff_cache.get(new_path, "")
