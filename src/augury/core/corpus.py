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

# The extract, committed. The lab is a separate repository, and a judge holding
# only Augury got an empty corpus, a different prompt and a miss on every
# cassette -- so the published table could not be reproduced by the one person
# it was published for. Found by cloning this repository and running the
# evaluation in it.
#
# The lab remains the source. This is what ships, and it is preferred over the
# lab so that a machine which happens to have both records cassettes anybody
# can replay.
EXTRACT = Path(__file__).resolve().parent / "corpus"

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

    The committed extract, unless a caller names a lab explicitly.

    The lab used to win whenever a checkout happened to sit beside the
    repository. The two texts agree today, so nothing showed; the day the lab
    is edited, prompts recorded on a machine that has it stop replaying on
    every machine that does not, and the cassette set silently becomes
    unusable by everyone but its author. Preferring the shipped copy means
    one commit builds one prompt everywhere. `extract_from` names the lab and
    still reads it, which is how the shipped copy is regenerated.

    An explicit path that is not a directory falls through to the extract
    rather than returning nothing, because a mistyped lab should cost the
    caller its override and not the specialist its corpus.

    Empty when neither is present, and empty rather than a sentence about being
    empty: a corpus explaining its own absence is still something the
    specialist reads on every call.
    """
    root = lab_root(lab) if lab is not None else None
    if root is None:
        # The shipped copy, whether or not a lab is sitting beside this
        # checkout. This is the path every run takes unless one is named.
        shipped = EXTRACT / f"{lab_layer}.md"
        return shipped.read_text(encoding="utf-8").strip() if shipped.is_file() else ""

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


def extract_from(lab: Path, into: Path = EXTRACT) -> list[str]:
    """Write the corpus this repository ships, from the lab it came from.

    Run when the lab changes. The output is committed, because the alternative
    is a prompt that differs depending on which repositories the reader
    happens to have cloned.
    """
    into.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for layer in sorted(lab.iterdir()):
        if not layer.is_dir() or not layer.name[0].isdigit():
            continue
        found = corpus_for(layer.name, lab=lab)
        if not found:
            continue
        (into / f"{layer.name}.md").write_text(f"{found}\n", encoding="utf-8")
        written.append(layer.name)
    return written
