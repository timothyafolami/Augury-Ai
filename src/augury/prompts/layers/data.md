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
  `UPDATE ... SET x = x + n`, or SERIALIZABLE. Predict the divergence under
  N concurrent writers.
- Queries issued inside a loop or a serializer, where the count scales with the
  result set. Predict queries per request at a stated row count.
- Filters, joins and ORDER BY on columns with no index. Predict the latency at
  a stated table size, and say which index would remove it.
- Pool size against the real concurrency ceiling: worker count times threads.
  Predict the arrival rate at which requests begin queueing rather than failing.
- Transactions held open across a network call.

Do not report a missing index you cannot tie to a query in this file, and do
not report isolation problems on a table only one writer touches.
