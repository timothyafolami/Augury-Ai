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
    assert corpus_for("03-data", lab=tmp_path / "nowhere") == ""


def test_a_missing_lab_does_not_claim_a_source_it_lacks(tmp_path: Path) -> None:
    """An empty corpus must be empty, not a sentence about being empty."""
    assert "lab" not in corpus_for("03-data", lab=tmp_path / "nowhere").lower()


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
