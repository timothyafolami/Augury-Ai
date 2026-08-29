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
project makes. Five of the seven steps consult no model.

The full architecture, written from the code and one recorded run, is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Results

Three cases, ten seeded defects, five runs per arm, every prediction put to
the case's own experiments. `openai/gpt-oss-120b` on Groq at temperature 0.

**What "five seeds" means here, precisely:** the seed is a label on a repeat.
It does not vary the prompt, the temperature, the case, or the order modules
are read in -- every run sends byte-identical prompts, which
[`tests/test_what_a_seed_varies.py`](tests/test_what_a_seed_varies.py) pins.
So the spread between seeds measures **how much the provider varies when asked
the same question five times at temperature 0**. It is not a sample over
anything the harness varied and must not be read as a confidence interval.
This was discovered by recording the sweep: all five collapsed to one, because
they were one call repeated.

### The comparison was unfair until recently, in the pipeline's favour

Every number published before this section was produced by a harness that gave
the two arms different instructions. A review found four asymmetries, all
pointing the same way:

- The analyst prompt was told exactly what the falsifiability validator
  rejects. The baseline prompt was not -- so one arm held the answer key to a
  metric both arms are scored on.
- A finding whose prediction failed validation was counted **twice** in that
  metric's denominator, once as a finding and once as dropped. So a malformed
  prediction cost more than no prediction at all, and the arm that was not
  coached produced more of them.
- `reconcile`, which is deterministic and costs no model call, ran on the
  pipeline arm only. It removes duplicate findings from the denominator.
- The baseline was told to omit a field the schema requires, which strict
  providers reject outright.

All four are fixed, with tests that fail against the old behaviour
([`tests/test_arm_symmetry_beyond_bytes.py`](tests/test_arm_symmetry_beyond_bytes.py),
[`tests/test_precision_denominator.py`](tests/test_precision_denominator.py)).
Two of the tests that were supposed to catch this were instead enforcing it:
one asserted the vacuity rule for the analyst *by name*, and one accepted a
`nested` schema argument and never used it.

### The result after fixing it

A sweep was recorded call by call and the recordings committed, so this is
reproducible exactly, with no API key: `make eval-replay` prints it verbatim.

| metric | baseline | augury |
|---|---|---|
| seeded recall (matcher) | 0.800 | 0.800 |
| seeded recall (hand-audited) | 0.700 | 0.800 |
| falsifiable precision | **0.909** | 0.667 |
| hit rate | 0.833 (5/6) | 1.000 (6/6) |
| experiments run | 6 | 5 |
| prediction coverage | 0.600 | 0.429 |
| cost | $0.00 replayed | $0.00 replayed |

```
hit rate  repeats not independent: p = n/a  not measured
recall    repeats not independent: inconclusive
```

**The harness cannot separate the two arms on any metric, and now says so on
every row.**

Recall is identical. Falsifiable precision favours the baseline: the pipeline
states more claims and a smaller share survive validation. The hit rate favours
the pipeline by **one prediction** — six of six against five of six — which is
not a result, and the significance test refuses to dignify it with a p-value
because the repeats are not independent.

#### Recall, audited by hand

Recall is matched by prose against a manifest, and prose matching cannot tell a
correct diagnosis from a wrong one that mentions the right word. So all twenty
matches in the run above were read by hand. One is wrong:

**C01-3** is a session leaked when the body raises. The baseline was credited
with it for this finding:

> `engine`: SQLAlchemy engine is configured with `pool_size=10` and
> `max_overflow=0` ... 40 concurrent `with_session` calls will exceed this

That is a different defect, and its remediation -- raise the pool size -- does
not close the leak. It scores because the sentence contains `with_session`.
The pipeline's match on the same defect is genuine: *"When `work` raises an
exception the session is never closed."*

| | matcher | audited |
|---|---|---|
| baseline | 0.800 | **0.700** |
| augury | 0.800 | **0.800** |

Which is a difference in the pipeline's favour, and it is worth exactly as
little as the differences that ran the other way: **one observation, ten
defects, no significance test possible.** It is reported because the sentence
"recall is tied" was not supported by the underlying matches, not because 0.700
against 0.800 is a result.

