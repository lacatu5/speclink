from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent

__all__ = ["load_template_raw"]


def load_template_raw(name: str) -> str:
    return (_TEMPLATES_DIR / f"{name}.yaml").read_text()
