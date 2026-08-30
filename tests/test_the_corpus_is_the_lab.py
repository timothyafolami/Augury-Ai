"""The analyst was handed its own brief twice and told to cite it.

`corpus=layer.brief` alongside `layer_brief=layer.brief` meant the section
headed "These come from a practice lab written before this review existed, and
they are the source of your authority. Cite them" contained the same twenty-four
lines the specialist already had. So the specialist had a brief and no corpus,
and was invited to attribute the brief to a lab it had never seen.

The lab is a separate repository, so this has to work when it is absent: a
judge cloning only Augury must get a review, and a prompt that does not claim
to cite what it was not given.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.corpus import LAB_ENV, corpus_for

LAB = Path("/Users/apple/Downloads/software-engineering-practice")


def test_a_missing_lab_is_not_an_error(tmp_path: Path) -> None:
    """It yields the committed extract, which is the ordinary case.

    The lab is a separate repository and most readers will not have it, so a
    missing one is not a degraded state: it is what happens for everybody
    except the two machines the lab lives on.
    """
    assert corpus_for("03-data", lab=tmp_path / "nowhere") != ""


def test_neither_a_lab_nor_an_extract_is_empty_rather_than_a_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty corpus must be empty, not a sentence about being empty: a
    corpus explaining its own absence is still read on every call."""
    monkeypatch.setattr("augury.core.corpus.EXTRACT", tmp_path / "no-extract")

    assert corpus_for("03-data", lab=tmp_path / "nowhere") == ""


@pytest.mark.skipif(not LAB.is_dir(), reason="the practice lab is a separate repository")
def test_it_carries_the_mechanism_from_the_layer_it_owns() -> None:
    found = corpus_for("03-data", lab=LAB)

    assert "xmin horizon" in found, "the mechanism this layer is known for"


@pytest.mark.skipif(not LAB.is_dir(), reason="the practice lab is a separate repository")
def test_it_is_not_simply_the_brief_again() -> None:
    from augury.core.layers import LAYERS

    data = next(layer for layer in LAYERS if layer.lab_layer == "03-data")

    assert corpus_for("03-data", lab=LAB) != data.brief


@pytest.mark.skipif(not LAB.is_dir(), reason="the practice lab is a separate repository")
def test_it_is_bounded_because_it_is_sent_on_every_call() -> None:
    """A whole layer is tens of thousands of tokens, once per module per
    specialist. The cap is the difference between a corpus and a bill."""
    from augury.core.corpus import MOST_CHARS

    for layer in ("01-machine", "03-data", "07-security"):
        assert len(corpus_for(layer, lab=LAB)) <= MOST_CHARS


@pytest.mark.skipif(not LAB.is_dir(), reason="the practice lab is a separate repository")
def test_it_is_the_same_every_run() -> None:
    """A corpus that varies is a cassette that never replays."""
    assert corpus_for("05-failure", lab=LAB) == corpus_for("05-failure", lab=LAB)


@pytest.mark.skipif(not LAB.is_dir(), reason="the practice lab is a separate repository")
def test_it_names_the_topic_each_mechanism_came_from() -> None:
    """ "Cite them" is only possible if the citation is in the text."""
    found = corpus_for("03-data", lab=LAB)

    assert "02-mvcc-and-vacuum" in found


def test_a_layer_nobody_owns_is_empty_rather_than_everything(tmp_path: Path) -> None:
    (tmp_path / "03-data").mkdir()
    assert corpus_for("99-nothing", lab=tmp_path) == ""


def test_the_lab_can_be_pointed_at_by_the_environment() -> None:
    """A judge who has both repositories should not have to move either."""
    assert LAB_ENV == "AUGURY_LAB"


def test_the_corpus_ships_with_the_repository() -> None:
    """A clean clone must reproduce the published numbers, and the corpus is
    in the prompt, so it is in every cassette key.

    Found by cloning: the lab is a separate repository, the loader looked for
    it beside the checkout, and a judge holding only Augury got an empty
    corpus, a different prompt and a miss on every cassette. The published
    table then could not be reproduced by the one person it was published for.

    So the extract is committed. The lab remains the source; this is what
    ships.
    """
    from augury.core.corpus import EXTRACT

    assert EXTRACT.is_dir(), "the committed corpus is missing"
    assert list(EXTRACT.glob("*.md")), "the committed corpus is empty"


def test_the_committed_extract_is_preferred_over_a_lab_that_may_not_exist() -> None:
    """Deterministic wherever it runs, or a cassette recorded on the machine
    that has the lab replays nowhere else."""
    from augury.core.corpus import corpus_for

    assert corpus_for("03-data", lab=Path("/nonexistent")) != ""


def test_every_wired_layer_has_a_committed_extract() -> None:
    """A layer whose extract is missing silently loses its corpus, and the
    specialist is told to cite material it was not given."""
    from augury.core.corpus import EXTRACT
    from augury.core.layers import LAYERS

    for layer in LAYERS:
        assert (EXTRACT / f"{layer.lab_layer}.md").is_file(), layer.lab_layer


def test_the_extract_wins_over_a_lab_that_says_something_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two machines must build the same prompt from the same commit.

    `corpus_for` preferred a lab checkout sitting beside the repository and
    fell back to the committed extract. The texts match today, so nothing
    showed; the day the lab is edited, every prompt recorded on a machine
    that has it stops replaying on every machine that does not. That is the
    memo-shadow defect one layer up, and it is cheaper to remove than to
    detect. The lab is read when a caller names it, which is how the extract
    is regenerated, and never implicitly.
    """
    from augury.core.corpus import EXTRACT, corpus_for

    topic = tmp_path / "lab" / "03-data" / "01-topic"
    topic.mkdir(parents=True)
    (topic / "README.md").write_text(
        "**The one idea:** a different lab entirely.\n\n"
        "**Why it matters in practice:** it must not reach a prompt.\n\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUGURY_LAB", str(tmp_path / "lab"))

    assert corpus_for("03-data") == (EXTRACT / "03-data.md").read_text(encoding="utf-8").strip()


def test_naming_the_lab_still_reads_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Which is how `extract_from` regenerates the committed copy."""
    from augury.core.corpus import corpus_for

    topic = tmp_path / "lab" / "03-data" / "01-topic"
    topic.mkdir(parents=True)
    (topic / "README.md").write_text(
        "**The one idea:** a different lab entirely.\n\n"
        "**Why it matters in practice:** it must not reach a prompt.\n\n",
        encoding="utf-8",
    )

    assert "a different lab entirely" in corpus_for("03-data", lab=tmp_path / "lab")
