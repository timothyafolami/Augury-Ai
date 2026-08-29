Rust removes whole classes of defect at compile time, so the ones that remain
are about blocking, cancellation and panics rather than memory.

**Blocking inside an async task.** `std::thread::sleep`, `std::fs`, a
`reqwest::blocking` client, or a CPU-bound loop inside a Tokio task blocks that
runtime worker thread. With the default multi-threaded runtime this starves a
core; with `current_thread` it stalls everything. `tokio::task::spawn_blocking`
is the boundary that exists for this.

**A future that is dropped mid-await is cancelled.** Anything after the
`.await` never runs. A database transaction, a lock guard or a half-written
file left in that state is a correctness defect, not a performance one, and
`select!` makes it easy to write by accident.

**`.unwrap()` and `.expect()` in a request path.** Both panic. In an Axum or
Actix handler a panic aborts that request and, depending on the runtime and
panic strategy, can take the worker with it.

**`Mutex` held across `.await`.** A `std::sync::Mutex` guard is not `Send`, and
a `tokio::sync::Mutex` held across an await serialises every task that wants
it. Either is a bottleneck that reads as correct code.

**Unbounded channels.** `tokio::sync::mpsc::unbounded_channel` grows until
memory does. The bounded version applies backpressure, which is the point.

**`Arc<Mutex<...>>` as shared cache.** Correct and often the contention point:
every reader takes the write lock unless it is an `RwLock`, and neither evicts.

**Connection pool sizing.** `sqlx`'s `max_connections` defaults low; `deadpool`
and `bb8` each have their own default. The number that matters is the pool
against the runtime's worker count, and neither is visible from the other.
