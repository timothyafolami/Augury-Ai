"""The Scheduler decides what gets read, and therefore what gets found.

A codebase does not fit in a context window, so the reviewer cannot read
everything. It must repeatedly choose the next module that is worth its cost,
and stop when nothing left is. These tests pin that judgement.
"""

from augury.core.cartography import ModuleNode, RepoMap, Signal
from augury.core.scheduling import Budget, Scheduler


def module(path: str, **kwargs: object) -> ModuleNode:
    defaults: dict[str, object] = {
        "loc": 50,
        "signals": frozenset({Signal.DATA}),
        "fan_in": 0,
        "churn": 0,
        "imports": frozenset(),
    }
    return ModuleNode(path=path, **{**defaults, **kwargs})  # type: ignore[arg-type]


def repo(*modules: ModuleNode) -> RepoMap:
    return RepoMap(root="/tmp/repo", modules=list(modules))


def take(plan: Scheduler) -> ModuleNode:
    """Next module, asserting the review is not over.

    `Scheduler.next` is deliberately Optional: "nothing left worth reading" is
    a real answer. Tests that expect a module say so here rather than everywhere.
    """
    module = plan.next()
    assert module is not None, "expected the scheduler to have work left"
    return module


def test_selects_the_most_depended_upon_module_first() -> None:
    """Fan-in is blast radius: a defect in a module twenty others import is
    worth finding before one in a leaf."""
    plan = Scheduler(repo(module("leaf.py", fan_in=0), module("core.py", fan_in=20)))

    assert take(plan).path == "core.py"


def test_never_selects_the_same_module_twice() -> None:
    plan = Scheduler(repo(module("a.py", fan_in=5), module("b.py", fan_in=1)))

    first = take(plan)
    plan.record(first, findings=0, spent_usd=0.01)
    second = take(plan)

    assert first.path != second.path


def test_never_selects_a_module_with_nothing_to_analyse() -> None:
    """No signal means no specialist has anything to say. Reading it anyway
    is spend with a known-zero expected return."""
    plan = Scheduler(repo(module("constants.py", signals=frozenset(), fan_in=99)))

    assert plan.next() is None


def test_stops_when_the_budget_is_spent() -> None:
    plan = Scheduler(
        repo(module("a.py", fan_in=5), module("b.py", fan_in=4)),
        budget=Budget(usd=0.05),
    )

    plan.record(take(plan), findings=1, spent_usd=0.05)

    assert plan.next() is None


def test_a_finding_raises_the_priority_of_modules_that_import_it() -> None:
    """Defects travel along the import graph. A caller of broken code is a
    better next read than an unrelated module of the same size."""
    caller = module("caller.py", imports=frozenset({"broken.py"}), fan_in=0)
    unrelated = module("unrelated.py", fan_in=1)
    plan = Scheduler(repo(module("broken.py", fan_in=2), caller, unrelated))

    plan.record(take(plan), findings=3, spent_usd=0.01)

    assert take(plan).path == "caller.py"


def test_exhausting_every_candidate_ends_the_review() -> None:
    plan = Scheduler(repo(module("a.py"), module("b.py")))

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.record(take(plan), findings=0, spent_usd=0.01)

    assert plan.next() is None


def test_reports_what_it_chose_not_to_read() -> None:
    """Silent truncation reads as 'we covered everything'. Coverage must be
    reportable, so a skipped module is recorded with a reason."""
    plan = Scheduler(
        repo(module("a.py", fan_in=5), module("b.py", fan_in=1)),
        budget=Budget(usd=0.01),
    )

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.next()

    assert plan.coverage.skipped == ["b.py"]
    assert plan.coverage.reason == "budget exhausted"
