Node runs one thread of JavaScript. Everything below follows from that, or from
a promise nobody awaited.

**The unawaited promise.** An `async` function called without `await` and
without `.catch` produces an unhandled rejection: the work continues, the
caller returns success, and the failure surfaces as a process-level warning or
a silent exit. In a request handler this means responding 200 before the work
that response describes has happened.

**Blocking the event loop.** `fs.readFileSync`, `crypto.pbkdf2Sync`, `JSON.parse`
on a large payload, a `for` loop over a big array, or any synchronous crypto in
a request path stalls every other request in the process. `libuv`'s thread pool
defaults to four threads, so four concurrent `fs` or `dns` operations saturate
it and the fifth queues.

**`Promise.all` with no bound.** Mapping an array of unknown length to promises
and awaiting all of them opens that many connections at once. With a database
pool of ten and an array of five hundred, the pool is the failure point.
`Promise.allSettled` changes the error handling, not the concurrency.

**Connection pools created per request.** A `new Pool()` or `new PrismaClient()`
inside a handler creates a pool per request rather than per process, so the
pool bounds nothing and connections are never reused.

**`try/catch` around `await` that swallows.** Catching and returning a default
has the same effect as Python's bare `except`: an outage becomes an empty
result. In TypeScript the type system actively hides it, because the function
still returns its declared type.

**Types are erased at runtime.** A value typed `User` that arrives from
`JSON.parse`, a database driver or `req.body` has been asserted, not validated.
Any handler that trusts an interface without a runtime schema check is
trusting the client.

**Timeouts are absent by default.** `fetch` and `axios` have no default
timeout, so a hung upstream holds the request until the client gives up.

- `pg.Pool` defaults to `max: 10` and `connectionTimeoutMillis: 0`, which queues
  a request that cannot get a connection **indefinitely**: the event loop stays
  responsive, health checks pass, and requests simply never complete. Failing by
  waiting rather than by erroring is the shape to look for.
- `server.keepAliveTimeout` must be shorter than `server.headersTimeout`.
- `dns.lookup` uses the **same** four-thread libuv pool as file IO, so DNS and
  disk contend for it.
- A global `unhandledRejection` handler converts a loud crash into a silent
  failure.
- V8 sizes its heap from the cgroup, but Buffers and Worker heaps live outside
  it, so the container is killed at a total the heap limit never predicted.
