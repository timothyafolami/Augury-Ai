"""What share of workers a single slow provider holds.

Runs the case repository's own `quote` from four concurrent workers against a
shipping provider that accepts the connection and never answers, then asks how
many are still blocked once a reasonable deadline has passed.

A call with a deadline releases its worker and the service keeps serving on
what is left. A call without one holds its worker for as long as the provider
cares to hold the socket, so one slow dependency takes the whole service down
while every dashboard reports it healthy.

The last line printed is the measurement, as a share of workers from 0 to 1.
"""

import asyncio
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "repo"))

from app.clients import shipping  # noqa: E402

WORKERS = 4
DEADLINE_SECONDS = 3.0

_keep_open: list[socket.socket] = []


def silent_server() -> int:
    """Accepts connections and answers none of them."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(WORKERS * 2)

    def accept_forever() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            # Held open deliberately: closing would look like a fast failure.
            _keep_open.append(connection)

    threading.Thread(target=accept_forever, daemon=True).start()
    return int(listener.getsockname()[1])


async def main() -> None:
    port = silent_server()
    shipping.RATES_URL = f"http://127.0.0.1:{port}/rates"
    print(f"provider at {shipping.RATES_URL}, accepting and never answering")
    print(f"{WORKERS} workers, {DEADLINE_SECONDS:g}s deadline")

    tasks = [
        asyncio.create_task(shipping.quote("SW1A 1AA", 500)) for _ in range(WORKERS)
    ]
    done, pending = await asyncio.wait(tasks, timeout=DEADLINE_SECONDS)

    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    blocked = len(pending)
    print(f"{blocked} of {WORKERS} workers still held after the deadline:")
    print(blocked / WORKERS)


asyncio.run(main())
