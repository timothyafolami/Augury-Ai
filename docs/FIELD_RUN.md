# The first run on code nobody seeded

> **Recorded before the arm-parity fixes of iteration 20.** The prompts have
> since changed: both arms are now told what the falsifiability validator
> rejects, and every layer brief names a metric from the published vocabulary.
> This run is kept as recorded rather than re-run, because what it demonstrates
> -- that a well-formed prediction can be completely false -- does not depend on
> those changes, and re-running it would replace a real observation with a
> tidier one.

Every number in `README.md` comes from `eval/cases/`, where the defects were
planted by this project and the grader knew the answers. That is the right way
to measure, and it is not evidence that the thing is useful.

So it was pointed at a repository it had never seen and nobody had prepared:
the practice lab this project's eight specialists are derived from. 533 modules,
six languages, no seeded defects, no answer key.

## What it was given

| | |
|---|---|
| repository | `software-engineering-practice`, 533 modules |
| languages | python 228, javascript 97, go 69, rust 50, cpp 45, java 43, typescript 1 |
| mapping | 1.5s, 2 files unparsed, 0 skipped, **no model calls** |
| budget | **$0.05** |
| model | `openai/gpt-oss-20b` on Groq |

## What it did

| | |
|---|---|
| modules read | **14 of 533** (3%) |
| stopped because | budget exhausted |
| spent | **$0.0501** in 71s |
| findings | 10, plus 1 dropped as unfalsifiable |

Three percent coverage is the honest headline. The Scheduler is not sampling
randomly — it ranks by fan-in, churn and signal density and buys the most
promising reads first — but a nickel buys fourteen files, and it says so rather
than implying it read the repository.

## Scoring it by hand

Nobody had an answer key, so each finding was checked against the source. This
is the same discipline the lab's own `PREDICTIONS.md` demands: a plausible
finding and a true one are indistinguishable until you look.

### Correct — verified in the source

**`04-distributed/.../kafka.py:22` — offsets commit before the work happens.**
The source reads `"enable.auto.commit": True`. Offsets commit on a timer
independent of processing, so a crash between the commit and the handler loses
the message. Textbook at-most-once. Right file, right line, right mechanism.

**`05-failure/lab/app/cache.py` — a Redis outage is counted as a cache miss.**
`except Exception: counters.inc("cache_misses"); return None`. The finding's
phrasing — that an outage becomes indistinguishable from a legitimate miss in
the metrics — is exactly right, and it is an observability defect rather than
the correctness defect it superficially resembles.

**`01-machine/.../openloop.py:176` — a new TCP connection per request.**
`urllib.request.urlopen(url, timeout=5)` inside the per-request handler, no
pooling. True. Also the most interesting hit in the run: this is the lab's
**own load generator**, carrying a defect from the lab's own curriculum.

**`03-data/lab/local/lab_db.py` — `has_extension` swallows the reason.**
`except Exception: return False`, so a permission denial is reported as "the
extension is absent." True.

### True, but context-blind

**`05-failure/lab/app/config.py` — `PGPASSWORD` default is `"app"`.**
The string is in source. It is also the default in a config table for a
docker-compose lab that never leaves localhost. Reported **high**; it is
low at most.

**`04-distributed/.../payments6.py` — `POST /payments` has no authentication.**
Factually correct — there is no auth anywhere in the file. It is a lab fixture
whose entire purpose is to demonstrate dual-write versus the transactional
outbox. Reported **high**.

Both are the same error: the finding is true about the code and wrong about
what the code is for. Nothing in the pipeline reads a repository's *purpose*.

### False

**`05-failure/lab/app/config.py:114` — "SSRF via `DATABASE_URL`".**

> `active_connections at_least 1 count @ DATABASE_URL='http://169.254.169.254/'`

`db.py:50` uses `DATABASE_URL` as an **asyncpg DSN**. asyncpg will not fetch an
HTTP URL; it will fail to parse it. There is no request, no internal address
reached, no SSRF.

This is the most useful result in the run, because of how it is dressed. It has
a metric from the published vocabulary, a comparator, a value, a unit, and a
condition specific enough to run. It passed the falsifiability gate cleanly and
sits in the report looking exactly like the Kafka finding, which is true.

**The gate makes a claim checkable. It does not make it true.** That is the
whole argument for the Prover, and it is why the evaluation reports no
detectable difference between the arms: a well-formed wrong answer costs the
same as a well-formed right one until something runs it.

### Not checked

Three findings assert behaviour under load (`worker_saturation` at 250rps,
`active_connections` at `workers=4`, saturation at `POOL_SIZE=0`). Checking
them means running the experiment, which this repository has no case for. They
are neither hits nor misses here. Counting them either way would be the
Layer 1 mistake.

## Tally

| | |
|---|---|
| correct, verified | 4 |
| true but context-blind | 2 |
| false | 1 |
| unchecked, needs an experiment | 3 |

Six of seven checkable findings say something true about the code. One is
confidently wrong. On a sample of seven that is a hit rate with a confidence
interval wide enough to drive through — it is a demonstration, not a
measurement, and it is reported here as one.

## What it says about the design

**Symbols are reliable; line numbers are not.** Every finding named the right
function. `has_extension` was reported at line 285 and is at 425 — 140 lines
off. `cache.get` was off by about ten. Two were exact. Anything downstream that
binds a finding to a location should bind on the symbol.

**Mapping being free is what makes a nickel useful.** Cartography read all 533
modules, in six languages, in 1.5 seconds, for nothing, and that is what let
the Scheduler spend the entire budget on fourteen files worth reading rather
than on the first fourteen it encountered.

**The specialists disagreed usefully.** `cache.py` came back from `craft` as a
swallowed exception; the mechanism that made it worth reporting is an
observability one. One file, two concerns, and the routing sent it to both.
