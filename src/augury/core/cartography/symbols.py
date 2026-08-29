"""Where a symbol is defined, according to the parser rather than the model.

The field run recorded in `docs/FIELD_RUN.md` found every finding naming the
right function and one of them naming a line 140 away from it. A model is
reliable about *what* it is discussing and unreliable about *where*, so the
line is taken back off it: the specialist names a symbol, and this resolves it.

Returning None is a real answer. A symbol this cannot confirm keeps whatever
line the specialist gave, because replacing a guess with a different guess is
not an improvement.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from tree_sitter import Node

from augury.core.cartography.languages import EXTENSIONS, Language

# Tree-sitter node types that introduce a named definition, per grammar. A
# grammar absent from this table simply yields no correction.
DEFINITION_NODES: dict[Language, frozenset[str]] = {
    Language.GO: frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    Language.RUST: frozenset({"function_item", "struct_item", "enum_item", "trait_item"}),
    Language.JAVA: frozenset({"method_declaration", "class_declaration", "interface_declaration"}),
    Language.CPP: frozenset({"function_definition", "class_specifier", "struct_specifier"}),
    Language.TYPESCRIPT: frozenset(
        {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "generator_function_declaration",
        }
    ),
    Language.JAVASCRIPT: frozenset(
        {
            "function_declaration",
            "method_definition",
            "class_declaration",
            "generator_function_declaration",
        }
    ),
}

# Grammar name per language, matching tree-sitter-language-pack.
_GRAMMARS: dict[Language, str] = {
    Language.GO: "go",
    Language.RUST: "rust",
    Language.JAVA: "java",
    Language.CPP: "cpp",
    Language.TYPESCRIPT: "typescript",
    Language.JAVASCRIPT: "javascript",
}


def locate(source: str, symbol: str, language: Language) -> int | None:
    """The 1-based line where `symbol` is defined, or None if unconfirmed."""
    name = _last_segment(symbol)
    if not name:
        return None
    if language is Language.PYTHON:
        return _locate_python(source, name)
    return _locate_treesitter(source, name, language)


def _last_segment(symbol: str) -> str:
    """`Class.method` and `pkg::thing` both name their final segment."""
    cleaned = symbol.strip().replace("::", ".").split("(")[0]
    return cleaned.rsplit(".", 1)[-1].strip()


def _locate_python(source: str, name: str) -> int | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if isinstance(node, definitions) and node.name == name:
            return node.lineno
    return None


def _locate_treesitter(source: str, name: str, language: Language) -> int | None:
    grammar = _GRAMMARS.get(language)
    wanted = DEFINITION_NODES.get(language)
    if grammar is None or wanted is None:
        return None
    try:
        from tree_sitter_language_pack import get_parser

        tree = get_parser(grammar).parse(source.encode())
    except Exception:
        return None

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in wanted and _declared_name(node) == name:
            return int(node.start_point[0]) + 1
        stack.extend(reversed(node.children))
    return None


def _declared_name(node: Node) -> str | None:
    """The identifier a definition node introduces, however the grammar spells it."""
    for field in ("name", "declarator"):
        child = node.child_by_field_name(field)
        while child is not None and child.type not in ("identifier", "field_identifier"):
            # C and C++ wrap the name in nested declarators.
            child = child.child_by_field_name("declarator") or _first_identifier(child)
        if child is not None and child.text is not None:
            return child.text.decode()
    return None


def _first_identifier(node: Node) -> Node | None:
    for child in node.children:
        if child.type in ("identifier", "field_identifier"):
            return child
    return None


def locator_for(root: Path) -> Callable[[str, str], int | None]:
    """A locator over a checkout: (repo-relative path, symbol) to line.

    Each file is read and parsed at most once per review. Anything that cannot
    be resolved -- a missing file, an unsupported extension, an unreadable
    encoding -- is None, which leaves the specialist's own line in place.
    """
    cache: dict[str, str | None] = {}

    def read(path: str) -> str | None:
        if path not in cache:
            candidate = root / path
            try:
                cache[path] = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                cache[path] = None
        return cache[path]

    def locate_in(path: str, symbol: str) -> int | None:
        language = EXTENSIONS.get(Path(path).suffix.lower())
        if language is None:
            return None
        source = read(path)
        if source is None:
            return None
        return locate(source, symbol, language)

    return locate_in
