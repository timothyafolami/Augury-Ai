"""What a model returns, and the gate that turns it into a finding.

The baseline and the full pipeline emit this same schema and are asked for the
same thing, a prediction included. Anything else would rig the comparison: a
baseline denied the chance to be falsifiable would lose by construction, and
the result would mean nothing.

So the gate lives here and is applied identically to both. A prediction
survives only if it passes the same validation, which means a model that fills
the fields with something unusable -- an inverted band, a dimensionless number
-- gets the finding counted as unfalsifiable, exactly as if it had left them
empty. The finding itself is still shown to the user; only the claim to be
testable is withdrawn, and the reason is recorded.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from augury.core.findings import Dropped, Finding, Report, Severity
from augury.core.schemas import Comparator, Prediction


class DraftPrediction(BaseModel):
    """A prediction as the model states it, before validation.

    Every field is required, because strict structured-output providers demand
    that each declared property also appear in `required` and reject the whole
    response otherwise. Optional means nullable here, never absent.
    """

    model_config = ConfigDict(extra="ignore")

    metric: str
    comparator: Comparator
    value: float
    upper: float | None
    unit: str
    condition: str


class DraftFinding(BaseModel):
    """A finding as the model states it. Every field required, null allowed."""

    model_config = ConfigDict(extra="ignore")

    path: str
    line: int
    layer: str
    symbol: str
    mechanism: str
    severity: Severity
    remediation: str
    arithmetic: str
    prediction: DraftPrediction | None


class DraftReport(BaseModel):
    """One review, as the model states it."""

    model_config = ConfigDict(extra="ignore")

    findings: list[DraftFinding]


def to_report(
    draft: DraftReport,
    *,
    model_id: str = "",
    usd: float = 0.0,
    seconds: float = 0.0,
    locator: Callable[[str, str], int | None] | None = None,
) -> Report:
    """Validate every draft finding, keeping what cannot be proved but saying so.

    `locator` maps (path, symbol) to the line the parser found the definition
    on. A model names the right function and frequently the wrong line -- the
    field run measured one 140 lines out -- so where a parser can confirm the
    location, it wins. Returning None leaves the model's line alone: replacing
    a guess with a different guess is not an improvement.

    Both arms get the same locator, because a correction given to one arm and
    withheld from the other would be a difference in the harness reported as a
    difference in the reviewer.
    """
    findings: list[Finding] = []
    dropped: list[Dropped] = []

    for item in draft.findings:
        prediction, reason = _validate(item.prediction)
        if reason is not None:
            dropped.append(
                Dropped(
                    symbol=item.symbol or "unknown",
                    path=item.path or "unknown",
                    reason=reason,
                )
            )

        path = item.path or "unknown"
        symbol = item.symbol or "unknown"
        located = locator(path, symbol) if locator else None

        findings.append(
            Finding(
                path=path,
                line=located if located is not None else max(item.line, 0),
                layer=item.layer or "unknown",
                symbol=symbol,
                mechanism=item.mechanism or "not stated",
                severity=item.severity,
                remediation=item.remediation or "not stated",
                arithmetic=item.arithmetic,
                prediction=prediction,
            )
        )

    return Report(
        findings=tuple(findings),
        dropped=tuple(dropped),
        model_id=model_id,
        usd=usd,
        seconds=seconds,
    )


def _validate(draft: DraftPrediction | None) -> tuple[Prediction | None, str | None]:
    """A prediction, or None with the reason it could not be one."""
    if draft is None:
        return None, None
    try:
        return Prediction(**draft.model_dump()), None
    except ValidationError as exc:
        return None, why_it_failed(exc)


# What Pydantic puts in front of a message raised by a validator. It names the
# library that noticed, which is not what the reader needs to know.
_LIBRARY_PREFIX = "Value error, "


def why_it_failed(exc: ValidationError) -> str:
    """A rejected prediction's reason, as a sentence rather than a dump.

    A rule about the whole model -- "the upper bound must exceed the lower" --
    has no field to name, so `loc` is empty and joining it produced a leading
    colon with nothing before it. Printed dozens of times on one run.
    """
    said: list[str] = []
    for error in exc.errors():
        message = str(error["msg"])
        if message.startswith(_LIBRARY_PREFIX):
            message = message[len(_LIBRARY_PREFIX) :]
        where = ".".join(str(part) for part in error["loc"])
        said.append(f"{where}: {message}" if where else message)
    return "; ".join(said)
