Shared mutable state, atomicity, and what the runtime does or does not do for
you. The lab's point is that the same idea looks different in every language,
so read for what this runtime actually guarantees rather than for a pattern.

Shared state touched by more than one thread without synchronisation does not
reliably fail. It corrupts silently, sometimes, in a way that "it worked when I
tested it" gives you zero evidence against. That is why this concern needs a
differential experiment rather than a load test: run the operation a known
number of times concurrently and compare the final state to the arithmetic.

Specifically look for:

- Read-modify-write on state reachable from more than one task, thread or
  request: counters, caches, accumulators, dictionaries keyed by request.
  Predict the final value after N concurrent operations versus the correct N.
- Check-then-act: `if key not in cache` followed by a write, `if not exists`
  followed by create. Predict the duplicate rate.
- Lock ordering that differs between two paths, which is a deadlock.
- `async` functions performing blocking work, which stalls the whole loop.
  Predict the effect on p99 for unrelated requests.
- Assumptions the runtime does not honour: the GIL does not make `+=` atomic,
  a single-threaded event loop does not make an await sequence atomic.

State which runtime guarantee is being assumed and is not actually provided.
