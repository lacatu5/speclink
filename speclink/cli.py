import logging
from pathlib import Path

import structlog
import typer
from rich.panel import Panel

from .core.logging import CONSOLE, log_error
from .core.paths import config_path, docmap_path
from .retrieval import analyze_repo
from .rewrite import sync_repo
from .wizard import run_wizard

app = typer.Typer(add_completion=False)


logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


@app.command(
    help="Configure docs, pipeline mode, and generate GitHub Actions workflow."
)
def scope() -> None:
    repo_root = Path.cwd()
    run_wizard(repo_root)


@app.command(help="Map documentation sections to code files. Incremental by default.")
def analyze(
    full: bool = typer.Option(
        False,
        "--full",
        help="Force full re-analyze, ignoring cached mappings",
    ),
    eval_mode: bool = typer.Option(
        False,
        "--eval",
        help="Save evaluation data (rerank scores, classifications) to cache",
    ),
) -> None:
    repo_root = Path.cwd()

    config_file = config_path(repo_root)
    if not config_file.exists():
        CONSOLE.print("[red]Error:[/red] Run [bold]speclink scope[/bold] first")
        raise typer.Exit(code=1)

    try:
        analyze_repo(repo_root, full=full, eval_mode=eval_mode)
    except Exception as exc:
        log_error("analyze failed", stats={"error": str(exc)})
        raise typer.Exit(1)


@app.command(help="Show environment and GitHub secrets setup instructions.")
def guide() -> None:
    CONSOLE.print(
        Panel(
            "Add these secrets to your repository\n"
            "([dim]Settings → Secrets and variables → Actions[/dim])\n\n"
            "  • LLM_API_KEY\n"
            "  • LLM_MODEL\n"
            "  • RERANK_API_KEY\n"
            "  • RERANK_MODEL",
            title="GitHub Secrets Setup",
            border_style="blue",
        )
    )
    CONSOLE.print(
        Panel(
            "1. Create a [bold].env[/bold] file in your project root:\n\n"
            "  [dim]LLM_API_KEY=[/dim]<your-api-key>        [dim]# OpenAI, Anthropic, or Mistral[/dim]\n"
            "  [dim]LLM_MODEL=[/dim]<model-name>            [dim]# openai/gpt-4o, claude-3-5-sonnet-20240620[/dim]\n"
            "  [dim]RERANK_API_KEY=[/dim]<your-api-key>     [dim]# Cohere API key[/dim]\n"
            "  [dim]RERANK_MODEL=[/dim]<model-name>         [dim]# cohere/rerank-v3.5[/dim]\n\n"
            "  [dim]Speclink uses LiteLLM — 100+ models at[/dim] [blue]https://docs.litellm.ai/docs/providers[/blue]\n\n"
            "2. Run:  [bold]speclink analyze[/bold]\n"
            "3. Commit:  [bold]git add .speclink/ .github/ && git commit -m 'chore: init speclink'[/bold]",
            title="Environment Setup",
            border_style="green",
        )
    )


@app.command(help="Sync docs with code changes between base and HEAD commits.")
def sync() -> None:
    repo_root = Path.cwd()

    doc_map_file = docmap_path(repo_root)
    if not doc_map_file.exists():
        CONSOLE.print("[red]Error:[/red] Run [bold]speclink analyze[/bold] first")
        raise typer.Exit(1)

    try:
        analysis_report = sync_repo(repo_root)
    except Exception as exc:
        log_error("sync failed", stats={"error": str(exc)})
        raise typer.Exit(1)

    if analysis_report.total_errors:
        log_error("sync failed", stats={"errors": analysis_report.total_errors})
        raise typer.Exit(1)


if __name__ == "__main__":  # pragma: no cover
    app()

