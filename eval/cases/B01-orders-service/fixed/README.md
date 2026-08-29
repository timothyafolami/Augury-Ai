# The remediated versions

For each seeded defect, the file as it should have been written.

These are not documentation. `tests/test_experiments_discriminate.py` copies the
case repository, overlays these files, and re-runs every experiment against the
result. An experiment that reports the same number on both is not measuring the
defect, and the test fails.

That test exists because three of the five experiments did exactly that, and
the numbers they produced were published:

- `worker_saturation` reported 1.000 for a client with a perfectly good
  timeout, because its deadline was shorter than httpx's own default.
- `retry_amplification` reported 3 for a client with backoff, jitter and a
  retry budget, because it measured `MAX_ATTEMPTS` from a single request.
- `queries_per_request` reported 51 for a repository whose list endpoint had
  been fixed, because the experiment looped over its own query instead of
  calling the endpoint.

An experiment that cannot fail on correct code cannot pass on incorrect code
either. It just returns a number.
