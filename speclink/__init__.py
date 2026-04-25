from importlib.metadata import version

from .core.paths import load_docs, save_docs
from .retrieval.analyzer import Analyzer
from .wizard import run_wizard

__version__ = version("speclink")

__all__ = [
    "Analyzer",
    "load_docs",
    "run_wizard",
    "save_docs",
]
