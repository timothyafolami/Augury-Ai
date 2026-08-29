The JVM hides allocation and scheduling well enough that the defects show up as
pool exhaustion and as work that never finishes.

**Blocking a thread from a bounded pool.** A servlet container has a fixed
worker pool, and an outbound call without a timeout holds one worker for as
long as the upstream takes. Tomcat's default `maxThreads` is the ceiling on
concurrency, and it is in configuration rather than code.

**`ExecutorService` never shut down.** A pool created per request, or created
and never `shutdown()`, leaks threads. `Executors.newCachedThreadPool()` has no
upper bound at all.

**JPA and the N+1.** A lazy association walked in a loop or during
serialisation issues one query per row. `@Transactional` on a method that makes
a network call holds the database transaction for the duration of that call.

**HikariCP sizing.** `maximumPoolSize` against the servlet thread count is the
real concurrency ceiling; a pool smaller than the worker pool means workers
queue on connections, and `connectionTimeout` decides whether that surfaces as
latency or as an error.

**Catching `Exception` and logging.** Same defect as elsewhere, with the
addition that catching `Throwable` also catches `OutOfMemoryError` and
continues.

**`CompletableFuture` without an executor.** The default is the common
ForkJoinPool, which is shared process-wide and sized to the CPU count. Blocking
work submitted there starves everything else using it.

**Virtual threads change the arithmetic, not the rules.** Under Java 21 virtual
threads a blocking call no longer pins a platform thread -- unless it is inside
`synchronized`, which pins, or a native call, which pins.
