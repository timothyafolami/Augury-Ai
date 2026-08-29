"""How far the inbox backs up when arrivals outrun the worker.

Offers the case repository's own queue two hundred events while a single
worker drains them at a fixed rate, and reports the backlog after a fixed
window. A queue that pushes back stops accepting and the depth stays at its
bound. An unbounded one absorbs everything, and the backlog is the difference
between what arrived and what was served.

The last line printed is the measurement, as items waiting.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from app.queue import inbox  # noqa: E402

ARRIVALS = 200
SERVICE_SECONDS = 0.002
WINDOW_SECONDS = 0.2


async def main() -> None:
    print(f"{ARRIVALS} events arriving, one worker at {SERVICE_SECONDS:g}s each")

    async def worker() -> None:
        while True:
            await inbox.take()
            await asyncio.sleep(SERVICE_SECONDS)

    draining = asyncio.create_task(worker())

    accepted = 0
    for index in range(ARRIVALS):
        try:
            await asyncio.wait_for(inbox.accept({"id": index}), timeout=0.01)
            accepted += 1
        except (asyncio.TimeoutError, Exception):
            # A queue that pushes back refuses the event, which is the point.
            break

    await asyncio.sleep(WINDOW_SECONDS)
    draining.cancel()

    print(f"{accepted} accepted, backlog after {WINDOW_SECONDS:g}s:")
    print(inbox.depth())


asyncio.run(main())
