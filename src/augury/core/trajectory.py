"""Recording what the agents did, as they do it.

The submission has to show what each agent did, how its tools responded, and
what shaped its next step. That is a feature rather than a document: written
afterwards it would be a summary, and a summary is exactly what a reader cannot
check.

Two decisions worth stating. Deterministic steps are recorded alongside model
calls, because two of the agents never call a model and a trace showing only
the calls would misrepresent where the work happens. And retries are recorded
rather than smoothed over, because a run that needed three attempts is a
different run from one that needed none.

Line-delimited JSON so a partial file from an interrupted run is still readable
up to the point it stopped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from augury.core.adapters.base import Usage

# Trajectories are committed and handed to judges, and Augury reads other
# people's repositories. A prompt carrying a reviewed repository's credential
# must not be published along with it.
_SECRETS = re.compile(
    r"""(
        # A private key is matched whole. Matching only the BEGIN line replaced
        # the header and published the body -- strictly worse than no match,
        # because the marker every secret scanner keys on had been removed.
        -----BEGIN[A-Z\ ]*PRIVATE\ KEY-----.*?-----END[A-Z\ ]*PRIVATE\ KEY-----

        # Character classes include _ and -: real keys contain them, and a
        # class without them matched only to the first underscore and then fell
        # short of the length floor, silently publishing the key.
        | gsk_[A-Za-z0-9\-_]{20,}
        | sk-[A-Za-z0-9\-_]{20,}
        | gh[opsu]_[A-Za-z0-9\-_]{20,}
        | github_pat_[A-Za-z0-9\-_]{20,}
        | xox[baprs]-[A-Za-z0-9\-]{10,}
        | AKIA[0-9A-Z]{16}
        | AIza[A-Za-z0-9\-_]{30,}
        | eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}

        # The password inside a connection string. Case B01 is itself a
        # Postgres service, so this is the expected shape in a reviewed file
        # rather than a hypothetical one.
        | (?<=://)[^:@/\s]+:[^@/\s]+(?=@)

        # A secret being assigned. Deliberately broad: this file is committed
        # and handed to judges, so redaction fails closed.
        | (?i:password|secret|passwd|api[_-]?key|access[_-]?token)\s*[=:]\s*\S+

        # An AWS secret access key has no prefix to key on, only its shape.
        | (?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])
    )""",
    re.VERBOSE | re.DOTALL,
)


class Trajectory:
    """An append-only record of one run."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Created immediately: an empty trajectory is evidence too, and says
        # the run did nothing rather than that recording failed.
        self._path.touch()

    def record(self, *, agent: str, action: str, detail: dict[str, Any]) -> None:
        """A step that consulted no model."""
        self._write({"agent": agent, "action": action, "model_call": False, "detail": detail})

    def record_call(
        self,
        *,
        agent: str,
        prompt: str,
        response: Any,
        usage: Usage,
        retries: int,
    ) -> None:
        """A model call, with what was asked and what came back."""
        self._write(
            {
                "agent": agent,
                "action": "model_call",
                "model_call": True,
                "prompt": redact(prompt),
                "response": json.loads(redact(json.dumps(response, default=str))),
                "usage": usage.model_dump(),
                "retries": retries,
            }
        )

    def _write(self, step: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(step, default=str) + "\n")


def redact(text: str) -> str:
    """Replace anything shaped like a credential."""
    return _SECRETS.sub("REDACTED", text)
