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

Three seeds per arm, every prediction put to the case's own experiments.

| metric | baseline | augury |
|---|---|---|
| seeded recall, mean | 0.867 | **1.000** |
| seeded recall, range | **0.600 - 1.000** | **1.000 - 1.000** |
| hit rate | 0.571 (7 tested) | 0.500 (10 tested) |
| prediction coverage | 0.64 | 0.42 |
| cost, three seeds | $0.008 | $0.079 (10.5x) |

The baseline is a single strong prompt containing the whole repository, asked
for exactly the same thing including a prediction. It is not a strawman, and
it is not beaten on either headline rate.

**What separates them is consistency, not average quality.** Across three
seeds the baseline found 5 of 5, 5 of 5, then 3 of 5. Augury found 5 of 5
every time. A reviewer that occasionally misses two fifths of what is there is
materially worse than one that does not, even when their means are close, and
the mean is what a single run would have shown you.

On hit rate the two are **not distinguishable**: 0.571 against 0.500 over seven
and ten tested predictions. Neither denominator supports a claim.

Recall is formally **inconclusive** too, because the ranges touch at 1.000.
`SweepResult.compare` returns that verdict automatically whenever ranges
overlap, so an unsupported win cannot be published by accident.

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

**A metric measured at low coverage is not measuring what you think.**

An earlier run of this same comparison reported hit rates of 0.000 for the
baseline and 0.750 for Augury, and that number was in this README. It was an
artefact: only three experiments existed, so only a third of each arm's
predictions could be tested, and which third happened to be testable decided
the result. Adding two more experiments moved coverage from 0.37 to 0.53 and
reversed the ordering.

Nothing was wrong with the scoring code. The denominator was simply too small
to mean anything, and it was reported anyway. That is the failure mode this
project exists to catch, found in the project itself, and it is why the harness
now refuses to print a rate under five measurements.

The second failure mode is cheaper to state: routing to specialists costs ten
times a single prompt for no distinguishable gain in either headline rate. The
Scheduler exists for repositories too large to read at once, and seventeen
modules is not that. Either the crossover is at a size not yet tested, or the
architecture does not pay for itself. The evaluation cannot presently separate
those, and saying so is more useful than picking one.

## Hot take

See [`docs/HOT_TAKE.md`](docs/HOT_TAKE.md).

---

## What existed before

The engineering knowledge, the compose harness and the load scenarios come from
a multi-layer software engineering practice lab that predates this competition.
Everything under `src/`, `eval/` and `tests/` was written for it. The full
accounting is in [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
