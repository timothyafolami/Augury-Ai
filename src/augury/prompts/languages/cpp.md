C++ gives you the machine and no supervision. The defects worth predicting are
about lifetime, sharing and what the optimiser is allowed to do.

**A data race is undefined behaviour, not a wrong number.** Unsynchronised
access to shared state may work, may lose updates, or may be deleted entirely
by the optimiser. A benchmark reporting zero lost updates at `-O2` has usually
had its loop hoisted; the same code at `-O0` loses millions.

**Lifetime across a thread boundary.** A reference or raw pointer captured by a
lambda passed to a thread outlives its scope unless something guarantees
otherwise. `std::thread` not joined and not detached terminates the process.

**`std::shared_ptr` is only atomic in its control block.** The refcount is
thread-safe; the pointee is not, and a cycle of `shared_ptr` never frees.

**Blocking with a lock held.** A mutex held across IO serialises every thread
that wants it. `std::lock_guard` makes the scope obvious, which is why a raw
`lock()`/`unlock()` pair is worth reading twice.

**Unbounded queues between threads.** A producer faster than its consumer grows
memory until the allocator fails, and the failure is a crash rather than
backpressure.

**Exceptions across an ABI boundary.** Throwing through C, or out of a
destructor, or out of a thread's top-level function, terminates.

- `std::thread::hardware_concurrency()` may return 0, and when it returns
  anything it reports the host's CPUs rather than the cgroup's quota. A pool
  sized from it is sized for a machine this process cannot use.
- `high_resolution_clock` is implementation-defined and may be an alias for
  `system_clock`, so a duration measured with it can go backwards when the wall
  clock is stepped. Use `steady_clock` for anything you subtract.
- Under Linux overcommit a `bad_alloc` handler essentially never runs. The
  allocation succeeds, the process is killed inside a later `memcpy`, and the
  cleanup path you wrote is never reached.
- `memcmp` short-circuits at the first differing byte, so it leaks the length of
  a correct prefix and is wrong for comparing a secret.
- `PQexec` permits multiple statements in one call, which turns any injection
  into an arbitrary-statement injection. `PQexecParams` does not.
