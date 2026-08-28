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
