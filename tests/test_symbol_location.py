"""Where a symbol is actually defined, according to the parser.

The field run in docs/FIELD_RUN.md found that findings name the right function
and the wrong line: `has_extension` was reported at 285 and is at 425. The model
is good at saying *what* it is talking about and bad at saying *where*, which is
a reason to stop asking it. The parser already knows.

All six languages are covered because a locator that only works for Python
would quietly leave five languages reporting the model's guess.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages import Language
from augury.core.cartography.symbols import locate

CASES: list[tuple[Language, str, str, int]] = [
    (
        Language.PYTHON,
        "import os\n\n\ndef first():\n    pass\n\n\ndef wanted(a, b):\n    return a\n",
        "wanted",
        8,
    ),
    (
        Language.GO,
        'package main\n\nimport "fmt"\n\n'
        "func first() {}\n\nfunc wanted(a int) int {\n\treturn a\n}\n",
        "wanted",
        7,
    ),
    (
        Language.RUST,
        "use std::io;\n\nfn first() {}\n\nfn wanted(a: i32) -> i32 {\n    a\n}\n",
        "wanted",
        5,
    ),
    (
        Language.JAVA,
        "class C {\n    void first() {}\n\n    int wanted(int a) {\n        return a;\n    }\n}\n",
        "wanted",
        4,
    ),
    (
        Language.CPP,
        "#include <cstdio>\n\nvoid first() {}\n\nint wanted(int a) {\n    return a;\n}\n",
        "wanted",
        5,
    ),
    (
        Language.TYPESCRIPT,
        "import x from 'y';\n\nfunction first() {}\n\n"
        "function wanted(a: number) {\n  return a;\n}\n",
        "wanted",
        5,
    ),
]


@pytest.mark.parametrize(("language", "source", "symbol", "line"), CASES)
def test_a_definition_is_found_at_its_real_line(
    language: Language, source: str, symbol: str, line: int
) -> None:
    assert locate(source, symbol, language) == line


def test_a_symbol_that_is_not_defined_here_returns_none() -> None:
    # None means "the parser could not confirm it", which must leave the
    # model's guess alone rather than replace it with a wrong number.
    assert locate("def other():\n    pass\n", "wanted", Language.PYTHON) is None


def test_a_call_is_not_mistaken_for_a_definition() -> None:
    source = "def other():\n    wanted()\n\n\ndef wanted():\n    pass\n"
    assert locate(source, "wanted", Language.PYTHON) == 5


def test_a_class_counts_as_a_definition() -> None:
    source = "import os\n\n\nclass Wanted:\n    pass\n"
    assert locate(source, "Wanted", Language.PYTHON) == 4


def test_a_method_inside_a_class_is_found() -> None:
    source = "class C:\n    def first(self):\n        pass\n\n    def wanted(self):\n        pass\n"
    assert locate(source, "wanted", Language.PYTHON) == 5


def test_a_dotted_symbol_matches_on_its_last_segment() -> None:
    # Specialists sometimes name a method as `Class.method`.
    source = "class C:\n    def wanted(self):\n        pass\n"
    assert locate(source, "C.wanted", Language.PYTHON) == 2


def test_unparsable_source_returns_none_rather_than_raising() -> None:
    assert locate("def (((", "wanted", Language.PYTHON) is None


# -- wiring ----------------------------------------------------------------


def test_to_report_takes_the_line_from_the_locator_not_the_model() -> None:
    """The correction, end to end through the object a report is made of."""
    from augury.core.drafts import DraftFinding, DraftReport, to_report
    from augury.core.findings import Severity

    draft = DraftReport(
        findings=[
            DraftFinding(
                path="svc/pool.py",
                line=285,  # what the model said
                layer="data",
                symbol="has_extension",
                mechanism="Swallows the reason the extension is missing.",
                severity=Severity.HIGH,
                remediation="Let the error propagate.",
                arithmetic="",
                prediction=None,
            )
        ]
    )
    report = to_report(
        draft, locator=lambda path, symbol: 425 if symbol == "has_extension" else None
    )
    assert report.findings[0].line == 425


def test_a_symbol_the_locator_cannot_place_keeps_the_model_s_line() -> None:
    from augury.core.drafts import DraftFinding, DraftReport, to_report
    from augury.core.findings import Severity

    draft = DraftReport(
        findings=[
            DraftFinding(
                path="svc/pool.py",
                line=12,
                layer="data",
                symbol="anonymous_lambda",
                mechanism="Something.",
                severity=Severity.LOW,
                remediation="Something else.",
                arithmetic="",
                prediction=None,
            )
        ]
    )
    report = to_report(draft, locator=lambda path, symbol: None)
    assert report.findings[0].line == 12


def test_a_locator_over_a_checkout_resolves_across_languages(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from augury.core.cartography.symbols import locator_for

    (tmp_path / "a.py").write_text("import os\n\n\ndef wanted():\n    pass\n")
    (tmp_path / "b.go").write_text('package m\n\nimport "fmt"\n\nfunc wanted() {}\n')
    locate_in = locator_for(tmp_path)

    assert locate_in("a.py", "wanted") == 4
    assert locate_in("b.go", "wanted") == 5
    assert locate_in("missing.py", "wanted") is None
    assert locate_in("a.txt", "wanted") is None
