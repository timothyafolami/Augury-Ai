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
