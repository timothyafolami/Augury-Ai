Go gives you real parallelism and almost no guardrails around lifetime. Most
defects here are things that were started and never stopped.

**The goroutine that outlives its reason.** `go func()` with no way to cancel
it, or one that writes to a channel nobody reads again, leaks for the life of
the process. The tell is a goroutine started in a request handler without the
request's `context.Context`, or a `select` with no `case <-ctx.Done()`.

**A context that is not propagated.** `context.Background()` or `context.TODO()`
inside a request path discards the caller's deadline, so a timeout at the edge
does not stop the work underneath it. Every outbound call in a handler should
carry the handler's context.

**`defer` in a loop.** Deferred calls run at function return, not at iteration
end, so `defer rows.Close()` inside a loop holds every connection until the
function exits.

**`rows.Err()` unchecked.** `for rows.Next()` ends both on exhaustion and on
error, and skipping `rows.Err()` turns a mid-iteration failure into a short
result set that looks like a successful query returning less data.

**`database/sql` pool defaults.** `SetMaxOpenConns` unset means unlimited
connections to the database, which moves the failure from the service to
Postgres. `SetConnMaxLifetime` unset behind a proxy or load balancer means
connections are held until something else severs them.

**Unbuffered channels and `WaitGroup`.** A send on an unbuffered channel blocks
until a receiver is ready; a `wg.Add` inside the goroutine instead of before it
is a race. `wg.Wait()` with no timeout waits forever.

**Errors dropped with `_`.** Assigning an error to `_`, or returning it wrapped
without checking, is the same defect as a swallowed exception and is easier to
miss because it is one character.

**`http.Client` without a `Timeout`.** The zero value has no timeout at all. A
package-level `http.DefaultClient` in a service is an unbounded wait.
