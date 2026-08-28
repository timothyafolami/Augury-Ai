"""One adapter for the five non-Python languages, parameterised by grammar.

tree-sitter gives a single parsing interface across every language the practice
lab teaches, so support for Go, Rust, Java, TypeScript and C++ is a table of
node types and a signal map rather than five hand-written parsers.
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from augury.core.cartography.languages.base import (
    Language,
    LanguageAdapter,
    ParsedModule,
    ParseError,
)
from augury.core.cartography.model import Signal

# The statement that carries a dependency, per grammar.
IMPORT_NODES: dict[Language, frozenset[str]] = {
    Language.GO: frozenset({"import_spec"}),
    Language.RUST: frozenset({"use_declaration"}),
    Language.JAVA: frozenset({"import_declaration"}),
    Language.TYPESCRIPT: frozenset({"import_statement", "call_expression"}),
    Language.JAVASCRIPT: frozenset({"import_statement", "call_expression"}),
    Language.CPP: frozenset({"preproc_include"}),
}

# Node in the wild is still overwhelmingly CommonJS, so `require` counts as an
# import. Any other call is not: reading every call's string argument would
# make a log line mentioning "redis" look like a Redis client.
REQUIRE_CALLS = frozenset({"require"})

# The node *inside* that statement holding the name. Reading the name node
# rather than the whole statement is what keeps `import axios from 'axios'`
# from becoming the string "axios 'axios", which only ever matched by accident.
NAME_NODES: dict[Language, frozenset[str]] = {
    Language.GO: frozenset({"interpreted_string_literal", "raw_string_literal"}),
    Language.RUST: frozenset({"scoped_identifier", "identifier", "crate"}),
    Language.JAVA: frozenset({"scoped_identifier"}),
    Language.TYPESCRIPT: frozenset({"string"}),
    Language.JAVASCRIPT: frozenset({"string"}),
    Language.CPP: frozenset({"system_lib_string", "string_literal"}),
}

_SEPARATORS = ("/", ".", "::")


@dataclass(frozen=True)
class TreeSitterAdapter(LanguageAdapter):
    """Parses one language and reports its imports and layer signals."""

    _language: Language
    _grammar: str
    _signals: dict[str, frozenset[Signal]]

    @property
    def language(self) -> Language:
        return self._language

    def parse(self, source: str, *, package: str) -> ParsedModule:
        tree = get_parser(self._grammar).parse(source.encode())
        if tree.root_node.has_error:
            raise ParseError(f"{self._language} source did not parse cleanly")

        imports = self._imports(tree.root_node)
        signals: set[Signal] = set()
        unmatched: set[str] = set()
        for name in imports:
            matched = self._signals_for(name)
            if matched:
                signals |= matched
            else:
                unmatched.add(name)

        return ParsedModule(
            loc=sum(1 for line in source.splitlines() if line.strip()),
            imports=frozenset(imports),
            signals=frozenset(signals),
            unmatched_imports=frozenset(unmatched),
        )

    # -- extraction --------------------------------------------------------

    def _imports(self, root: Node) -> set[str]:
        return {
            name
            for statement in self._descendants(root, IMPORT_NODES[self._language])
            if self._is_dependency(statement) and (name := self._name_in(statement))
        }

    @staticmethod
    def _is_dependency(statement: Node) -> bool:
        """A call statement only counts when it is a `require`."""
        if statement.type != "call_expression":
            return True
        function = statement.child_by_field_name("function")
        return (
            function is not None
            and function.text is not None
            and (function.text.decode() in REQUIRE_CALLS)
        )

    def _name_in(self, statement: Node) -> str:
        """The dependency name, from the first name node inside the statement.

        Falls back to the statement's own text so an unfamiliar grammar shape
        degrades to something matchable rather than to nothing.
        """
        for node in self._descendants(statement, NAME_NODES[self._language]):
            if node.text is not None:
                return _unquote(node.text.decode())
        return _unquote(statement.text.decode()) if statement.text else ""

    @staticmethod
    def _descendants(root: Node, wanted: frozenset[str]) -> list[Node]:
        found: list[Node] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in wanted:
                found.append(node)
            stack.extend(reversed(node.children))
        return found

    # -- matching ----------------------------------------------------------

    def _signals_for(self, name: str) -> frozenset[Signal]:
        matched: set[Signal] = set()
        for prefix, signals in self._signals.items():
            if _is_leading_segment(prefix, name):
                matched |= signals
        return frozenset(matched)


def _unquote(text: str) -> str:
    """Strip the syntax around a name, and normalise Node's `node:` prefix.

    `node:http` and `http` are the same module; modern Node prefers the
    prefixed form, so not normalising silently zeroes the signal.
    """
    name = text.strip().strip("\"'<>`").strip()
    return name.removeprefix("node:")


def _is_leading_segment(prefix: str, name: str) -> bool:
    """True when `name` starts with `prefix` at a segment boundary.

    Segment-aware so `net` does not match `internet` and `log` does not match
    `logrus`, while `java.util.concurrent` still matches
    `java.util.concurrent.Executor`.
    """
    if name == prefix:
        return True
    return any(name.startswith(f"{prefix}{separator}") for separator in _SEPARATORS)
