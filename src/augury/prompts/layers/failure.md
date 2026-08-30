What happens when the system is past the knee: queueing delay, retry
amplification, timeout budgets, backpressure and metastable failure.

The governing fact is that queueing delay grows as `1/(1-rho)`, so latency does
not degrade as you approach capacity, it goes vertical. This is the mechanism
behind almost every "it was fine and then it wasn't" incident, and it is why a
capacity plan built on average CPU is wrong.

Specifically look for:

- A concurrency limit somewhere in this file: a pool, a semaphore, a worker
  count. Apply Little's Law with the observed service time and predict `http_req_duration_p99` at a stated arrival rate. Show the arithmetic.
- Retries with no backoff, no jitter or no budget. Retry multiplies load at
  exactly the moment capacity is lowest, and it multiplies across a chain:
  three hops each retrying three times is up to 27x at the leaf. Predict `retry_amplification`.
- Timeouts that are absent, or that are longer than the caller's own deadline,
  so the work continues after nobody is waiting for it.
- Unbounded queues with no shedding: the failure is memory and latency, not an
  error, so nothing pages.
- A cache or a fallback whose failure mode is a stampede onto the thing it was
  protecting.

Prefer one prediction with arithmetic you can show over three you cannot.

- A CPU quota is not a slower CPU, it is a periodic freeze. Eight runnable
  threads drain a 1.0-CPU quota in about 12.5ms of a 100ms period and the
  container is stopped dead for the remaining 87.5ms, at an average utilisation
  that looks fine. More threads spend the budget faster, they do not earn more
  of it. A p99 near a round multiple of 100ms is the fingerprint.
- Throughput flat while goodput collapses is the signature of metastable
  failure. Count responses delivered to a caller that was still waiting.
  Removing the trigger does not end it, because the retry backlog is now the
  sustaining mechanism, and a timeout shorter than **degraded** service time
  converts partial degradation into a 100% failure rate.
- In a fan-out of n, the chance of hitting at least one leg's p99 is
  `1 - (1-p)^n`: 4.9% at n=5, 18.2% at n=20, 63.4% at n=100 when p is 1%. One
  dependency's rare tail is the parent's common case.
- Cancelling the caller does not stop the work. The query already sent keeps
  running until `statement_timeout` kills it, and `SET LOCAL statement_timeout`
  silently does nothing outside a transaction. A client deadline without a
  server-side one gives you the errors without the relief.
- Reject on queue **wait time**, not queue length: the same length is healthy
  for a 1ms handler and catastrophic for a 500ms one. A 503 that still runs
  auth and a database lookup saves nothing.
- Above the pool sit two ceilings nobody watches: uvicorn's `--backlog` of 2048,
  invisible to every application metric, and the anyio thread limiter at 40 per
  process.
- A handler that never checks whether the caller is still there keeps working
  and holding its pool connection after the client has gone. A long endpoint
  should check `await request.is_disconnected()` between stages.
