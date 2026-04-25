from rich.console import Console
from rich.theme import Theme

RICH_THEME = Theme(
    {
        "stage": "bold cyan",
        "stat.key": "dim",
        "stat.val": "bold white",
        "stat.sep": "dim",
        "done": "bold green",
        "warn": "bold yellow",
        "err": "bold red",
    }
)

CONSOLE = Console(theme=RICH_THEME, stderr=True)


def format_stats(stats: dict[str, str | int | float]) -> str:
    parts = []
    for k, v in stats.items():
        parts.append(f"[stat.key]{k}[/] [stat.val]{v}[/]")
    return "  [stat.sep]·[/]  ".join(parts)


_STYLES = {
    "stage": "  [stage]▸[/]  {message}",
    "warn": "  [warn]![/]  {message}",
    "error": "  [err]✗[/]  {message}",
}


def _log(
    level: str,
    message: str,
    *,
    elapsed: str | None = None,
    stats: dict[str, str | int | float] | None = None,
) -> None:
    line = _STYLES[level].format(message=message)
    if stats:
        line += f"    {format_stats(stats)}"
    if elapsed:
        line += f"  [dim]{elapsed}[/]"
    CONSOLE.print(line)


def log_stage(
    message: str,
    *,
    elapsed: str | None = None,
    stats: dict[str, str | int | float] | None = None,
) -> None:
    _log("stage", message, elapsed=elapsed, stats=stats)


def log_warn(message: str, stats: dict[str, str | int | float] | None = None) -> None:
    _log("warn", message, stats=stats)


def log_error(message: str, stats: dict[str, str | int | float] | None = None) -> None:
    _log("error", message, stats=stats)
