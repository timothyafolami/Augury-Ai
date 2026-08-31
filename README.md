# Augury

**Reads the code. Makes a falsifiable claim. Runs the experiment.**

Every AI code reviewer on the market emits fluent, plausible, unfalsifiable
observations: *"this may have concurrency issues"*, *"consider adding a
timeout"*. Augury emits claims carrying a number, a unit and a condition, and
then runs an experiment to find out whether they were right.

What `augury review --case B01 --arm augury --prove` actually prints, copied
from a run you can reproduce with no API key:

```
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ severity ┃ location                  ┃ claim                      ┃ verdict  ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ medium   │ app/serializers.py:10     │ queries_per_request        │ hit      │
│          │                           │ at_least 51queries @ GET   │          │
│          │                           │ /orders listing for a      │          │
│          │                           │ customer with 50 orders    │          │
│ high     │ app/services/wallet.py:15 │ no prediction              │ untested │
│ high     │ app/services/wallet.py:31 │ final_balance between 10x  │ hit      │
└──────────┴───────────────────────────┴────────────────────────────┴──────────┘
dropped debit: vacuous: a band starting at or below zero excludes nothing
```

Three things in that table are the product. The **claim** column carries a
metric, a comparator, a number with a unit and the condition it holds under.
The **verdict** column is what an experiment measured, not what the model
believes. And `no prediction` and `dropped` are printed rather than hidden: a
finding the reviewer could not make testable is still shown, and a claim the
falsifiability gate refused says why.

None of that is what distinguishes the two arms -- both are graded by the same
experiments, which is the only way the comparison could be fair. It is what
distinguishes either of them from a review nobody can check.

---

## Three ways in

One review engine. The CLI drives it, an MCP server exposes it to another
agent, and a web client watches it work. None is a second implementation, and
the document a team acts on is rendered by the same function whichever asked
for it.

### Start it

```bash
./start.sh
```

That installs the dependencies, builds the interface once, and serves the API
and the UI from a single process on <http://localhost:8000>. **It needs no API
key and spends nothing**: it replays reviews recorded call by call and
committed to this repository, so the pipeline you watch is a real run rather
than a demonstration mode. `./start.sh --live` reviews your own repositories
and needs a provider key.

The other two clients:

```bash
augury report --path /path/to/repo --scope backend   # writes the document
augury mcp                                           # exposes it over MCP
```

Three repositories replay, and the interface offers them:

| repository | language | replays |
|---|---|---|
| `eval/cases/B01-orders-service/repo` | Python | 4 deployment findings, 16 code findings across nine specialists, 5 pressures, 4 synthesis observations, 259-line document |
| `eval/cases/E01-go-inventory/repo` | Go | 4 deployment, 6 code, 4 pressures, 3 observations, 151-line document |
| `eval/cases/F01-ts-checkout/repo` | TypeScript | 4 deployment, 5 code, 2 pressures, 3 observations, 143-line document |

Every count there is what a fresh clone with no key produced, at $0.00. Every
panel is populated from the recording rather than from anything invented for
the occasion.

Pointed at a repository with no recordings while replaying, the interface says
so before the run starts, because a review that maps files, misses every model
call and reports nothing is otherwise indistinguishable from a broken model.

The interface needs Node to build, once; the engine does not need it at all,
and every number this README publishes comes from the CLI.

### Two models, if you want them

Triage is asked once per file — *which concerns does this file touch* — and it
is the highest-volume call in a review and the least demanding. It can be
given a smaller model:

```bash
AUGURY_MODEL=openai/gpt-oss-120b AUGURY_TRIAGE_MODEL=openai/gpt-oss-20b ./start.sh --live
```

Unset, triage uses the reviewing model, which is what every recording here was
made against. The reported cost sums both models: splitting the work must not
be able to hide half the bill, and for a while it did.

What the interface adds is watching. It subscribes to the trajectory the
reviewer writes anyway, which is the file handed to a judge, so the tree
lighting up and the agents handing off are the run rather than an animation of
one. When the pipeline stops emitting, the screen stops moving. The raw event
stream sits beside the rendered view for exactly that reason: a reader should
be able to check that the diagram is not a cartoon over a spinner.

