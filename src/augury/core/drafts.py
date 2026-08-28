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

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from augury.core.findings import Dropped, Finding, Report, Severity
from augury.core.schemas import Comparator, Prediction


class DraftPrediction(BaseModel):
    """A prediction as the model states it, before validation."""

    model_config = ConfigDict(extra="ignore")

    metric: str = ""
    comparator: Comparator = Comparator.AT_LEAST
    value: float = 0.0
    upper: float | None = None
    unit: str = ""
    condition: str = ""


class DraftFinding(BaseModel):
    """A finding as the model states it."""

    model_config = ConfigDict(extra="ignore")

    path: str = ""
    line: int = 0
    layer: str = "unknown"
    symbol: str = "unknown"
    mechanism: str = ""
    severity: Severity = Severity.MEDIUM
    remediation: str = ""
    arithmetic: str = ""
    prediction: DraftPrediction | None = None


class DraftReport(BaseModel):
    """One review, as the model states it."""

    model_config = ConfigDict(extra="ignore")

    findings: list[DraftFinding] = Field(default_factory=list)


def to_report(
    draft: DraftReport,
    *,
    model_id: str = "",
    usd: float = 0.0,
    seconds: float = 0.0,
) -> Report:
    """Validate every draft finding, keeping what cannot be proved but saying so."""
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

        findings.append(
            Finding(
                path=item.path or "unknown",
                line=max(item.line, 0),
                layer=item.layer or "unknown",
                symbol=item.symbol or "unknown",
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
        return None, "; ".join(
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
