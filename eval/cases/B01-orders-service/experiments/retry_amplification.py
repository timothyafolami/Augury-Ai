"""How much load a failing gateway receives, per request from the client.

Runs twenty concurrent charges through the case repository's own `charge`
against a gateway that always fails, and counts what arrives.

Twenty clients is the point. An earlier version issued one charge and counted
three arrivals, which measures `MAX_ATTEMPTS` and nothing else: a client with
exponential backoff, full jitter and a retry budget -- the exact remediation
the defect calls for -- also retries three times on its first request, and also
measured three. The defect is not that retries exist. It is that nothing caps
them in aggregate, so the multiplication applies to every client at once at
exactly the moment the dependency has least capacity to absorb it.

A retry budget binds across requests, so it can only be observed across
requests. That is why this experiment sends many.

The last line printed is the measurement, as a multiple of one request.
"""

import asyncio
import os
import sys
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# The repository under measurement. Overridable so the same experiment can be
# run against a remediated copy: an experiment that reports the same number
# either way is not measuring the defect, and tests/test_experiments_
# discriminate.py proves each one does by pointing this at the fixed version.
REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from app.clients import payments  # noqa: E402

CLIENTS = 20

received = 0
_lock = threading.Lock()


class AlwaysFails(BaseHTTPRequestHandler):
    """A dependency having a bad minute."""

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        global received
        with _lock:
            received += 1
        self.send_response(503)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


class Threaded(HTTPServer):
    """One thread per connection, so concurrent clients are actually concurrent.

    The listen backlog is raised well above the client count. At the default
    of five, connections were refused under the burst and the refused ones
    never reached the counter, so the same code measured anywhere between 1.9
    and 2.5 -- a property of the socket queue rather than of the retry policy.
    """

    daemon_threads = True
    request_queue_size = 256

    def process_request(self, request: object, address: object) -> None:
        threading.Thread(
            target=self._handle, args=(request, address), daemon=True
        ).start()

    def _handle(self, request: object, address: object) -> None:
        try:
            self.finish_request(request, address)  # type: ignore[arg-type]
        finally:
            self.shutdown_request(request)  # type: ignore[attr-defined]


async def main() -> None:
    server = Threaded(("127.0.0.1", 0), AlwaysFails)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[0], server.server_address[1]

    payments.GATEWAY_URL = f"http://{host}:{port}/charge"
    print(f"gateway at {payments.GATEWAY_URL}, failing every request")
    print(f"{CLIENTS} concurrent charges")

    async def one(index: int) -> None:
        try:
            await payments.charge(index, Decimal("10.00"), f"idempotency-{index}")
        except Exception:
            return

    await asyncio.gather(*(one(index) for index in range(CLIENTS)))

    # Every in-flight request has been answered by the time gather returns,
    # but the handler threads that increment the counter may not have run yet.
    await asyncio.sleep(0.2)
    server.shutdown()

    print(f"{received} requests reached the gateway for {CLIENTS} client requests:")
    print(received / CLIENTS)


asyncio.run(main())
