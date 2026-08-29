"""What each language's failures look like.

A layer brief names a concern. This names how that concern shows up in the
runtime the file is written for, because "look for blocking work" means a
different search in `async def`, in a goroutine and on an event loop.

Kept beside the layer briefs rather than inside them: eight concerns times
seven languages is fifty-six documents nobody would maintain, and the two
compose at the point of use.
"""

from __future__ import annotations

from functools import cache

from augury.core.cartography.languages import Language
from augury.prompts import raw

# Runtimes that share a brief because they share a runtime.
ALIASES: dict[Language, Language] = {
    Language.TSX: Language.TYPESCRIPT,
    Language.JAVASCRIPT: Language.TYPESCRIPT,
}


@cache
def brief_for(language: Language) -> str:
    """The bottleneck notes for this language."""
    return raw(f"languages/{ALIASES.get(language, language).value}")
