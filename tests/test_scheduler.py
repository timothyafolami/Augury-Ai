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


def test_reports_what_the_budget_stopped_it_reading() -> None:
    """Silent truncation reads as 'we covered everything'. Every unread file
    is reported, with the reason it was not read."""
    plan = Scheduler(
        repo(module("a.py", fan_in=5), module("b.py", fan_in=1)),
        budget=Budget(usd=0.01),
    )

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.next()

    assert plan.coverage.skipped == {"b.py": "budget"}
    assert plan.coverage.stopped_because == "budget exhausted"


def test_modules_with_no_signal_are_reported_as_skipped_not_omitted() -> None:
    """'No signal' can mean 'the mapper missed it'. A consumer seeing
    analysed=[a.py] and skipped={} would conclude the repo was fully covered."""
    plan = Scheduler(repo(module("a.py"), module("constants.py", signals=frozenset())))

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.next()

    assert plan.coverage.skipped == {"constants.py": "no signal"}
    assert plan.coverage.stopped_because == "nothing left worth reading"


def test_files_that_failed_to_parse_are_reported_as_skipped() -> None:
    unreadable = RepoMap(root="/tmp/repo", modules=[module("a.py")], unparsed=["broken.py"])
    plan = Scheduler(unreadable)

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.next()

    assert plan.coverage.skipped == {"broken.py": "unparsed"}


def test_spend_never_exceeds_the_budget_through_float_drift() -> None:
    """Ten cents of one-cent reads sums to 0.09999999999999999, which is less
    than 0.10, which buys an eleventh read that was not paid for."""
    plan = Scheduler(repo(*(module(f"m{i}.py") for i in range(20))), budget=Budget(usd=0.10))

    reads = 0
    while (chosen := plan.next()) is not None:
        plan.record(chosen, findings=0, spent_usd=0.01)
        reads += 1

    assert reads == 10


def test_a_module_too_expensive_for_the_remaining_budget_is_not_issued() -> None:
    """A ceiling that is only checked after the money is gone is not a ceiling."""
    plan = Scheduler(
        repo(module("huge.py", loc=500_000)),
        budget=Budget(usd=0.01, usd_per_1k_loc=1.0),
    )

    assert plan.next() is None
    assert plan.coverage.stopped_because == "nothing left fits the remaining budget"


def test_recording_the_same_module_twice_does_not_double_count() -> None:
    plan = Scheduler(repo(module("a.py")))
    chosen = take(plan)

    plan.record(chosen, findings=0, spent_usd=0.01)
    plan.record(chosen, findings=0, spent_usd=0.01)

    assert plan.coverage.analysed == ["a.py"]


def test_coverage_is_honest_even_when_the_caller_stops_early() -> None:
    """Coverage was only computed on the exit path inside next(), so a caller
    that stopped for any other reason -- a wall-clock cap, a 429, an exception
    in the fan-out -- published an empty skip list that reads as full
    coverage. That is exactly when it was least true."""
    plan = Scheduler(repo(module("a.py"), module("b.py"), module("c.py")))

    read = take(plan)
    plan.record(read, findings=0, spent_usd=0.01)

    assert plan.coverage.analysed == [read.path]
    assert set(plan.coverage.skipped) == {"a.py", "b.py", "c.py"} - {read.path}
    assert plan.coverage.stopped_because == "still running"


def test_an_unmatched_module_is_not_reported_as_having_no_signal() -> None:
    """Skipping because our table did not recognise an import is a fact about
    us, not about the code."""
    unrecognised = module(
        "exotic.py", signals=frozenset(), unmatched_imports=frozenset({"weird_lib"})
    )
    plan = Scheduler(repo(module("a.py"), unrecognised))

    plan.record(take(plan), findings=0, spent_usd=0.01)
    plan.next()

    assert plan.coverage.skipped["exotic.py"] == "no detector matched its imports"
