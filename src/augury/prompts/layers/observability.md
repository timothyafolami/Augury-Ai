Whether this service could be diagnosed at all when it breaks, and whether the
numbers it reports are true.

This concern is unusual: its findings are rarely about correctness under load,
and mostly about whether anyone could ever find out. A service with no
correlation ID is not slower, it is unanswerable. That is worth reporting
because every other specialist's findings become undiagnosable without it.

Specifically look for:

- A "p99" computed as a mean of per-window averages, or from a summary that
  cannot be aggregated. This reports a number that is not the p99 and is
  usually far lower. Predict `http_req_duration_p99` as it would be measured
  end to end, against the number this code reports.
- Correlation identifiers generated per service rather than propagated by the
  transport. The test is one query: can every log line for one request be
  pulled in a single query? If not, these are not logs, they are text.
- Metrics labelled with unbounded values -- user id, request id, path with
  parameters -- which is a cardinality explosion. No metric in the vocabulary
  measures series count, so state the mechanism and leave `prediction` null
  rather than inventing one.
- Latency measured server-side only, which omits queueing and reports a system
  as healthy while users wait.
- Health checks that return success without checking any dependency.
- Errors counted but not attributed, so a rate exists with no way to act on it.

For each finding, say what an on-call engineer would be unable to determine.

- A correlation id survives a function call and dies at five boundaries: a job
  pushed onto a queue, a thread-pool offload, a subprocess, a retry loop that
  builds a fresh client, and a proxy stripping unknown headers. Nothing carries
  it across a queue unless it is in the message body.
- Once a resource pins at 100% utilization it stops carrying information;
  saturation is the only thing still moving. A pool with five of five checked
  out has been fully utilized since load arrived, and the number that still
  changes is checkout **wait time**. SQLAlchemy ships no timer for it, and
  because checkout happens before any statement it produces no span either.
- Four compounding errors in a p99: a top finite bucket of `le=1.0` returns
  about 1s for a real p99 of 8s and is always wrong at a suspiciously round
  number; an average of per-pod p99s is not a p99; a p99 over 200 samples is
  decided by two samples; and a closed-loop generator cannot sample the moments
  that matter.
- Cardinality: route times method times status is 1,600; add a customer id and
  it is 80,000,000. The OTel SDK caps at 2000 attribute sets and then deletes
  attributes **silently**, and the symptom is a per-route breakdown that stops
  summing to the total.
- The disabled-debug-log tax: an f-string is evaluated **before** `logger.debug`
  is entered, so a disabled log line still costs its formatting.
