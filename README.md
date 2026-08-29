# Augury

**Reads the code. Makes a falsifiable claim. Runs the experiment.**

Every AI code reviewer on the market emits fluent, plausible, unfalsifiable
observations: *"this may have concurrency issues"*, *"consider adding a
timeout"*. Augury emits claims carrying a number, a unit and a condition, and
then runs an experiment to find out whether they were right.

```
FORECAST-02   app/serializers.py:11                                    high
  Claim    queries_per_request at most 2 queries, for a 50-order listing
  Basis    the loop is in api/orders.py, the query is here; one per row plus the list
  Proof    ran experiments/queries_per_request.py -> measured 51           MISS
```

The `Proof` line is the product. It is also, so far, the only thing that
distinguishes Augury from a single well-written prompt.

---

## Who this is for

The engineer on call for a service they did not fully write.

Not because anyone was careless. Producing a working FastAPI service with a
worker, a broker and a database is now roughly one prompt away, and reviewing
generated code as closely as hand-written code destroys the speed that made you
generate it. So review got shallower. Code volume went up, comprehension went
down, and the whole difference is absorbed by whoever is paged.

The bottleneck is not writing the fix. It is forming a correct hypothesis about
an unfamiliar system while the clock runs, from evidence spread across logs,
metrics, configuration and deploy history.

And the defects that cause this share a signature. From the practice lab this
project's knowledge comes from, written months before it existed:

> **03-data/01** — "exactly the profile of a bug that survives review, because
> the code that causes it reads correctly line by line."
>
> **03-data/06** — "N+1 is not detectable by reading code. It is detectable by
> **counting queries per request**."
>
> **08-craft/03** — "A swallowed exception in a data access path turns a broken
> database into a *fast, successful, empty* response. Your dashboards go green."

If the defects that matter are invisible to reading and visible only to
measurement, a reviewer that only reads is structurally incapable of finding
them. That is the gap this fills, and it is why the Prover exists.

---

## What it does

Two components do the hardest work and neither is a language model.

**Cartographer** walks a repository in any of six languages, resolves the
import graph, computes fan-in and churn, and attaches the engineering concerns
each module touches. Deterministic; no model call.

**Scheduler** picks the next module worth reading by expected yield per dollar,
boosts modules importing something already found defective, stops when nothing
left is worth its cost, and reports every file it did not read with the reason.
Deterministic; no model call.

Then, per module: **Triage** routes to the specialists that concern applies to
(routing on presence, not certainty, because a specialist never called cannot
find anything). Eight **specialists**, one per practice-lab layer, each briefed
from the layer that defines its concern. A **Reconciler** merges findings that
collide on one construct. A **Prover** runs the case's own experiment and
records what it measured.

Knowing which parts must not be a language model is the engineering claim this
project makes.

---

## Results

Case **B01**: a seventeen-module orders service, five seeded defects each
traced to a lab topic, each reading correctly line by line, plus a loud
`FIXME: this is slow` on code that is fine.

Model `openai/gpt-oss-120b` on Groq, temperature 0.

| metric | baseline | augury |
|---|---|---|
| seeded defect recall | 1.000 | 1.000 |
| falsifiable precision | 0.833 | 0.875 |
| **hit rate** | **0.000** | **0.750** |
| cost | $0.004 | $0.027 |

The baseline is a single strong prompt containing the whole repository, asked
for exactly the same thing including a prediction. It is not a strawman: it
finds the defects, and it produces claims that look falsifiable.

**Its numbers do not survive the experiment.** That is the entire result, and
it is the only axis on which the two arms are distinguishable.

Recall, measured across three seeds, is **inconclusive** — 0.933 for the
baseline against 0.867 for Augury, identical ranges. Reported as inconclusive
rather than argued for; `SweepResult.compare` returns that verdict
automatically whenever ranges overlap, so an unsupported win cannot be
published by accident.

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for how each of these numbers
moved, and what failed to produce it.

---

## Run it

```bash
make install
cp .env.example .env      # add GROQ_API_KEY
make check                # lint, types, 311 tests
```

Full instructions, including reproducing the published numbers with no API key,
are in [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

---

## The main failure mode

Everything expensive in this system is a purchase, and the honest accounting is
that most of them have not yet paid for themselves. Routing to specialists
costs six and a half times a single prompt and finds no more seeded defects.
The Scheduler's whole reason to exist is repositories too large to read at
once, and seventeen modules is not that.

Either the crossover is at a size not yet tested, or the architecture does not
pay for itself and the hit-rate gain is the entire return. The evaluation
cannot presently separate those, and saying so is more useful than picking one.

## Hot take

See [`docs/HOT_TAKE.md`](docs/HOT_TAKE.md).

---

## What existed before

The engineering knowledge, the compose harness and the load scenarios come from
a multi-layer software engineering practice lab that predates this competition.
Everything under `src/`, `eval/` and `tests/` was written for it. The full
accounting is in [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
