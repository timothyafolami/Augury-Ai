# Defect Taxonomy

Every seeded defect traces to a topic in the engineering-practice lab. Nothing
here is invented for convenience: the lab decides what a defect *is*, and the
lab's own argument decides how it must be verified.

Three topics state the thesis of this project outright, and they were written
before this hackathon existed:

> **03-data/01** — "exactly the profile of a bug that survives review, because
> the code that causes it reads correctly line by line."
>
> **03-data/06** — "N+1 is not detectable by reading code. It is detectable by
> **counting queries per request**, which is mechanical, automatable and
> enforceable in CI."
>
> **08-craft/03** — "A swallowed exception in a data access path turns a broken
> database into a *fast, successful, empty* response. Your dashboards go green."

If the defects that matter are invisible to reading and visible only to
measurement, then a code reviewer that only reads is structurally incapable of
finding them. That is the gap Augury fills, and it is why the Prover exists.

---

## 1. The three codebases

The defects are spread across three small services rather than one, because a
reviewer that only works on the shape of repo it was tuned for has not been
tested. Each is a plausible service that **reads fine**. None is a toy with an
obvious bug, and none is a full end-to-end product.

| Repo | Shape | Defect families |
|---|---|---|
| `orders-api` | FastAPI + SQLAlchemy + Postgres | Data correctness, concurrency, pooling |
| `ingest-worker` | Async worker + Redis + HTTP upstream | Retries, timeouts, idempotency, backpressure |
| `llm-gateway` | FastAPI proxy in front of a model server | Cancellation, races, security, measurement |

`llm-gateway` mirrors `10-edge/lab/gateway`, so its verification reuses the k6
scenarios already captured in `10-edge/lab/out/`.

---

## 2. The catalogue

**Tier 1** is the committed set — eight defects, done excellently. **Tier 2** is
the stretch set, built only after Tier 1 is measured end to end. This is the
answer to "eight or twelve": both, in that order, with a gate between them.

### orders-api

| ID | Defect | Lab topic | Tier | Verified by |
|---|---|---|---|---|
| A1 | Read-modify-write on a balance with no row lock; lost update under READ COMMITTED | `03-data/01` | 1 | Differential |
| A2 | N+1 across a serializer boundary; loop and query in different files | `03-data/06` | 1 | Query count |
| A3 | Hot filter column with no index; fine at 1k rows | `03-data/03` | 2 | Load |
| A4 | SQLAlchemy `pool_size` below uvicorn worker count | `02-network/02`, `03-data/07` | 1 | Load |
| A5 | Bare `except` in a data-access path returning an empty list | `08-craft/03` | 1 | Probe |

### ingest-worker

| ID | Defect | Lab topic | Tier | Verified by |
|---|---|---|---|---|
| B1 | Retry with fixed delay, no jitter, no budget; multiplicative across hops | `05-failure/03` | 1 | Load |
| B2 | Outbound HTTP call with no timeout | `02-network/03` | 1 | Load |
| B3 | Non-idempotent handler; duplicate delivery doubles the side effect | `04-distributed/02` | 2 | Differential |
| B4 | Unbounded queue, no backpressure or shedding | `05-failure/05` | 2 | Load |
| B5 | Correlation ID generated per service, not propagated by transport | `06-observability/03` | 2 | Probe |

### llm-gateway

| ID | Defect | Lab topic | Tier | Verified by |
|---|---|---|---|---|
| C1 | No cancellation on client disconnect; work continues after the client leaves | `10-edge/02` | 2 | Differential |
| C2 | Shared counter mutated from multiple tasks without synchronisation | `01-machine/04` | 1 | Differential |
| C3 | Credential written to a log line at INFO | `07-security/07` | 1 | Probe |
| C4 | String-interpolated filter in an admin endpoint | `07-security/02` | 2 | Probe |
| C5 | "p99" computed as a mean of per-window averages | `06-observability/02` | 2 | Differential |

Tier 1 is A1, A2, A4, A5, B1, B2, C2, C3 — eight defects spanning six lab
layers and all three verification strategies.

---

## 3. Verification strategies

The Prover has exactly three, and every defect declares which one applies. This
is what keeps the Prover small enough to build well.

**Load** — parameterise a k6 scenario from the claim's threshold, run it against
the service, read the result. Answers "does p99 cross X at rate Y". Reuses
`pool_ramp.js`, `arrival_rate.js`, `fanout.js` and `fake_upstream.py`.

**Differential** — run an operation whose correct outcome is arithmetically
known, then compare observed state to expected. Two hundred concurrent
increments should leave the counter at two hundred. Answers "is the result
wrong", not "is it slow".

**Probe** — a single request or a single scan, with a deterministic assertion.
Kill the database and assert the endpoint returns an error rather than a fast
empty success. Grep the log stream for the seeded credential. Run the one-query
test for a correlation ID.

Every verdict is **Hit**, **Miss** or **Broken**, per `PREDICTIONS.md`. Broken
means the experiment itself failed and is never counted as either.

---

## 4. Why this doubles as the agent architecture

The lab layers are not just where the defects come from. They are also how the
analyst agents are divided, so the specialist that hunts a defect is the one
that owns the layer that defines it. See `BUILD_PLAN.md` §3.2.
