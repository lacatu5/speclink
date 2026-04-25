from collections import defaultdict
from pathlib import Path

import pathspec
import typer
from beaupy import select_multiple

from ._templates import load_template_raw
from .core.logging import CONSOLE, log_error
from rich.panel import Panel
from .core.paths import (
    config_path,
    load_docs,
    save_docs,
    speclink_root,
)


def list_markdown_files(docs_path: Path) -> list[Path]:
    all_md = sorted(docs_path.rglob("*.md"))
    gitignore = docs_path / ".gitignore"
    if not gitignore.exists():
        return all_md
    try:
        patterns = [
            p
            for p in gitignore.read_text(encoding="utf-8").splitlines()
            if p and not p.startswith("#")
        ]
    except OSError:
        return all_md
    if not patterns:
        return all_md
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    return [
        f
        for f in all_md
        if not spec.match_file(str(f.relative_to(docs_path)))
    ]


PIPELINE_DEFAULTS = {
    "temperature": 0,
    "drop_params": True,
    "max_retries": 3,
    "timeout": 60,
    "max_concurrent": 50,
    "max_context_items": 30,
    "max_signatures": 100,
    "max_variables": 30,
    "rerank_floor": 0.5,
    "rerank_gap": 0.15,
    "max_paragraph_length": 2000,
    "max_paragraph_tokens": 8000,
}


def generate_workflow(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = load_template_raw("github_action")
    output_path.write_text(template)


def init_wizard(repo_path: Path) -> None:

    speclink_dir = speclink_root(repo_path)
    speclink_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_path(repo_path)
    existing_docs = load_docs(config_file)

    md_files = list_markdown_files(repo_path)
    if not md_files:
        log_error("no markdown files found")
        raise typer.Exit(1)

    by_folder: dict[str, list[Path]] = defaultdict(list)
    for f in md_files:
        rel = f.relative_to(repo_path)
        folder = str(rel.parts[0]) if len(rel.parts) > 1 else "(root)"
        by_folder[folder].append(f)

    choices = []
    for folder in sorted(by_folder.keys()):
        folder_files = by_folder[folder]
        for f in sorted(folder_files):
            rel_path = str(f.relative_to(repo_path))
            choices.append(rel_path)

    preselected_indices = [i for i, c in enumerate(choices) if c in existing_docs]
    while True:
        selected_files = select_multiple(
            options=choices,
            ticked_indices=preselected_indices or None,
            pagination=True,
            page_size=10,
        )
        if not selected_files:
            CONSOLE.print("[yellow]No files selected. Exiting.[/yellow]")
            raise typer.Exit(0)
        break

    save_docs(config_file, selected_files)

    if config_file.exists():
        import yaml
        data = yaml.safe_load(config_file.read_text()) or {}
        for key, value in PIPELINE_DEFAULTS.items():
            data.setdefault(key, value)
        config_file.write_text(yaml.dump(data, default_flow_style=False))

    CONSOLE.print(
        Panel(
            "Edit [bold].speclink/config.yaml[/bold] to tune pipeline settings.\n"
            "Run [bold]speclink guide[/bold] for setup instructions.",
            title="[bold green]Scope created[/bold green]",
            border_style="green",
        )
    )

    workflow_path = repo_path / ".github" / "workflows" / "speclink-sync.yml"
    generate_workflow(workflow_path)


def run_wizard(repo_root: Path) -> None:
    init_wizard(repo_root)
