Correctness and cost at the database boundary: isolation levels and the
anomalies each one permits, index presence on hot predicates, query counts per
request, lock ordering, and pool sizing against real concurrency.

The defects here share a signature: the code reads correctly line by line and
fails only under concurrency or at scale. A read-modify-write on a balance is
obviously correct in isolation and loses updates under READ COMMITTED the
moment two writers overlap. An N+1 is invisible in the file you are reading
because the loop and the query live in different layers.

Specifically look for:

- Read-modify-write on a row without `SELECT ... FOR UPDATE`, an atomic
  `UPDATE ... SET x = x + n`, or SERIALIZABLE. Predict `final_balance` under
  N concurrent writers.
- Queries issued inside a loop or a serializer, where the count scales with the
  result set. Predict `queries_per_request` at a stated row count.
- Filters, joins and ORDER BY on columns with no index. Predict `http_req_duration_p99` at a stated table size, and say which index would remove it.
- Pool size against the real concurrency ceiling: worker count times threads.
  Predict `active_connections` against the pool size, and the `worker_saturation` that follows.
- Transactions held open across a network call.
- One connection left `idle in transaction` pins the xmin horizon for **every**
  table in the cluster, not only the ones this code touches, so autovacuum
  reclaims nothing. SQLAlchemy opens a transaction on the first statement
  including a read, so a read-only `Session` that is never closed does this.
- Count the whole fleet: `replicas x workers x (pool_size + max_overflow)`
  against `max_connections` minus the reserved superuser slots. Four workers at
  `pool_size=5, max_overflow=10` is 60 from one container, and a second replica
  is 120 against a default budget of 97.
- A read replica makes "I just saved this and it is gone" supported behaviour.
  Correctness needs the LSN captured after commit compared against
  `pg_last_wal_replay_lsn()`, not `pg_last_wal_receive_lsn()`: received rather
  than applied is the bug people actually ship.
- `ALTER TABLE` waiting behind one long `SELECT` queues every later `SELECT`
  behind the waiter, so traffic stops within seconds. `SET LOCAL lock_timeout`
  turns that outage into a failed migration. `CREATE INDEX` without
  `CONCURRENTLY` over about a million rows blocks writes throughout.
- Write skew: two transactions each read a consistent snapshot, each update
  their **own** row, and the invariant breaks with no row conflict. Postgres
  `REPEATABLE READ` permits it, and retrying only the failed statement on a
  40001 reintroduces it. The whole transaction must be retried.
- An N+1 that crosses a service boundary has the same shape and no ORM tool can
  see it. A GraphQL resolver runs per field per object by design, and DataLoader
  batches only within one tick of the event loop, so a single `await` between
  them ends the batching window while the configuration still looks right.

Do not report a missing index you cannot tie to a query in this file, and do
not report isolation problems on a table only one writer touches.
