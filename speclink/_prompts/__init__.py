from pathlib import Path

import yaml

_PROMPTS_DIR = Path(__file__).parent

__all__ = ["load_prompt"]


def load_prompt(name: str) -> dict[str, str]:
    return yaml.safe_load((_PROMPTS_DIR / f"{name}.yaml").read_text())