---

## Point it at your own service

```bash
augury survey --path /path/to/repo --scope backend
```

Free, no API key, a few seconds. It reads `docker-compose.yml` first, so before
spending anything it can tell you which directories hold services, what each
one runs, what they depend on, and how much of the repository a request can
actually reach. On the production service used throughout this README:

```
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ service           ┃ built from ┃ runs                      ┃ capacity        ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ api               │ backend    │ serves :10000             │ -               │
│ worker_default    │ backend    │ celery worker -Q default  │ --concurrency=1 │
│ worker_alignment  │ backend    │ celery worker -Q alignment│ --concurrency=1 │
│ worker_generation │ backend    │ celery worker -Q generation│ --concurrency=1│
│ worker_evaluation │ backend    │ celery worker -Q evaluation│ --concurrency=2│
│ beat              │ backend    │ celery beat               │ -               │
└───────────────────┴────────────┴───────────────────────────┴─────────────────┘

depends on: qdrant (vector store), redis (cache or queue)

224 modules, 29,576 lines — 224 python
164 reachable from an entrypoint, 60 not, 0 unparsed

schema — 6 findings in the migrations
dependencies — 2 findings
```

That `--concurrency=1` is a capacity ceiling that appears in **no source file**.
Only the deployment declares it.

Then, when you want the model involved:

```bash
augury review --path /path/to/repo --scope backend --budget 0.25   # ranked table
augury report --path /path/to/repo --scope backend --out review.md # a document
```

`report` is for a codebase where a findings table is the wrong artefact. It
writes what the service is, what its deployment declares, what its schema and
dependencies say, the findings in rank order, and -- the section most reports
omit -- how much was never looked at.

---

## Where the interesting part is

The pipeline exists for repositories too large to put in one prompt. That is
worth stating precisely, because it is also the reason the evaluation below
cannot demonstrate it.

On the service above, the baseline arm -- one prompt containing the whole
repository, which is what most AI review tools are -- reaches this much of it:

```
modules in scope                224
modules that fit in one prompt   19   8.5%
modules dropped                 205   did not fit in one prompt
```

One prompt is one prompt. The seeded cases in `eval/` are 3 to 23 modules,
where the baseline sees everything, so the published comparison measures the
two arms in the one regime where the architecture cannot help. That is a real
limitation of the evaluation and it is not fixed by running it again.

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
metrics, configuration and deploy history. Getting that hypothesis wrong is
what turns a twenty-minute incident into a two-hour one, and it is why the
expensive defects are the ones that read correctly line by line.

**This is evidence for an engineer, not a verdict.** Augury produces findings,
measurements and a report; deciding what to change remains a qualified
person's job, and nothing here should be applied to a running system without
one. The design says so on purpose: a claim carries the experiment that tested
it so a reviewer can disagree with the measurement rather than with the
model.

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
each module touches. Deterministic; no model call. Two of those six are
measured end to end by the evaluation: `E01-go-inventory`, a Go service with
eight seeded defects and a clean `go vet`, and `F01-ts-checkout`, a TypeScript
Express service with eight, which `tsc --noEmit` accepts under strict. The
other three are exercised by unit tests over their parsers and signal
detectors, which is a weaker claim and is worth reading as one.

What those detectors read is the source, not only the import list, because
the constructs that matter most import nothing. A goroutine is `go func`. A
lock is `synchronized`. An escape from Rust's guarantees is the keyword
`unsafe`. An unbounded copy is `strcpy`, from a header the file already
needed. Java's `Runtime.exec` lives in `java.lang`, which is imported
implicitly and therefore appears in no import list anywhere.

Each of those was measured raising nothing before it was added, and each is
anchored on syntax rather than on a word: routing a file to a specialist
costs a model call, so a rule that fires on "go" in a sentence spends money
to be told nothing. Fourteen such guards are held by tests.