[`tests/test_the_recall_matcher_is_not_sound.py`](tests/test_the_recall_matcher_is_not_sound.py)
pins five ways the matcher is wrong, including this one and including a review
that asserts the code is **correct** in five sentences and scores a perfect
1.000. Those tests assert the flaws rather than the fix, because there is no
fix: a matcher cannot read intent.

The `prediction coverage` row is the one to read next to the hit rate. An
untested prediction costs nothing: it is not a miss, it is not Broken, it is
excluded. The pipeline had **43%** of its falsifiable claims graded against the
baseline's 60%, so its perfect hit rate is a perfect score on its best-aimed
claims. That row is printed for exactly this reason — it was computed and
withheld from the table until a review pointed out that the hit rate cannot be
read honestly without it.

#### This table said something else an hour ago

It read `hit rate 0.833 (25/30) vs 1.000 (30/30), Fisher p = 0.052,
suggestive`. Every one of those numbers was an artefact.

Replay serves all five repeats from one recording, so the observation is 5/6
and 6/6 — and pooling counted it five times. `compare` and the permutation test
were both guarded against exactly this after iteration 18. **`fisher_exact` was
not**, and it was the one being fed the pooled counts. p = 1.0000 was published
as p = 0.052.

At the same time, falsifiable precision read 0.583 instead of 0.667, because
the commit that fixed the double-counted denominator changed `score()` and the
published figure comes from `aggregate()`. The test written to catch that used
a report with zero falsifiable findings, where 0/1 and 0/2 are both 0.0 — so
the fix, and its test, both passed without the fix reaching the number.

Both were found by an adversarial review of the harness, by mutation rather
than by reading. Of 36 mutations applied to the scoring and significance code,
33 were killed by the suite. The three that survived are how these shipped.

**The pipeline does not beat one well-written prompt.** It finds the same
seeded defects, states more claims of which fewer survive validation, is graded
on a smaller share of them, and costs five times as much. Its one nominal lead
is a single prediction on a run whose repeats carry no independent information.

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
make check                # lint, types, 519 tests
```

Full instructions, including reproducing the published numbers with no API key,
are in [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

### On a repository of your own

```bash
augury mcp --root /path/to/your/repo
```

Serves the reviewer over the Model Context Protocol on stdio, so it runs inside
whatever agent you already use rather than only behind this CLI. Three tools:

| tool | cost | needs a key |
|---|---|---|
| `augury_map` | free | no |
| `augury_explain` | free | no |
| `augury_review` | reports what it spent | yes |

Mapping is deterministic and the layer briefs are files on disk, so two of the
three cost nothing — you can see what a review would cover, and what it would
cost, before buying one. The root is fixed by whoever launches the server
rather than chosen per call: the client is driven by a language model, and a
model that can name any path can read any file on the machine.

The stdio protocol is implemented directly rather than via the `mcp` SDK. It is
about forty lines of JSON-RPC framing, it adds no dependency to a project a
judge has to install offline, and it made the handler a pure request-to-response
function that [`tests/test_mcp_server.py`](tests/test_mcp_server.py) exercises
without a subprocess.

---

## Pointed at code nobody seeded

Every number under **Results** comes from cases where this project planted the
defects. So it was also run once against a repository it had never seen — 533
modules, six languages, a five-cent budget. It read 14 files, spent $0.0501, and
returned 10 findings. Scored by hand against the source: **four correct, two
true but blind to what the code was for, one confidently false, three needing an
experiment nobody has written.**

The false one is the reason that run is worth publishing. It carried a metric, a
comparator, a value, a unit and a runnable condition; it passed the
falsifiability gate cleanly; and it was wrong. The gate makes a claim checkable,
not true — which is the same thing the evaluation says, arrived at from the
other direction.

[`docs/FIELD_RUN.md`](docs/FIELD_RUN.md) has every finding and how it was scored.

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
repositories too large to read at once, and twenty-three modules is not that.
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
