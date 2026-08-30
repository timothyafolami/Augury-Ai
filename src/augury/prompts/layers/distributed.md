What happens when a message is delivered twice, not at all, or out of order,
and when the answer to "did it work" is genuinely unknown.

The defining problem is the ambiguous result: a call times out and the caller
cannot distinguish "it did not happen" from "it happened and the reply was
lost". Every retry in the system is built on top of that ambiguity, so every
handler a retry can reach has to be safe to run twice.

Specifically look for:

- Handlers that a retry or a redelivery can reach, which are not idempotent:
  they insert, increment, charge, send or append. Predict `duplicate_side_effects` under N redeliveries, and the `final_balance` that follows.
- Idempotency keys that are checked and then written non-atomically, which is
  the same race one level up.
- Side effects performed inside a transaction that commits separately from the
  message acknowledgement, so a crash between the two loses or duplicates work.
  Name which of the two it is.
- Ordering assumed across partitions, consumers or retries where none is
  guaranteed.
- Wall-clock time used to decide ordering, expiry or leadership. Clocks lie,
  and the skew is not bounded by anything you control.
- A lease or a lock with no fencing token, so a delayed holder can still act
  after losing it.

Say precisely what an operator would observe: the duplicate charge, the lost
job, the row that two writers both believe they own.

- Name which exception proves the request never landed. With httpx,
  `ConnectError` and `ConnectTimeout` prove nothing happened and are safe to
  retry; `ReadTimeout`, `WriteTimeout`, `RemoteProtocolError` and `ReadError`
  prove nothing at all. All six subclass `httpx.HTTPError`, so catching the
  parent and retrying converts an ambiguous result into a duplicate charge. In
  Java the safe case is a subclass of the unsafe one.
- The outbox relay: a high-water-mark cursor permanently and silently skips
  rows, because sequences allocate outside the transaction so a lower id can
  commit after a higher one. `NOTIFY` is not durable.
- Last-write-wins on client timestamps discards writes silently, and one NTP
  step poisons a p99 for a whole scrape window. Go strips the monotonic reading
  on `.UTC()`, `.Round()` and JSON marshalling, so a duration can come out
  negative.
- A check of `lease.still_valid()` before a write can never be made safe, only a
  fencing token the resource itself checks. The pause that expires your lease is
  a GC pause, a CFS throttle, or an event loop blocked by one sync call: the
  lease expires because you were working.
- `SELECT` then `INSERT` both see nothing under READ COMMITTED, and
  `ON CONFLICT DO NOTHING RETURNING id` returns **zero rows** on conflict, which
  is the bug. Two-state keys cannot tell in-flight from never-started.
