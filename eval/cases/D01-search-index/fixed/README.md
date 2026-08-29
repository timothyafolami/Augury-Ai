# The remediated version of D01

Every file here replaces its namesake in `../repo/`. Running an experiment
against this tree instead of against `repo/` is how the experiment is shown to
measure the defect rather than the harness:

| experiment | seeded | remediated |
|---|---|---|
| `memory_bytes` | 3,971,308 | 266,096 |
| `queries_per_request` | 41 | 1 |

Both were run twice against both trees and returned the same number each time.

## `app/index/cache.py` — the unbounded cache

An `OrderedDict` bounded at 128 entries, evicting least-recently-used. The
bound is chosen against the working set rather than against the query space,
because a cache that must hold every distinct query is not a cache.

## `app/index/searcher.py` — the N+1

One query that selects the body alongside the id and title, instead of a
listing query followed by a fetch per matching row.

## `app/api/handlers.py` — the per-request key stretch

The verified tokens are remembered, so the stretch runs once per distinct
token rather than once per request.

**This one ships with no experiment, and the reason is worth stating.**

Its metric is `http_req_duration_p99`, and this project requires every
experiment to return the *same number twice* — `tests/test_experiments_
discriminate.py` runs each one twice and fails on any difference. That
guarantee exists because `retry_amplification` once returned anywhere between
1.9 and 2.5 for identical code.

A wall-clock percentile cannot meet it. An experiment was written for this
defect, and it worked: 33.9 ms seeded against 0.001 ms remediated, four orders
of magnitude apart. It was deleted anyway, because the second decimal place
moves every run and shipping it would have meant weakening the determinism
guarantee to accommodate one measurement.

Writing it was not wasted. It surfaced a defect in itself first: at a hundred
samples the nearest-rank p99 *is* the maximum, so the remediation -- which pays
the stretch exactly once -- measured no better than the defect, because that
one warm-up request was the p99. Five hundred samples fixed it. Then the
determinism rule killed it regardless.

So `http_req_duration_p99` stays in the published vocabulary, is predicted
against by four of the eight layer briefs, and is settled by nothing. A
prediction naming it passes the falsifiability gate and is recorded as
untested. That is a real limitation of this harness and it is written down here
rather than left for a reader to infer from an absence.
