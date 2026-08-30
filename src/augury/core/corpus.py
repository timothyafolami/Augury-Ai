"""The lab, as reference material a specialist can actually cite.

The analyst prompt says the mechanisms it is checking against "come from a
practice lab written before this review existed, and they are the source of
your authority. Cite them." It was then handed the specialist's own brief, the
same twenty-four lines it already had under another heading, so it had a brief
and no corpus and was invited to attribute the brief to a lab it had never
seen.

The lab is a separate repository. This has to work when it is absent, because a
judge cloning only Augury must still get a review, and must get a prompt that
does not claim to cite what it was not given.

Bounded, because this is sent on every call: a whole layer is tens of thousands
of tokens, once per module per specialist, and the cap is the difference
between a corpus and a bill. Deterministic, because a corpus that varies is a
cassette that never replays.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Where a reader is told to look for the lab if it is not beside this checkout.
LAB_ENV = "AUGURY_LAB"

# What one specialist may carry. Roughly two thousand tokens: enough for the
# mechanism of every topic in a layer, far short of the topics themselves.
MOST_CHARS = 8_000

# What each topic is worth quoting for. The lab writes every topic the same
# way, and this is the paragraph that states the mechanism rather than the
# experiment, the code or the questions.
_TAKEAWAY = re.compile(
    r"\*\*The one idea:\*\*(?P<idea>.+?)(?=\n\s*\n|\*\*Why it matters)", re.DOTALL
)
_MATTERS = re.compile(
    r"\*\*Why it matters in practice:\*\*(?P<why>.+?)(?=\n\s*\n|\*\*You'll know)", re.DOTALL
)


def lab_root(explicit: Path | None = None) -> Path | None:
    """Where the practice lab is, if it is anywhere.

    Beside this checkout is the ordinary case, since the two repositories were
    written together. The environment wins, so a judge holding both does not
    have to move either.
    """
    if explicit is not None:
        return explicit if explicit.is_dir() else None
    stated = os.environ.get(LAB_ENV, "")
    if stated:
        found = Path(stated).expanduser()
        return found if found.is_dir() else None
    beside = Path(__file__).resolve().parents[3].parent / "software-engineering-practice"
    return beside if beside.is_dir() else None


def corpus_for(lab_layer: str, *, lab: Path | None = None) -> str:
    """The mechanisms this layer teaches, each with the topic it came from.

    Empty when the lab is not present, and empty rather than a sentence about
    being empty: a corpus that explains its own absence is still something the
    specialist has to read on every call.
    """
    root = lab_root(lab)
    if root is None:
        return ""

    layer = root / lab_layer
    if not layer.is_dir():
        return ""

    quoted: list[str] = []
    used = 0
    # Sorted, because the topics are numbered and a corpus that varies between
    # runs is a cassette that never replays.
    for topic in sorted(layer.iterdir()):
        readme = topic / "README.md"
        if not topic.is_dir() or not readme.is_file():
            continue
        mechanism = _mechanism(readme.read_text(encoding="utf-8", errors="replace"))
        if not mechanism:
            continue
        entry = f"- **{topic.name}** — {mechanism}"
        if used + len(entry) > MOST_CHARS:
            break
        quoted.append(entry)
        used += len(entry)

    return "\n".join(quoted)


def _mechanism(readme: str) -> str:
    """One topic's mechanism, from the block the lab puts it in."""
    idea = _TAKEAWAY.search(readme)
    if idea is None:
        return ""
    said = _flatten(idea.group("idea"))
    matters = _MATTERS.search(readme)
    if matters is not None:
        said = f"{said} {_flatten(matters.group('why'))}"
    return said


def _flatten(text: str) -> str:
    """One paragraph on one line, so a bullet stays a bullet."""
    return " ".join(text.split()).strip()
