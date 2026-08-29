"""How far the inbox will back up when nothing is draining it.

Offers the case repository's own queue far more events than any sensible bound
and reports what it holds. A bounded queue stops at its bound, whatever that
bound is. An unbounded one holds everything offered.

An earlier version ran a worker against a fixed arrival count in a fixed
window, and reported the arithmetic on those three constants: a queue bounded
at 512 measured exactly the same as an unbounded one, because 512 was above the
backlog the constants produced. It discriminated only against the particular
bound the remediation happened to use, which is overfitting to one's own answer.

Offering more than any bound removes the constants from the result. The number
is the queue's capacity, or the offered count if it has none.

The last line printed is the measurement, as items held.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from app.queue import inbox  # noqa: E402

OFFERED = 5000


async def main() -> None:
    print(f"offering {OFFERED} events with nothing draining them")

    accepted = 0
    for index in range(OFFERED):
        try:
            await asyncio.wait_for(inbox.accept({"id": index}), timeout=0.05)
        except Exception:
            # Any refusal is the queue pushing back, which is the behaviour
            # being looked for. What kind of refusal is not this experiment's
            # business.
            break
        accepted += 1

    print(f"{accepted} accepted before the queue pushed back; it now holds:")
    print(inbox.depth())


asyncio.run(main())