Adding those two cases found three defects in this stage that no Python case
could reach. The import graph was empty for every language but Python, so
fan-in was zero, nothing was reachable from an entrypoint, and the scheduler's
boost for a module importing something already found defective never fired.
`fetch` is a global, so the most common outbound call in TypeScript raised no
signal and the module making it went unread. And a synchronous call on a
single-threaded runtime — the one hazard the practice lab singles Node out for
— routed nowhere.

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

Six cases, twenty-nine seeded defects across Python, Go and TypeScript, five
runs per arm, every prediction put to the case's own experiments.
`openai/gpt-oss-120b` on Groq at temperature 0.

**The primary metric is hit rate:** of the claims that were falsifiable enough
to test, what share survived an experiment that tried to refute them. It is
the primary one because it is the only metric here that measures whether the
reviewer was *right*, which is the thing the user needs and the thing every
other reviewer on the market leaves unmeasured. Recall counts what was named,
precision counts what was well-formed; only hit rate counts what was true.

**What was defined as a good result, before the sweep ran:** the pipeline
ahead of the baseline on hit rate at equal or better recall, on at least four
cases, at a cost premium under 10x. Recorded here because a target written
afterwards is not a target. **The observed result meets two of those three and
misses recall**, and the margin has changed direction five times in six cases,
so the honest reading is in the paragraphs below the table rather than in the
table.

