"""A document about a service, rather than a list of lines.

On a repository of a few hundred modules a findings table is the wrong
artefact: nobody triages a hundred and thirty-nine rows. What a team acts on is
a document that says what the service is, what its deployment declares, what
its schema and dependencies say, which defects were found, and -- the part most
reports leave out -- how much was never looked at.

Every coverage sentence here is arithmetic. A report that implies it read a
repository it sampled is worse than no report at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from augury.core.findings import Finding, Report
from augury.core.schema.model import SchemaFinding
from augury.core.schemas import Comparator, Prediction
from augury.core.survey.model import Survey

# How many code findings the document lists in full. They arrive ranked, so
# this is the head rather than a sample, and the count of the rest is stated.
LISTED = 20


def write_report(
    *,
    name: str,
    survey: Survey,
    report: Report,
    schema: tuple[SchemaFinding, ...],
    dependencies: tuple[SchemaFinding, ...],
    deployment: tuple[SchemaFinding, ...] = (),
    synthesis: Sequence[Any] = (),
    modules: int,
    unreachable: int,
    reading: dict[str, tuple[str, ...]] | None = None,
) -> str:
    """The whole document, as markdown."""
    parts = [
        _heading(name),
        _what_it_is(survey, modules, unreachable),
        _coverage(report, modules),
        # First of the findings, because they are about the thing that runs
        # rather than the thing that was written, and on a real backend they
        # outnumber the code findings by an order of magnitude. Omitted
        # entirely when empty: a heading over an empty section reads as a
        # section that found nothing, which is not what a section that never
        # ran should look like.
        _section("Deployment", deployment, "") if deployment else "",
        _section(
            "Schema",
            schema,
            "No schema findings: the migrations declare nothing "
            "this checks that a populated table would not survive.",
        ),
        _section(
            "Dependencies",
            dependencies,
            "No dependency findings: nothing declared "
            "is a major version behind what the registry ships, and nothing is unpinned.",
        ),
        _reading(reading or {}),
        _code(report),
        _synthesis(synthesis),
        _withdrawn(report),
        _limits(report),
    ]
    return "\n\n".join(part for part in parts if part)


def _heading(name: str) -> str:
    return (
        f"# {name}\n\n"
        "An engineering review. Everything below is read from the repository or "
        "measured against it; nothing is inferred from what the project claims "
        "about itself."
    )


def _what_it_is(survey: Survey, modules: int, unreachable: int) -> str:
    lines = ["## What this service is", ""]
    if survey.services:
        lines.append("| service | built from | ports | command |")
        lines.append("|---|---|---|---|")
        for service in survey.services:
            command = service.command or "-"
            lines.append(
                f"| `{service.name}` | `{service.source_root or '.'}` | "
                f"{', '.join(service.ports) or '-'} | `{command}` |"
            )
        lines.append("")
    if survey.backing:
        lines.append("It depends on things it did not write:")
        lines.append("")
        for item in survey.backing:
            lines.append(f"- **{item.name}** — {item.kind} (`{item.image}`)")
        lines.append("")

    reachable = modules - unreachable
    lines.append(
        f"{modules} modules. {reachable} are reachable from an entrypoint; "
        f"{unreachable} are not, which usually means migrations, tests and scripts."
    )
    return "\n".join(lines)


def _coverage(report: Report, modules: int) -> str:
    analysed = len(report.coverage.analysed) if report.coverage else 0
    stopped = report.coverage.stopped_because if report.coverage else "unknown"
    share = (100.0 * analysed / modules) if modules else 0.0
    return (
        "## What was actually read\n\n"
        # One decimal, and never rounded up: 249 of 250 rendered as (100%),
        # which is the one number this document must not overstate.
        f"This review **read {analysed} of {modules} modules** ({share:.1f}%), "
        f"spent ${report.usd:.4f}, and stopped because {stopped}.\n\n"
        "The modules were chosen by distance from an entrypoint and by how much "
        "depends on them, so this is the part of the service a request touches "
        "first rather than an arbitrary sample. It is still not the whole "
        "repository, and nothing below should be read as a clean bill of health "
        "for the part that was not read."
    )


def _reading(notes: dict[str, tuple[str, ...]]) -> str:
    """Where to read about the version gaps, quoted and attributed.

    Never asserted. The reviewer has not read these changelogs; it has found
    where they are, and search is the least trustworthy input here -- a version
    number is a fact, a snippet is somebody's prose about one.
    """
    if not notes:
        return ""
    lines = ["## Before you upgrade", ""]
    lines.append(
        "Links only. Nothing below has been read or verified by this review, "
        "and none of it is a finding about your code."
    )
    lines.append("")
    for package, urls in sorted(notes.items()):
        lines.append(f"**{package}**")
        lines.append("")
        for url in urls:
            lines.append(f"- {url}")
        lines.append("")
    return "\n".join(lines)


def _section(title: str, findings: tuple[SchemaFinding, ...], empty: str) -> str:
    if not findings:
        return f"## {title}\n\n{empty}"
    lines = [f"## {title}", ""]
    for finding in findings:
        lines.append(f"**`{finding.rule}`** — `{finding.path}:{finding.line}`")
        lines.append("")
        lines.append(f"{finding.detail}.")
        lines.append("")
        lines.append(f"*Fix:* {finding.remediation}.")
        lines.append("")
    return "\n".join(lines)


def _code(report: Report) -> str:
    if not report.findings:
        return "## Code\n\nNo code findings in the modules that were read."

    lines = ["## Code", ""]
    lines.append(
        "Ordered by evidence: a finding carrying a claim an experiment could "
        "settle outranks one that does not, and a module a request reaches "
        "outranks one further away. The severity beside each is the reviewer's "
        "own word for it and is the weakest signal here."
    )
    lines.append("")
    for position, finding in enumerate(report.findings[:LISTED], start=1):
        lines.append(f"### {position}. `{finding.symbol}` — `{finding.path}:{finding.line}`")
        lines.append("")
        lines.append(f"*{finding.layer}, {finding.severity.value}*")
        lines.append("")
        lines.append(finding.mechanism)
        lines.append("")
        if finding.prediction is not None:
            lines.append(f"**Testable claim:** {claim_of(finding.prediction)}")
            lines.append("")
        if finding.measurement is not None:
            # The document rendered none of this, and then closed by saying
            # nothing had been executed -- so a refuted claim was published as
            # an open one.
            lines.append(settled_as(finding))
            lines.append("")
        lines.append(f"*Fix:* {finding.remediation}")
        lines.append("")

    hidden = len(report.findings) - min(LISTED, len(report.findings))
    if hidden:
        lines.append(f"{hidden} further findings rank below these.")
    return "\n".join(lines)


def claim_of(prediction: Prediction) -> str:
    """A prediction as something a reader can check.

    Both bounds of a band. Printing only the lower one published "between
    250ms", which is not the claim that was scored and cannot be checked
    against anything -- the one property every claim here is meant to have.
    """
    bound = f"{prediction.value:g}"
    if prediction.comparator is Comparator.BETWEEN and prediction.upper is not None:
        bound = f"{prediction.value:g} and {prediction.upper:g}"
    return (
        f"`{prediction.metric} {prediction.comparator.value} {bound}{prediction.unit}` "
        f"under `{prediction.condition}`."
    )


def settled_as(finding: Finding) -> str:
    """What the experiment measured, and what that made of the claim."""
    measured = finding.measurement
    if measured is None:
        return ""
    if measured.value is None:
        return f"**Experiment:** ran and measured nothing — {measured.detail}"
    verdict = finding.prediction.score(measured.value) if finding.prediction else None
    said = f"{verdict.value}" if verdict is not None else "measured"
    return (
        f"**Measured:** {measured.value:g}{_unit_of(finding)} — **{said}**. "
        f"The experiment is at `{measured.experiment}`."
    )


def _unit_of(finding: Finding) -> str:
    return finding.prediction.unit if finding.prediction else ""


def _synthesis(observations: Sequence[Any]) -> str:
    """What no single specialist could have said.

    Empty when nothing connected, and silent about it: an empty synthesis is
    the correct answer for a report whose findings do not connect, and a
    heading announcing that is a paragraph nobody needed.
    """
    if not observations:
        return ""

    lines = [
        "## Read together",
        "",
        "Each of these connects findings from more than one specialist. The "
        "specialists never see each other's output, so none of them could have "
        "written any of this alone.",
        "",
    ]
    for item in observations:
        lines.append(f"**{item.mechanism}**")
        lines.append("")
        lines.append(str(item.consequence))
        lines.append("")
        for cite in item.citations:
            lines.append(f"- `{cite.symbol}` — `{cite.path}:{cite.line}` ({cite.layer})")
        lines.append("")
    return "\n".join(lines).rstrip()


def _withdrawn(report: Report) -> str:
    """The claims that were withdrawn, which the limits section promises.

    It asserted "the reasons are recorded rather than the findings quietly
    deleted" and showed none of them, so for this document's reader the
    withdrawal was exactly as quiet as the sentence denies.
    """
    if not report.dropped:
        return ""
    lines = [
        "## Withdrawn",
        "",
        "Claims this review made and then took back, with the reason. They are "
        "here because a reviewer that deletes its own output is one nobody can "
        "audit.",
        "",
    ]
    lines.extend(f"- `{entry.symbol}` — {entry.reason}" for entry in report.dropped)
    return "\n".join(lines)


def _limits(report: Report) -> str:
    measured = any(f.measurement is not None for f in report.findings)
    executed = (
        "- Every claim above that carries a measurement was executed; the rest "
        "are predictions, not observations."
        if measured
        else "- Nothing here was executed. A defect that only appears under load is "
        "predicted, not observed."
    )
    return (
        "## What this review cannot tell you\n\n"
        "- It read a fraction of the repository, named above.\n"
        "- A finding is a claim about the code, not a measurement of it. The "
        "ones carrying a testable claim say what would settle them; the rest "
        "are worth the time it takes to check them and no more.\n"
        "- Claims the repository itself disproves have been withdrawn, and the "
        "reasons are recorded rather than the findings quietly deleted.\n"
        f"{executed}"
    )
