What happens when the system is past the knee: queueing delay, retry
amplification, timeout budgets, backpressure and metastable failure.

The governing fact is that queueing delay grows as `1/(1-rho)`, so latency does
not degrade as you approach capacity, it goes vertical. This is the mechanism
behind almost every "it was fine and then it wasn't" incident, and it is why a
capacity plan built on average CPU is wrong.

Specifically look for:

- A concurrency limit somewhere in this file: a pool, a semaphore, a worker
  count. Apply Little's Law with the observed service time and predict the
  arrival rate at which p99 crosses a threshold. Show the arithmetic.
- Retries with no backoff, no jitter or no budget. Retry multiplies load at
  exactly the moment capacity is lowest, and it multiplies across a chain:
  three hops each retrying three times is up to 27x at the leaf. Predict the
  amplification factor.
- Timeouts that are absent, or that are longer than the caller's own deadline,
  so the work continues after nobody is waiting for it.
- Unbounded queues with no shedding: the failure is memory and latency, not an
  error, so nothing pages.
- A cache or a fallback whose failure mode is a stampede onto the thing it was
  protecting.

Prefer one prediction with arithmetic you can show over three you cannot.