**Read this section knowing what it measures.** The seeded cases are 3 to 23
modules. A repository that small fits in one prompt, so the pipeline's whole
reason for existing -- deciding what to read when you cannot read everything --
is dead weight there, and the numbers below say so: the baseline wins on every
metric. That is a real result and it stays published. It is also a result about
a size of repository nobody hires a reviewer for. The regime this was built for
is [further down](#on-a-production-service-nobody-seeded), and the two sections
disagree, which is the point of having both.

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

### The result, on six cases

A sweep was recorded call by call and the recordings committed, so this is
reproducible exactly, with no API key: `make eval-replay` prints these numbers.

| metric | baseline | augury |
|---|---|---|
| seeded recall | **0.828** | 0.759 |
| falsifiable precision | **0.679** | 0.675 |
| hit rate | 0.750 (6/8) | **0.857** (6/7) |
| experiments run | 8 | 7 |
| prediction coverage | **0.421** | 0.296 |
| experiments that broke | **4** | 6 |

**This margin has moved every time the suite has.** On four Python cases the
pipeline led on precision, 0.690 to 0.667. A Go service put the baseline ahead,
0.696 to 0.629. A TypeScript service put the pipeline back in front, 0.675 to
0.643. Then teaching the Cartographer to see concurrency primitives in source
— a `go func`, a `synchronized`, a `std::thread` — moved the baseline to 0.679
against 0.675, which is a tie in everything but the third decimal.

That last change is worth reading as a capability rather than a score. The Go
case seeds a goroutine leak, and the file that contains it was raising `data`
and `observability` and never reaching the concurrency specialist. It is now
found: E01 recall went to 7 of 8.

Read that as a warning about the sample size rather than as a result. The
margin has now changed direction five times over six cases. What it does say,
consistently, is that neither arm is dominating: the baseline reads everything
and finds slightly more, the pipeline reads a fraction and is slightly more
often right about what it finds.

**One number got worse and the cause is not established.** Experiments that
broke rose from 1 to 6 for the pipeline while the baseline held at 3. Docker
was running for the second sweep and not the first, but the baseline's count
was unchanged across exactly that difference, so the container path is not the
explanation. The likeliest remaining one is that the pipeline's claims changed
when the recordings were refreshed — the memo cache used to answer during
recording and no longer does — but that has not been demonstrated, and it is
recorded here as an open question rather than an explained one.

```
hit rate  repeats not independent: p = n/a  not measured
recall    repeats not independent: inconclusive
```

Cost is not in that table because replay is free, which is what makes it
reproducible without a key. On the recording run the baseline spent $0.0108 and
the pipeline $0.0582.

#### The comparison in the shape the brief asks for

| metric | simple baseline | agent solution | change |
|---|---|---|---|
| **primary outcome** — hit rate | 0.750 (6/8) | **0.857** (6/7) | **+0.107** |
| human time per task | ~35 min | ~45 s of attention | **−97%** |
| cost per task | $0.0018 | $0.0097 | **5.4x** |

*Human time per task* is the one estimate in this document rather than a
measurement, and it is marked as such. The baseline figure is how long it took
me to read one case repository and write down its defects by hand while
building the suite; the agent figure is wall-clock attention, not wall-clock
runtime — a six-case sweep takes 4 to 12 minutes but wants nothing from you
while it runs. Treat it as an order of magnitude, not a number.

*Cost per task* is measured: $0.0108 and $0.0582 over six cases.

Reproduced from a fresh clone of this repository, which is the only test of
that claim that counts. Every figure matches except the hit rate, which came
back 7/7 rather than 6/7: one of the seven experiments measures a lost update
and its number depends on how the concurrent writers interleave, so its verdict
can land either way. It is declared as such in
[`tests/test_experiments_discriminate.py`](tests/test_experiments_discriminate.py),
which exempts it from reproducing exactly and still requires it to detect the
defect on every run. A hit rate over seven experiments inherits that: it moves
by 0.14 when that one changes its mind, which is another way of saying seven
experiments settle very little.

**The pipeline arm leads for the first time, and one run of seven experiments
is not a finding.** Read the two lines under the table before the two in it:
the seeds are not independent, so nothing here is significant, and a hit rate
over seven experiments moves by 0.14 if one of them changes its mind. The
honest statement is that the gap reversed after the specialists were given the
lab, not that the architecture won.

**What changed was what the specialists know.** Three things landed together:
the twenty-five mechanisms an audit found missing from the layer briefs, a real
corpus, and eight metrics the lab's mechanisms needed in order to be stated at
all. The corpus is the one worth naming. The prompt had always said its
reference material "comes from a practice lab written before this review
existed, and they are the source of your authority -- cite them", and it was
handed the specialist's own brief a second time under that heading. The
specialist had a brief and no corpus, and was invited to attribute the brief to
a lab it had never seen.

**Seeded recall is now level, and it was not before.** The prompts told both
arms which of `value` and `upper` had to be larger only after a real run
withdrew eight predictions in a row for getting it the wrong way round. Saying
so moved the pipeline arm from 0.692 to 0.769 and left the baseline where it
was. That is a fact about the instructions, not about the architecture, and it
is the third time on this project that a gap between the arms turned out to be
a gap in what one of them was told.

**The pipeline arm's precision fell after these numbers were last published,
because a bug in this project's favour was fixed.** `collapse`, which merges
one sentence about sixteen files into one finding, ran on the pipeline arm and
not on the baseline, and the findings it merged away entered no list at all.
Falsifiable precision divides by findings plus discarded, so every collapsed
finding quietly left the denominator. Counting them again cost this arm about
nine points, with nothing about the reviewer changed.

**The baseline wins on cost, on coverage and on recall.** One prompt
containing the whole repository finds more of the seeded defects, states a
higher share of testable claims, gets more of them measured, and does it at a
fifth of the price. What it does not win on is being right: the pipeline leads
on hit rate, 0.857 against 0.750, and precision is a tie in the third decimal.

That is the whole finding, stated at the size it actually is. The pipeline
reads a fraction of the repository and is somewhat more often correct about
what it reports. Whether that trade is worth five times the price is a
question about repository size, and this suite is too small to locate the
crossover.

#### The fourth case erased the pipeline's only lead

On three cases the pipeline led on hit rate, 5/5 against 5/6. This document
said, in the section below and in the changelog's open questions:

> The margin is one experiment. A single measurement moving would erase or
> double it. It needs a fourth case, not a sixth repeat.

So a fourth case was built -- D01, a search-index service, chosen partly
because its first defect is the only one in the suite that measures
`memory_bytes`, a metric the published vocabulary had carried since the start
and no case had ever settled. On four cases the hit rate went to 1.000 against
0.600, and the lead was not merely gone but reversed.

It has since reversed again, to 0.750 against 0.857, after the specialists were
given the lab they had always been told they were citing. Then a fourth time,
on precision, when the suite stopped being entirely Python: one Go service put
the baseline back in front, 0.696 against 0.629. Then a fifth, when a
TypeScript service put the pipeline in front again, 0.675 against 0.643.

A margin that has moved five times, over seven or eight experiments and six
cases, is not a measurement of an architecture. It is a measurement of how
little six cases can settle. The last two moves are the most informative,
because neither came from tuning anything: both came from measuring a claim
the suite had never tested.

The prediction that preceded the first reversal is the part worth keeping: the
margin was named as too small to survive more data,
before the data existed, and it did not survive it.

**Read `prediction coverage` beside the hit rate.** The pipeline had 43.8% of
its falsifiable claims graded against the baseline's 80.0%. It writes more
claims, aimed at metrics and files the cases do not measure, so most of them
are never settled either way -- and the ones that were settled it got wrong
more often. A hit rate over five experiments is five observations; treat the
gap as a direction, not a measurement.

#### Recall, audited by hand (the three-case run)

The audit below was done on the three-case sweep that preceded D01. It is kept
because what it shows about the matcher does not depend on the case count.

Recall is matched by prose against a manifest, and prose matching cannot tell a
correct diagnosis from a wrong one that mentions the right word. So all sixteen
matches in the run above -- eight per arm -- were read by hand. One is wrong:

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

**The pipeline does not beat one well-written prompt.** On four cases it is
behind on every published metric: it finds fewer of the seeded defects, states a
lower share of testable claims, gets far fewer of them measured, is right about
fewer of the ones that are measured, and costs four times as much.

It held one nominal lead on three cases. Building a fourth case removed it.

It is also not shown to be worse. Ten seeded defects over three cases cannot
resolve a difference this size in either direction, and saying so is the honest
end of this experiment rather than a hedge before a claim. `significance.verdict`
returns "no detectable difference" and never "no difference", and on this run it
returns "not measured" instead, because a study too small to find a difference
has not shown there is none.

That is the result. It is not the one this was built to produce, and it is the
one the evidence supports.

A note on the case set. **A04 is pooled into these numbers and should not carry
weight**: its own manifest calls it too easy to distinguish the arms, both
score 1.000 on it, and it ships no experiments, so it pulls both arms toward
parity. Dropping it changes nothing that matters -- on B01 and C01 alone recall
is 0.778 for both arms, and the hit rates are identical to the pooled figures,
5/6 against 5/5, because A04 contributes no tested predictions at all.

### The finding is about measurement, not about agents

Five times this comparison appeared to have a winner, and five times the
harness was wrong:

| claim | why it was withdrawn |
|---|---|
| hit rate 0.000 vs 0.750 | measured at a third of the coverage; reversed when two experiments were added |
| the arms differ in consistency | the variance was substring matching, not the reviewers |
| hit rate 0.480 vs 0.703 | three of five experiments reported the same number on remediated code |
| falsifiable precision 0.682 | findings merged by `collapse` left the denominator, on the pipeline arm only |
| the gate rejects vacuous claims | it rejected `>= 0`, and `>= 0.000001` hits every measurement ever taken |

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
make check                # lint, types, 1438 tests
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

## On a production service nobody seeded

The seeded cases and the 533-module run above are both small enough that the
architecture is overhead. So it was pointed at a service the author has worked
on for months -- a FastAPI backend with four Celery workers, Redis and Qdrant --
with no budget ceiling. The command was:

```bash
augury report --path ../Interview-AI-Prod --scope backend --budget 0
```

| | |
|---|---|
| modules in the repository | 421 |
| in scope (`--scope backend`) | 224 |
| reachable from an entrypoint | 164 |
| modules read | **147 (66%)** |
| findings | 141 |
| cost | **$0.51** |
| wall clock | 7m51s |

It stopped on its own, and the reason it printed is the interesting part:
**"stopped because nothing left worth reading."** The 77 modules it skipped are
migrations, one-off scripts and `__init__.py` files; the Scheduler ranked them
below the threshold and never spent a call on them. That ranking is the
component the seeded cases cannot measure, because at 23 modules there is
nothing to rank.

Three things in that report exist in no source file and could only come from
reading the deployment:

- Three of the four Celery workers run `--concurrency=1` and the fourth at 2.
  That ceiling is declared in `docker-compose.yml` and nowhere in the code, so
  a reviewer that reads only source is blind to it -- and it is the number that
  decides how much queued work the service can actually clear.
- Six migrations do something to a table with rows in it -- a `NOT NULL` with
  no default, an index built without `CONCURRENTLY`. Found by parsing
  `upgrade()` without importing it.
- Six dependency findings, checked against PyPI at run time rather than against
  the model's training data.

Those twelve cost nothing: they come from the deterministic passes, before any
model call.

**The honest limit:** the 141 findings are not scored. There is no ground truth
for a repository nobody seeded, and hand-scoring 141 findings is a week of work,
not a weekend. What is verified here is the coverage, the cost, and the twelve
deterministic findings -- the part a reader can check without trusting anybody's
judgement. Three earlier attempts at this same run sit in the journal with no
completion time; they are real, and they died on provider rate limits before the
backoff was written.

## Which model, and what it costs

Four providers are supported. The choice is one environment variable, and it
matters more than the price list suggests:

```bash
AUGURY_PROVIDER=groq      AUGURY_MODEL=openai/gpt-oss-120b
AUGURY_PROVIDER=deepseek  AUGURY_MODEL=deepseek-v4-flash
```

The same scope of the same repository, the same $0.15 ceiling, run back to
back:

| | Groq `gpt-oss-120b` | DeepSeek `v4-flash` |
|---|---|---|
| modules read | **24 of 39** | 2 of 39 |
| findings | **34** | 6 |
| spent | **$0.135** | $0.196 |
| wall clock | **129s** | 265s |
| per module | **$0.0056** | $0.098 |

Eighteen times the cost per module, from the model with the lower published
price per token. DeepSeek v4-flash is a reasoning model and the chain of
thought is billed as output: one call spent 23,000 characters thinking before
it began the answer, and the answer was 2,900. A price list per million tokens
does not tell you how many tokens a question will cost.

This is why the budget is enforced against a measured rate rather than a
configured one. The first version of that ceiling was a fixed $0.02 per 1000
lines, which is about right for Groq and about ten times too cheap for
DeepSeek -- so a review asked for $0.15 and spent $0.80 before anyone noticed.
It now reads two modules, measures what they cost, and plans with that.

DeepSeek is the configured default and Groq is one environment variable away.
Which is right depends on what you are buying: Groq reads more of a repository
per dollar, and DeepSeek is a different family of model entirely, so a finding
that survives both is not an artefact of one provider's habits. What should not
happen is choosing either from the price list alone, which is what the table
above is here to prevent.

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

The second failure mode is cheaper to state: on the seeded cases, routing to
specialists costs six times a single prompt for no measurable gain. The
Scheduler exists for repositories too large to read at once, and twenty-three
modules is not that. That sentence used to end "and this evaluation cannot
separate them" -- it now can, because the run below was done: at 224 modules
a single prompt reaches a handful of them, and no amount of model quality fixes
a denominator.

## Hot take

**Everyone building AI code review is measuring whether the reviewer named the
defect. That is the easy half, it is nearly free to score, and it is why the
tools do not get better. The hard half is whether the reviewer's claim is true
— and almost nobody builds the apparatus to find out, because the moment you
do, it starts telling you things you did not want to hear.**

This project built the apparatus and then published what it said, including
that the architecture it was built to demonstrate does not clearly beat one
prompt. The full argument, with the four experiments that measured the harness
instead of the code, is in [`docs/HOT_TAKE.md`](docs/HOT_TAKE.md).

---

## What existed before

The engineering knowledge, the compose harness and the load scenarios come from
a multi-layer software engineering practice lab that predates this competition.
Everything under `src/`, `eval/` and `tests/` was written for it. The full
accounting is in [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
