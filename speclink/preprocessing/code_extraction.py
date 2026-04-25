import threading
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor
import tree_sitter_python
import tree_sitter_typescript

QUERIES_DIR = Path(__file__).parent / "queries"

LANG_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}


_EXTRA_SYMBOLS = (
    ("variable.node", "variable.name"),
    ("interface.node", "interface.name"),
    ("typeAlias.node", "typeAlias.name"),
    ("enum.node", "enum.name"),
)


@dataclass
class _LangConfig:
    grammar: Language
    scm_path: Path
    query_text: str = field(init=False, repr=False)
    stored_query: Query = field(init=False, repr=False)
    thread_local: threading.local = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.query_text = self.scm_path.read_text()
        self.stored_query = Query(self.grammar, self.query_text)
        self.thread_local = threading.local()

    @property
    def parser(self) -> Parser:
        p = getattr(self.thread_local, "parser", None)
        if p is None:
            p = Parser(self.grammar)
            self.thread_local.parser = p
        return p


def signature(node: Node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    if body:
        return (
            source[node.start_byte : body.start_byte].decode(errors="replace").strip()
        )
    value = node.child_by_field_name("value")
    if value:
        fat_arrow = next((c for c in value.children if c.type == "=>"), None)
        if fat_arrow:
            return (
                source[node.start_byte : fat_arrow.end_byte]
                .decode(errors="replace")
                .strip()
            )
    return source[node.start_byte : node.end_byte].decode(errors="replace").strip()


def make_symbol(
    node: Node,
    name: str,
    file_id: str,
    parent_id: str | None,
    source: bytes,
) -> dict[str, object]:
    label = (parent_id.split("::")[-1] + "." if parent_id else "") + name
    return {
        "id": f"{file_id}::{label}",
        "name": name,
        "signature": signature(node, source),
        "code": source[node.start_byte : node.end_byte].decode(errors="replace"),
    }


def extract(
    source: bytes,
    file_path: Path,
    root: Path,
    lang_config: _LangConfig,
) -> dict[str, list[dict[str, object]] | list[str]]:
    tree = lang_config.parser.parse(source)
    file_id = str(file_path.relative_to(root))
    all_matches = list(QueryCursor(lang_config.stored_query).matches(tree.root_node))

    symbols: list[dict[str, object]] = []
    method_ids: set[int] = set()

    for _, caps in all_matches:
        if "class.node" in caps:
            node = caps["class.node"][0]
            name = caps["class.name"][0].text.decode()
            sym = make_symbol(
                node,
                name,
                file_id,
                None,
                source,
            )
            symbols.append(sym)

        if "method.node" in caps:
            node = caps["method.node"][0]
            method_ids.add(node.id)
            name = caps["method.name"][0].text.decode()
            parent_name = caps["method.parent"][0].text.decode()
            parent_id = f"{file_id}::{parent_name}"
            sym = make_symbol(
                node,
                name,
                file_id,
                parent_id,
                source,
            )
            symbols.append(sym)

    for _, caps in all_matches:
        if "function.node" in caps:
            node = caps["function.node"][0]
            if node.id in method_ids:
                continue
            name = caps["function.name"][0].text.decode()
            sym = make_symbol(
                node,
                name,
                file_id,
                None,
                source,
            )
            symbols.append(sym)

    for _, caps in all_matches:
        for node_key, name_key in _EXTRA_SYMBOLS:
            if node_key in caps and name_key in caps:
                node = caps[node_key][0]
                for name_node in caps[name_key]:
                    name = name_node.text.decode()
                    sym = make_symbol(
                        node,
                        name,
                        file_id,
                        None,
                        source,
                    )
                    symbols.append(sym)

    variables = _extract_variables(tree.root_node, source)

    return {"symbols": symbols, "variables": variables}


def _extract_variables(root: Node, source: bytes) -> list[str]:
    variables: list[str] = []
    for child in root.children:
        if child.type == "expression_statement":
            if any(stmt.type == "assignment" for stmt in child.children):
                variables.append(
                    source[child.start_byte : child.end_byte].decode(errors="replace").strip()
                )
        elif child.type in ("lexical_declaration", "variable_declaration"):
            variables.append(
                source[child.start_byte : child.end_byte].decode(errors="replace").strip()
            )
        elif child.type == "export_statement":
            for sub in child.children:
                if sub.type in ("lexical_declaration", "variable_declaration"):
                    variables.append(
                        source[child.start_byte : child.end_byte].decode(errors="replace").strip()
                    )
    return variables


_PYTHON_CONFIG = _LangConfig(
    Language(tree_sitter_python.language()), QUERIES_DIR / "python.scm"
)
_TYPESCRIPT_CONFIG = _LangConfig(
    Language(tree_sitter_typescript.language_typescript()),
    QUERIES_DIR / "typescript.scm",
)
_JAVASCRIPT_CONFIG = _LangConfig(
    Language(tree_sitter_typescript.language_tsx()), QUERIES_DIR / "typescript.scm"
)
EXTRACTORS = {
    "python": lambda src, fp, root: extract(src, fp, root, _PYTHON_CONFIG),
    "typescript": lambda src, fp, root: extract(src, fp, root, _TYPESCRIPT_CONFIG),
    "javascript": lambda src, fp, root: extract(src, fp, root, _JAVASCRIPT_CONFIG),
}
