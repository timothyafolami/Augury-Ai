Python runs one thread of bytecode at a time. Almost every performance and
concurrency defect below follows from that, or from an `async def` that stops
being async somewhere in the middle.

**The blocking call in an async function.** `requests.get`, `time.sleep`,
`psycopg2`, `open().read()`, a `boto3` client, any `stripe.*` call, or a CPU
loop inside `async def` blocks the entire event loop, not one request. Under
uvicorn with one worker, one such call serialises every concurrent request
behind it. The tell is a function declared `async def` whose body contains no
`await` on the expensive line.

**`asyncio.run_in_executor` does not fix CPU work.** The default executor is a
thread pool, and threads do not run Python bytecode in parallel. Offloading a
hashing loop or a JSON parse to a thread moves it, it does not parallelise it.
Only a process pool does.

**SQLAlchemy sessions and the N+1.** A lazy relationship accessed in a loop or
inside a serialiser issues one query per row, and the loop is usually in a
different file from the query. Look for `selectinload`/`joinedload` absent on a
relationship the response walks. A `Session` shared across `await` boundaries
is a second defect: it is not concurrency-safe, and two coroutines using one
session corrupt each other's transaction state.

**Celery's defaults.** `acks_late=False` is the default, so a task acknowledged
at dispatch is lost if the worker dies mid-execution. `--concurrency=1` on a
worker is a capacity ceiling that appears only in the deployment command. A
task without `max_retries` and a retry backoff retries forever on a permanent
failure.

**`except Exception` that returns a default.** Returning `None`, `[]` or `{}`
from a handler makes an outage indistinguishable from an empty result, in the
response and in the metrics. This is the single commonest defect in Python
services written quickly.

**Mutable default arguments and module-level state.** `def f(x=[])` shares one
list across every call for the life of the process. A module-level dict used as
a cache is shared across every request in that worker and evicts nothing.

**Threads and processes do not share what people assume.** A `multiprocessing`
worker does not see a parent's module-level cache. A `threading.Lock` in a
module reloaded by `--reload` is not the same lock.

- A plain `def` endpoint is not on the event loop and has its own ceiling:
  FastAPI runs sync handlers through `anyio.to_thread.run_sync()`, whose default
  limiter is 40 tokens **per process**, so request 41 waits with no log line, no
  metric and no exception. An `async def` handler with a sync driver inside is
  the opposite defect and stalls every concurrent request on that worker. Say
  which of the two this file has.
- Nothing in the standard library reads the CPU quota. `os.cpu_count()` and
  `sched_getaffinity` report the host or the affinity mask, never `cpu.max`, so
  `workers = 2 * os.cpu_count() + 1` gives seventeen workers on a two-CPU quota.
- psycopg3 prepares server-side after five executions, so the plan you see in
  psql is not the plan production runs. A `str` bound to a `bigint` column is an
  implicit cast and misses the index.
- SQLAlchemy opens a transaction on the first statement **including a read**, so
  a read-only `Session` pins the xmin horizon until closed. An `IntegrityError`
  leaves the session aborted until rollback.
- `contextvars` are not carried across `run_in_executor` unless the callable is
  handed `contextvars.copy_context().run`, so a correlation id vanishes there.
