"""Where a symbol is defined, according to the parser rather than the model.

The field run recorded in `docs/FIELD_RUN.md` found every finding naming the
right function and one of them naming a line 140 away from it. A model is
reliable about *what* it is discussing and unreliable about *where*, so the
line is taken back off it: the specialist names a symbol, and this resolves it.

Returning None is a real answer, and the contract is strict about it: a symbol
this cannot confirm *unambiguously* keeps whatever line the specialist gave.
Two definitions of one name resolve to neither. An earlier version returned the
first match, which meant a correctly-named line 47 was replaced by line 2 with
the authority of "the parser confirmed it" -- worse than the guess it replaced,
and harder to doubt.
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
    # `type_spec`, not `type_declaration`: Go puts the name on the inner node,
    # so the outer one can never resolve.
    Language.GO: frozenset({"function_declaration", "method_declaration", "type_spec"}),
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

# Terminals that carry a declared name. `type_identifier` was missing, so every
# Go type declaration and every Rust and C++ type resolved to None while
# DEFINITION_NODES advertised support for them.
_NAME_NODES = frozenset({"identifier", "field_identifier", "type_identifier"})

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
    qualifier, name = _split(symbol)
    if not name:
        return None
    found = (
        _find_python(source, name)
        if language is Language.PYTHON
        else _find_treesitter(source, name, language)
    )
    return _one_of(found, qualifier)


def _one_of(found: list[tuple[str, int]], qualifier: str) -> int | None:
    """The single line this names, or None when it names more than one.

    `found` is (enclosing scope, line) per match. A qualifier narrows; without
    one, two matches is ambiguity and ambiguity is unconfirmed.
    """
    if qualifier:
        narrowed = [line for scope, line in found if scope == qualifier]
        return narrowed[0] if len(narrowed) == 1 else None
    lines = {line for _, line in found}
    return next(iter(lines)) if len(lines) == 1 else None


def _split(symbol: str) -> tuple[str, str]:
    """`Class.method` and `pkg::thing` give their qualifier and their name."""
    cleaned = symbol.strip().replace("::", ".").split("(")[0].strip()
    qualifier, _, name = cleaned.rpartition(".")
    return qualifier.rsplit(".", 1)[-1], name.strip()


def _find_python(source: str, name: str) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(source)
    # RecursionError on a long chained expression, ValueError on a null byte:
    # neither is a SyntaxError, and both once propagated out of a paid review.
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []

    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    found: list[tuple[str, int]] = []

    def walk(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, definitions):
                if child.name == name:
                    found.append((scope, child.lineno))
                walk(child, child.name)
            else:
                walk(child, scope)

    try:
        walk(tree, "")
    except RecursionError:
        return []
    return found


def _find_treesitter(source: str, name: str, language: Language) -> list[tuple[str, int]]:
    grammar = _GRAMMARS.get(language)
    wanted = DEFINITION_NODES.get(language)
    if grammar is None or wanted is None:
        return []
    try:
        from tree_sitter_language_pack import get_parser

        tree = get_parser(grammar).parse(source.encode())
    except Exception:
        return []

    found: list[tuple[str, int]] = []
    stack: list[tuple[Node, str]] = [(tree.root_node, "")]
    while stack:
        node, scope = stack.pop()
        inner = scope
        if node.type in wanted:
            declared = _declared_name(node)
            if declared == name:
                found.append((scope, int(node.start_point[0]) + 1))
            if declared:
                inner = declared
        stack.extend((child, inner) for child in reversed(node.children))
    return found


def _declared_name(node: Node) -> str | None:
    """The identifier a definition node introduces, however the grammar spells it."""
    for field in ("name", "declarator"):
        child = node.child_by_field_name(field)
        while child is not None and child.type not in _NAME_NODES:
            # C and C++ wrap the name in nested declarators.
            child = child.child_by_field_name("declarator") or _first_identifier(child)
        if child is not None and child.text is not None:
            return child.text.decode()
    return None


def _first_identifier(node: Node) -> Node | None:
    for child in node.children:
        if child.type in _NAME_NODES:
            return child
    return None


def locator_for(root: Path) -> Callable[[str, str], int | None]:
    """A locator over a checkout: (repo-relative path, symbol) to line.

    Each file is read and parsed at most once per review. Anything that cannot
    be resolved -- a missing file, an unsupported extension, an unreadable
    encoding -- is None, which leaves the specialist's own line in place.
    """
    cache: dict[str, str | None] = {}

    anchor = root.resolve()

    def read(path: str) -> str | None:
        if path not in cache:
            cache[path] = _read_within(anchor, path)
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


# A file larger than this is not read to place a symbol. Matches the
# Cartographer's own cap, so a model-named path cannot pull in more than the
# mapper would have.
MAX_SOURCE_BYTES = 256 * 1024


def _read_within(anchor: Path, path: str) -> str | None:
    """Read a repo-relative path, refusing anything that leaves the root.

    `path` is written by the model, and `anchor / path` silently discards the
    anchor when `path` is absolute. The MCP server enforces this boundary on
    the path a client supplies and must not lose it on the paths a model
    invents.
    """
    candidate = anchor / path
    try:
        resolved = candidate.resolve()
        if not resolved.is_relative_to(anchor):
            return None
        if resolved.stat().st_size > MAX_SOURCE_BYTES:
            return None
        return resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
