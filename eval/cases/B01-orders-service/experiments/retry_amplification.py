"""How many requests one payment reaches the gateway with when it is failing.

Runs the case repository's own `charge` against a local server that always
fails, and counts the requests that arrive. One client request should reach the
dependency once. Retries multiply that at exactly the moment the dependency has
least capacity, and the multiplication compounds across a chain of hops.

Nothing simulates the retry: the loop under measurement is the loop under
review, and the count is taken at the server that receives them.

The last line printed is the measurement, as a multiple of one request.
"""

import asyncio
import sys
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "repo"))

from app.clients import payments  # noqa: E402

received = 0


class AlwaysFails(BaseHTTPRequestHandler):
    """A dependency having a bad minute."""

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        global received
        received += 1
        self.send_response(503)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


async def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), AlwaysFails)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[0], server.server_address[1]

    payments.GATEWAY_URL = f"http://{host}:{port}/charge"
    print(f"gateway at {payments.GATEWAY_URL}, failing every request")

    try:
        await payments.charge(1, Decimal("10.00"), "idempotency-key-1")
    except Exception as error:
        print(f"charge gave up: {type(error).__name__}")

    server.shutdown()

    print("requests reaching the gateway for one client request:")
    print(received)


asyncio.run(main())
