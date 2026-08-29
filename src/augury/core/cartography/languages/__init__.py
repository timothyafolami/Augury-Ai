"""Language adapters. Adding a language is a table entry, not a new pipeline."""

from __future__ import annotations

from pathlib import Path

from augury.core.cartography.languages import specs
from augury.core.cartography.languages.base import (
    Language,
    LanguageAdapter,
    ParsedModule,
    ParseError,
)
from augury.core.cartography.languages.python import PythonAdapter
from augury.core.cartography.languages.treesitter import TreeSitterAdapter

_ADAPTERS: dict[Language, LanguageAdapter] = {
    Language.PYTHON: PythonAdapter(),
    Language.GO: TreeSitterAdapter(Language.GO, "go", specs.GO_SIGNALS),
    Language.RUST: TreeSitterAdapter(Language.RUST, "rust", specs.RUST_SIGNALS),
    Language.JAVA: TreeSitterAdapter(Language.JAVA, "java", specs.JAVA_SIGNALS),
    Language.CPP: TreeSitterAdapter(Language.CPP, "cpp", specs.CPP_SIGNALS),
    Language.TYPESCRIPT: TreeSitterAdapter(
        Language.TYPESCRIPT, "typescript", specs.TYPESCRIPT_SIGNALS
    ),
    Language.JAVASCRIPT: TreeSitterAdapter(
        Language.JAVASCRIPT, "javascript", specs.TYPESCRIPT_SIGNALS
    ),
    # `.tsx` is TypeScript with JSX and the typescript grammar rejects it. Sent
    # there, 178 of one real frontend's files failed to parse and were reported
    # as unreadable rather than as unsupported.
    Language.TSX: TreeSitterAdapter(Language.TSX, "tsx", specs.TYPESCRIPT_SIGNALS),
}

# Extension to language. The one place a new file type is registered.
EXTENSIONS: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".h": Language.CPP,
}


def adapter_for(path: Path) -> LanguageAdapter | None:
    """The adapter for this file, or None if the language is not supported."""
    language = EXTENSIONS.get(path.suffix.lower())
    return _ADAPTERS[language] if language else None


__all__ = [
    "EXTENSIONS",
    "Language",
    "LanguageAdapter",
    "ParseError",
    "ParsedModule",
    "adapter_for",
]
