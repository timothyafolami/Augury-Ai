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

The `Proof` line is the product. It is not what distinguishes the two arms --
both are graded by the same experiments, which is the only way the comparison
could be fair. It is what distinguishes either of them from a review nobody
can check.

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
project makes. Four of the six stages consult no model.

The full architecture, written from the code and one recorded run, is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Results

Three cases, ten seeded defects, five seeds per arm, every prediction put to
the case's own experiments. `openai/gpt-oss-120b` on Groq at temperature 0.

This is one run of `make evaluate`, the command in the reproduction guide, and
the table it prints:

| metric | baseline | augury | verdict |
|---|---|---|---|
| seeded recall | 0.840 | 0.860 | **inconclusive**, ranges overlap |
| hit rate | 0.931 (27/29) | 0.781 (25/32) | **no detectable difference** (Fisher p = 0.15) |
| cost | $0.009 | $0.043 (4.9x) | |

A second run of the same sweep gave recall 0.760 for both arms and hit rates of
0.893 and 0.757 -- the point estimates move by several points between runs at
temperature 0, and both runs return the same verdict. Expect your own numbers
to land near these rather than on them, and expect the verdict to be the same.
The reasons this evaluation cannot do better than that are in
[`docs/CHANGELOG.md`](docs/CHANGELOG.md), iteration 15.

**The pipeline does not beat one well-written prompt.** Not on defects found,
not on whether its numbers survive testing. It costs six times as much, and on
hit rate its point estimate is nominally *lower* than the baseline's.

It is also not shown to be worse. Ten seeded defects over three cases cannot
resolve a difference this size in either direction, and saying so is the honest
end of this experiment rather than a hedge before a claim. The verdict column
above says "no detectable difference" and not "no difference" for that reason:
a study too small to find one has not shown there is none.

That is the result. It is not the one this was built to produce, and it is the
one the evidence supports.

A note on the case set. **A04 is pooled into these numbers and should not carry
weight**: its own manifest calls it too easy to distinguish the arms, both
score 1.000 on it, and it ships no experiments, so it pulls both arms toward
parity. On B01 and C01 alone the picture is the same shape -- recall 0.730
against 0.725, hit rates 0.893 and 0.757 unchanged, since A04 contributes no
tested predictions at all.

### The finding is about measurement, not about agents

Three times this comparison appeared to have a winner, and three times the
harness was wrong:

| claim | why it was withdrawn |
|---|---|
| hit rate 0.000 vs 0.750 | measured at a third of the coverage; reversed when two experiments were added |
| the arms differ in consistency | the variance was substring matching, not the reviewers |
| hit rate 0.480 vs 0.703 | three of five experiments reported the same number on remediated code |

Each was found by pointing an adversarial reviewer at the evaluation rather
than at the code, and each survives in
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) with the run that produced it.

The last one is worth stating plainly: **for a while, the experiments could not
tell working code from broken code.** `worker_saturation` reported a perfect
score for a correctly fixed client, because httpx already defaults to a
five-second timeout and the deadline was three. `queries_per_request` reported
51 for a repository whose N+1 had been removed, because the experiment looped
over its own query instead of calling the endpoint. Both numbers were published.

The repairs are all pinned by tests. Every experiment is run against the
remediated version of the code it measures and must report a different number
([`tests/test_experiments_discriminate.py`](tests/test_experiments_discriminate.py)),
and against more than one remediation, because passing against one is how
`queue_depth` hid ([`tests/test_experiments_are_not_overfitted.py`](tests/test_experiments_are_not_overfitted.py)).

| experiment | seeded | remediated |
|---|---|---|
| `final_balance` | 90.0 | 0.0 |
| `http_status` | 200 | 500 |
| `queries_per_request` | 51 | 2 |
| `retry_amplification` | 3.0 | 1.15 |
| `worker_saturation` | 1.0 | 0.0 |
| `duplicate_side_effects` | 3 | 1 |
| `queue_depth` | 5000 | 32 |
| `active_connections` | 36 | 40 |

## Run it

```bash
make install
cp .env.example .env      # add GROQ_API_KEY
make check                # lint, types, 422 tests
```

Full instructions, including reproducing the published numbers with no API key,
are in [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

---

## The main failure mode

**The measuring apparatus was the least trustworthy component in the
experiment, and it was the last one anybody checked.**

Every published number in this project's history was wrong at least once, and
never because the scoring arithmetic was wrong. A metric divided by the wrong
denominator. A matcher that scored `except` as a mention of `exception`, and
later refused `leaks` as a mention of `leak` -- inverting recall so completely
that four findings saying nothing beat four correct ones. Experiments that
returned a number without measuring anything.

None of it was visible from inside. It took an adversarial reviewer told to
break the measurement rather than the code, and instructed to check each
experiment by writing the *fixed* version and re-running it. That single
instruction found three dead experiments in one pass.

If you build an evaluation, the thing to distrust first is the evaluation.

The second failure mode is cheaper to state: routing to specialists costs six
times a single prompt for no measurable gain. The Scheduler exists for
repositories too large to read at once, and seventeen modules is not that.
Either the crossover is at a size not yet tested, or the architecture does not
pay for itself, and this evaluation cannot separate them.

## Hot take

See [`docs/HOT_TAKE.md`](docs/HOT_TAKE.md).

---

## What existed before

The engineering knowledge, the compose harness and the load scenarios come from
a multi-layer software engineering practice lab that predates this competition.
Everything under `src/`, `eval/` and `tests/` was written for it. The full
accounting is in [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
