"""The boundary that keeps the rest of the system language-agnostic.

An adapter turns one source file into a `ParsedModule`. Everything downstream
of cartography, the Scheduler included, consumes `ModuleNode` and never learns
which language produced it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from augury.core.cartography.model import Signal


class Language(StrEnum):
    """The six the practice lab teaches, plus JavaScript alongside TypeScript."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"


class ParseError(Exception):
    """The file could not be parsed. Recorded, never fatal."""


class ParsedModule(BaseModel):
    """What every adapter must produce, whatever the runtime."""

    loc: int = Field(ge=0, description="Non-blank source lines")
    imports: frozenset[str] = Field(
        default_factory=frozenset,
        description="Dotted or quoted names this file depends on, as written",
    )
    named_in_strings: frozenset[str] = Field(
        default_factory=frozenset,
        description="Dotted names appearing as string constants, which may be "
        "dynamic imports. Kept apart from `imports` because they are guesses: "
        "the mapper resolves them by exact match only, where a real import "
        "statement is allowed to fall back to its package.",
    )
    third_party: frozenset[str] = Field(
        default_factory=frozenset,
        description="Top-level names imported from outside the standard "
        "library. Unlike `unmatched_imports` this keeps the ones a signal "
        "table recognised, because those are exactly the packages worth "
        "asking a registry about.",
    )
    signals: frozenset[Signal] = Field(default_factory=frozenset)
    unmatched_imports: frozenset[str] = Field(
        default_factory=frozenset,
        description="External imports no detector recognised",
    )


class LanguageAdapter(Protocol):
    """Parses one language into the shared representation."""

    @property
    def language(self) -> Language: ...

    def parse(self, source: str, *, package: str) -> ParsedModule: ...
