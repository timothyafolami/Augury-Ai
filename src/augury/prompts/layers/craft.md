Whether the interfaces in this file let a caller do the right thing, and
whether a failure can pass for a success.

The highest-severity finding in this concern is the silent one, because it does
not page anyone. A swallowed exception in a data access path turns a broken
database into a fast, successful, empty response: dashboards go green, latency
improves, and users see nothing. That is worth more attention than any amount
of naming or structure.

Specifically look for:

- Broad exception handlers that return a default, an empty collection or None.
  For each, say what the caller now believes and predict `http_status` when the
  dependency is down, and the `http_req_duration_p99` the caller waits.
- Errors that are logged and then swallowed, which is the same defect with a
  paper trail nobody reads.
- Functions whose failure mode is not expressible in their return type, so the
  caller cannot distinguish empty from broken.
- Shallow modules: an interface nearly as complex as its implementation, which
  costs the reader more than it saves.
- Abstractions that leak the thing they exist to hide, so callers must know
  both sides.
- Tests that assert on a mock rather than on behaviour, and therefore pass when
  the real dependency changes shape.

Prefer one finding about a failure that can pass for a success over five about
structure. The first is an outage; the second is an opinion.
