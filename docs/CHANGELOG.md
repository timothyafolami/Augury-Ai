# Improvement Changelog

Every entry below came from a run that failed or disappointed, not from a
plan. Each names what was tried, what the evidence said, and what was decided.
Entries that made things worse, or that turned out to measure nothing, are kept
in place rather than removed: they are the ones that say most about the
problem.

Model throughout: `openai/gpt-oss-120b` on Groq, temperature 0.
Cases: `A04` (3 modules, 1 defect, declared non-discriminating), `B01` (23
modules, 5 defects, 1 red herring), `C01` (13 modules, 4 defects chosen to sit
outside the specialist briefs).

---

## Baseline

**What it is.** One prompt, the whole repository in it, no tools, one shot.
What a competent engineer does today. It is asked for exactly what the pipeline
is asked for, including a falsifiable prediction, because a baseline denied the
chance to be falsifiable would lose by construction and the comparison would
prove nothing.

**First number on the board**, on the practice lab's `10-edge/lab/api`:

| | |
|---|---|
| findings | 4 |
| falsifiable precision | 0.750 |
| cost | $0.0025 |
| time | 6.7 s |

**What it taught.** A strong single prompt produces falsifiable-*looking*
claims easily, and correctly withheld a prediction on a swallowed-exception
finding rather than inventing one. So falsifiable precision alone was never
going to be the differentiator. That pushed the headline toward recall and hit
rate, which is a better and more honest story.

---

## Iteration 1 — the reasoning budget

**Tried.** Running the baseline against a real service.

**Evidence.** `json_validate_failed` with an *empty* `failed_generation`. This
reads like a schema problem and is not: gpt-oss reasons before it answers and
spent the whole default output budget doing it, so no JSON was ever emitted.

**Decided.** Kept. `AUGURY_MAX_TOKENS` defaults to 16000, and the reason is
written into `.env.example` so the next person does not lose the same twenty
minutes.

---

## Iteration 2 — cross-file context

**Tried.** The pipeline arm, reading one module at a time under the Scheduler.

**Evidence.** **0 findings, against the baseline's 3.** Triage was routing
correctly; the specialists were declining. Case A04's defect is `pool_size=5`
in `db.py` against `--workers 8` in the `Dockerfile`. Neither is wrong alone.
A reviewer shown only one of them is right to decline, and the baseline gets
the relationship free by putting every file in one prompt.

**Decided.** Kept. Deployment configuration (Dockerfile, compose, manifests) is
collected once and sent with every module. A `.env` is never collected: context
reaches a model and a committed recording, and a secret belongs in neither.

**What it taught.** The module is not the unit a defect lives in. Any
architecture that reads code in pieces has to pay this back somewhere.

---

## Iteration 3 — the strict-schema contract

**Tried.** Re-running after Iteration 2.

**Evidence.** Rejected with `missing properties: 'prediction'`. The model had
produced the finding *and* the arithmetic:

> Effective DB throughput = pool_size / service_time = 5 / 0.1 s = 50 req/s.
> With 8 workers, at 60 req/s the queue delay is 1 s, so p99 > 500 ms.

A correct answer, discarded on a technicality: strict structured-output
providers require every declared property to appear in `required`.

**Decided.** Kept. Optional now means nullable, never absent, across every
model-facing schema. A test asserts it, because the failure mode is a whole
review lost to a schema detail.

---

## Iteration 4 — triage was suppressing the pipeline

**Tried.** Re-running after Iteration 3.

**Evidence.** Triage returned **nobody, for every module**, including the one
holding the defect it had routed correctly a run earlier.

**Cause.** The prompt said "selecting nobody is a valid and often correct
answer" and told triage to be accurate rather than generous. That asks triage
to decide whether a bug exists, which is the specialist's job.

**Decided.** Rewritten to route on **presence, not certainty**. A specialist
that is never called cannot find anything and nothing downstream recovers the
miss, so the asymmetry favours calling it.

---

## Iteration 5 — a prompt that asked for a field the schema did not have

**Tried.** Re-running after Iteration 4. Augury now found the defect and
described the mechanism correctly, but every finding came back unfalsifiable:
**falsifiable precision 0.000 against the baseline's 1.000.**

**Cause.** The analyst prompt told the model to emit `claim`. The schema has no
`claim`. It has `prediction`, which the prompt never mentioned. The model
complied with the prompt, the schema dropped the answer, and **nothing failed
loudly.**

**Decided.** Kept, and generalised: `tests/test_prompt_schema_agreement.py`
refuses any prompt that asks for a field its schema lacks or omits one it
requires. This class of bug is invisible from either side alone, and it should
never again be findable only by hand.

| | before | after |
|---|---|---|
| falsifiable precision (A04) | 0.000 | 1.000 |

---

## Iteration 6 — case A04 was too easy to measure anything

**Tried.** The first honest head-to-head, on A04.

**Evidence.**

| metric | baseline | augury |
|---|---|---|
| seeded defect recall | 1.000 | 1.000 |
| falsifiable precision | 1.000 | 1.000 |
| cost | $0.0012 | $0.0034 |

**Decided.** Reported as a non-result. Three files and one defect is a
repository where reading everything is free, so nothing the pipeline does can
pay for itself. The verdict is written into A04's own manifest so the case
cannot later be cited as evidence of anything.

**Consequence.** Built case B01: twenty-three modules, five defects each traced to
a lab topic, each reading correctly line by line, plus a loud `FIXME: this is
slow` on code that is fine, to see whether a reviewer follows the loudest
signal or the causal one.

---

## Iteration 7 — retries, because a harness failure is not a reviewer failure

**Tried.** The first run on B01.

**Evidence.** Baseline 4 of 5. Augury **0 of 5** -- but not on merit: the model
returned the JSON *schema* instead of an instance (`{"$defs": ...,
"properties": ...}`) and the provider rejected the whole response.

**Decided.** Kept. Bounded retries, and critically the retry prompt *differs*:
repeating an identical prompt to a temperature-zero model repeats the identical
failure, so the correction names the rejection and says to return the instance,
not the schema. Retries are counted so flakiness stays visible instead of being
absorbed.

---

## Iteration 8 — reconciling specialists that collide

**Tried.** B01 with retries in place. Both arms found 5 of 5.

**Evidence.** Augury emitted **eleven findings of which four were duplicates**:
`charge` twice, `quote` twice, `list_for_customer` twice. Different specialists
raised the same construct, all honestly, and all of them were reported. Its
falsifiable precision was *below* the baseline as a result.

**Decided.** Kept. A deterministic reconciler merges findings on file and
symbol, keeping the highest severity and the strictest prediction, and crediting
every specialist that raised it. No model call: a rule that merges on an exact
key cannot hallucinate a merge, and spending a call on it would be waste.

| metric | baseline | augury before | augury after |
|---|---|---|---|
| seeded defect recall | 0.800 | 1.000 | 1.000 |
| falsifiable precision | 0.800 | 0.750 | **0.917** |
| findings | 5 | 11 | 12 |
| duplicates | 0 | 4 | **0** |

**Caveat, and it matters.** The baseline scored 5 of 5 on one run and 4 of 5 on
the next, at temperature zero. A single run of each arm cannot support a claim
about either. See Iteration 9.

---

## Iteration 9 — repeating the runs

**Tried.** Reading the two single-run results above as a win.

**Evidence.** The baseline's own recall moved between runs with nothing
changed. The difference being claimed was smaller than the variance inside one
arm.

**Decided.** Kept as a rule rather than a habit. `SweepResult.compare` returns
`inconclusive` whenever the ranges overlap, so an unsupported win cannot be
reported by accident, and the spread is printed beside every mean.

**Result, three seeds per arm on B01:**

| metric | baseline | augury |
|---|---|---|
| seeded recall, mean | **0.933** | 0.867 |
| seeded recall, range | 0.800 - 1.000 | 0.800 - 1.000 |
| falsifiable precision | 0.397 | **0.768** |
| cost | $0.0041 | $0.0268 (6.5x) |
| time | 10.6 s | 45.9 s (4.3x) |

**Verdict on recall: inconclusive.** The ranges are identical and the baseline
is marginally ahead on the mean. Three seeds each gave 5/4/5 and 4/4/5.

This is the result, and it is worth stating plainly rather than framed: **on a
seventeen-module repository, routing to specialists does not find more seeded
defects than one good prompt.** The extra spend buys falsifiable precision -- a
claim carrying a number, a unit and a condition roughly twice as often -- and
nothing measurable in coverage.

Two honest readings, and the evaluation cannot yet separate them:

1. Seventeen modules still fits comfortably in one prompt, so the Scheduler has
   nothing to earn. The crossover, if it exists, is at a repository size not
   yet tested.
2. The architecture does not pay for itself, and the falsifiable-precision gain
   is the whole return on 6.5x the cost.

The next experiment is designed to distinguish them, not to defend the
architecture.

---

## Iteration 10 — a metric measured at low coverage measured nothing

**Tried.** Reporting the first hit rate, with three experiments shipped.

**Evidence.** Baseline 0.000, Augury 0.750. It went into the README.

**Then.** Two more experiments were added, raising prediction coverage from
0.37 to 0.53. The same comparison, three seeds per arm:

| metric | baseline | augury |
|---|---|---|
| seeded recall, mean | 0.867 | **1.000** |
| seeded recall, range | 0.600 - 1.000 | 1.000 - 1.000 |
| hit rate | 0.571 (7 tested) | 0.500 (10 tested) |
| prediction coverage | 0.64 | 0.42 |
| cost | $0.008 | $0.079 |

**The ordering reversed.** The baseline's hit rate went from 0.000 to 0.571,
not because it improved but because more of what it had always been claiming
became testable. Which third of the predictions happened to have an experiment
had decided the earlier result.

**Decided.** The claim is withdrawn. Nothing was wrong with the scoring code;
the denominator was too small to mean anything and was published anyway. The
floor under a published rate (Iteration 9) exists because of this, and the
README now leads with it as the project's main failure mode.

**What actually separates the arms**, on this evidence: consistency. The
baseline found 5 of 5, 5 of 5, then **3 of 5**. Augury found 5 of 5 every time.
A reviewer that occasionally misses two fifths of what is there is materially
worse than one that does not, and a single run would have shown neither.

Hit rate remains **not distinguishable** between the arms, on seven and ten
tested predictions. Neither denominator supports a claim, and the harness now
declines to print one.

---

## Iteration 11 — the harness could not tell working code from broken code

**Tried.** Publishing the comparison from Iteration 10.

**Evidence.** An adversarial review was pointed at the evaluation rather than
the code, told to break the measurement, and to check each experiment by
writing the remediated version and re-running it. It found:

- `worker_saturation` reported **1.000 for a correctly fixed client**. httpx
  already defaults to a five-second timeout and the experiment's deadline was
  three, so the number was a property of that constant. The seeded "missing
  timeout" was not a defect at all.
- `retry_amplification` reported **3 for a client with backoff, full jitter and
  a retry budget** -- the exact remediation the defect text demands. One
  request only ever measures `MAX_ATTEMPTS`; a budget binds across requests.
- `queries_per_request` reported **51 for a repository whose list endpoint had
  been fixed**, because the experiment looped over its own query instead of
  calling the endpoint. That is the README's hero example.
- Seeded-defect matching was a substring lottery: `except` matched "an
  exception type is not declared", `balance` matched "should load-balance
  across replicas". Five findings describing nothing seeded scored **1.000**,
  and three of the five detections in the committed trajectory were earned
  that way.
- **The comparison was not fair.** Iteration 2 gave the pipeline the deployment
  configuration and never gave it to the baseline, while both were graded on
  arithmetic that needs it. Not a budget constraint: the baseline prompt used
  16,640 of its 120,000 characters.

**Decided.** All fixed, and each is now pinned by a test. The important one is
`tests/test_experiments_discriminate.py`: every case ships the remediated
version of every file it breaks, and every experiment is run against both.

| experiment | seeded | remediated |
|---|---|---|
| `final_balance` | 90.0 | 0.0 |
| `http_status` | 200 | 500 |
| `queries_per_request` | 51 | 2 |
| `retry_amplification` | 3.0 | 1.15 |
| `worker_saturation` | 1.0 | 0.0 |

Three of those columns used to be identical.

**Every number published before this point is withdrawn.** An experiment that
cannot fail on correct code cannot pass on incorrect code either; it just
returns a number.

---

## Iteration 12 — the consistency claim was a matching artefact

**Tried.** The claim from Iteration 10, that the arms differ in consistency
rather than average quality: the baseline scoring 5/5, 5/5, 3/5 while the
pipeline scored 5/5 every time.

**Evidence.** With whole-word matching, the first re-run gave **0.800 recall
for both arms on all three seeds, with zero variance in either.** The variance
the claim rested on was substring matching resolving differently depending on
which words a reviewer happened to use, not the reviewer being inconsistent.

**Decided.** Withdrawn. It was the second claim in a row to come from a
measurement artefact rather than from the arms, which is worth stating plainly
rather than burying: both times the harness was the least trustworthy component
in the experiment, and both times it took an adversarial pass to notice.

**What is left**, on the repaired harness, is a genuine and more interesting
observation: both arms miss exactly one defect and **they miss different ones**.
The baseline misses the N+1, whose loop and query live in different files. The
pipeline misses the retry storm. Neither is better; they fail differently.

---

## Iteration 13 — the hit rate does not survive repetition either

**Tried.** Reading the repaired-harness hit rate as the differentiator: the
first sweep gave the baseline 5 of 10 and the pipeline 10 of 12.

**Evidence.** Re-running the identical three-seed sweep, changing nothing, gave
**6 of 11 for both arms**. The pipeline's hit rate moved from 0.833 to 0.545
between two runs of the same experiment.

**Decided.** No hit-rate claim. Eleven tested predictions per arm cannot
separate them, and the design cannot be argued out of that: B01 seeds five
defects, so a run yields three or four distinct experiments however many
findings it produces. More seeds of one case buys correlated measurements, not
independent ones.

The honest statement is a power statement rather than a result: **this
evaluation, as built, cannot distinguish the arms on any published metric.**
Separating them needs more cases, not more seeds.

---

## Iteration 14 — the experiments were measuring the harness, again

**Tried.** Publishing the C01 comparison.

**Evidence.** Both arms scored a hit rate of **0.000 on C01 across seventeen
tested predictions**, and they were right:

> claim: `queries_per_request at least 101, reporting 100 shipments`
> measured: 41, because the experiment reports 40

Correct mechanism, correct direction, correct file, scored a Miss because the
experiment ran a different scenario than the claim was about. A prediction
carries a condition and the Prover ignored it.

**Decided.** Each case publishes what scenario every experiment runs, to both
arms identically. It reveals which metrics a case can measure; it reveals
nothing about where the defects are or what the numbers should be, and a test
asserts the conditions contain no word like "defect" or "should be". C01's hit
rates went from 0.000 to 0.867 and 0.700 -- the reviewers had never been the
problem.

A second adversarial pass on C01 then found three more:

- **`queue_depth` reported 121 for an unbounded queue and for one bounded at
  512.** It discriminated only against `maxsize=32`, the bound the remediation
  happened to use. It was measuring arithmetic on three harness constants.
- **`active_connections` measured CPython's garbage collector.** One
  `gc.collect()` made the leaking and the correct version identical; the same
  code reported 6, 20 or 0 depending on GC configuration.
- **Recall inverted.** The whole-word matcher rejected `leaks` for the symbol
  `leak`, so a review describing all four defects in natural English scored
  **0.000**, while four findings whose mechanism was a full stop scored
  **1.000**.

All fixed. Inflection counts and derivation does not; a finding must say what
is wrong rather than only where; `queue_depth` offers more events than any
bound and reports the queue's capacity; `active_connections` measures pool
exhaustion, which cannot be collected away. A new test class checks every
experiment against **more than one** remediation, because passing against one
is exactly how `queue_depth` hid.

---

## Iteration 15 — the result

**Three cases, ten seeded defects, five seeds per arm**, on a harness where
every experiment is proven to discriminate and both arms are proven to receive
the same information.

| metric | baseline | augury | verdict |
|---|---|---|---|
| seeded recall | 0.760 | 0.760 | no difference (permutation p = 1.00) |
| hit rate | 0.893 (25/28) | 0.757 (28/37) | no difference (Fisher p = 0.21) |
| cost | $0.036 | $0.216 | 6.0x |

**The pipeline does not beat one well-written prompt**, on either metric, at
six times the cost. That is the finding.

It is worth being precise about what was and was not shown. The pipeline is
not worse: p = 0.21 on a hit rate favouring the baseline is not evidence
either. Ten seeded defects over three cases cannot resolve a difference this
size in either direction, and saying so is the honest end of this experiment
rather than a hedge before a claim.

What the project actually demonstrates is the harness: ten defects that read
correctly line by line, eight experiments that provably distinguish working
code from broken code, and an evaluation that caught its own author being
wrong four times.

---

## A fourth time, caught before publishing

Running `make evaluate` at its default three seeds printed falsifiable
precision of **0.377 for the baseline and 0.852 for the pipeline** -- a gap
more than twice the size of anything else measured here, on the metric closest
to the project's own thesis.

At five seeds it is **0.727 against 0.779, Fisher p = 0.55**. There is nothing
there.

Nothing was fixed in response to this, because nothing was broken. It is
recorded because it is the fourth time a striking number in this project turned
out to be a small sample, and because it took no effort at all to want it to be
real. The only reason it is not in the README is that the habit of running the
test before writing the sentence is now in place.

---

## Iteration 16 — the documented command was not the command that produced the numbers

**Tried.** Submitting.

**Evidence.** A review asked one question: *the changelog credits publishing
each experiment's conditions with the largest movement in this project, so
show the line where `make evaluate` does that.*

There is no such line. The commit named "Give both arms the case's experiment
conditions" patched the `review` command and never touched `_one_run`, so the
sweep sent both arms

> (this repository ships no experiments, so no claim about it can be settled)

for cases shipping nine, and then graded the resulting claims against those
nine. No test reached that construction, which is how one commit could claim
two paths and fix one.

**The published numbers were not affected** -- they came from a script that
passes the conditions -- but the documented command could not reproduce them,
which is the same failure wearing different clothes. The whole argument of this
project is that a number is worth what the reader can check.

**Decided.** Fixed, with a test on the construction. The results table now
publishes what `make evaluate` prints, and states the spread observed between
runs rather than a single point estimate.

Three presentational corrections from the same review, all of which ran toward
asserting equivalence rather than superiority:

- `verdict()` returned **"no difference"** for any p above 0.15. For a project
  arguing that the measuring apparatus is what to distrust, an apparatus
  converting absence of evidence into evidence of absence was the most
  attackable line in it. It says "no detectable difference" now, and a test
  refuses any verdict that asserts the null.
- "produces more findings of the same quality" was an equivalence claim drawn
  from p = 0.21, on a metric whose point estimate favours the baseline by 13.6
  points.
- A04 is pooled into the headline. Its own manifest says it cannot distinguish
  the arms; both score 1.000 on it; it ships no experiments. Including it pulls
  both arms toward the null being reported. It is now marked as carrying no
  weight, with the two-case figures quoted beside it.

---

## Removed

Nothing yet. When something is removed, it stays listed here with what it cost
to learn.

---

## 17. Pointed at a repository nobody prepared

**What prompted it.** Every number in this file came from cases where this
project planted the defects and the grader held the answers. That is the right
way to measure a difference between two arms. It is not evidence that either
arm is useful, and after sixteen iterations of tightening the apparatus, the
apparatus was the only thing that had ever been tested.

**What was tried.** The practice lab: 533 modules, six languages, no seeded
defects, no answer key, a $0.05 budget. Then every finding scored by hand
against the source, because there was nothing else to score it against.

**What the evidence said.** It read 14 of 533 modules (3%) and stopped saying
so. Ten findings. Four correct and verified. Two true about the code and wrong
about what the code was for -- missing auth on a docker-compose lab fixture,
a default password in a localhost config table -- both reported `high`. Three
needing an experiment that does not exist, scored as neither. One false:

> `active_connections at_least 1 count @ DATABASE_URL='http://169.254.169.254/'`

described as SSRF. The value is used as an asyncpg DSN; asyncpg will not fetch
an HTTP URL. The claim is confidently and completely wrong, and it carries a
metric, a comparator, a value, a unit and a runnable condition. It passed the
falsifiability gate without a murmur.

**What was decided.** Publish it, in [`FIELD_RUN.md`](FIELD_RUN.md), including
the false one. Two things it settled that the seeded cases could not:

- **The gate is not a truth filter and was never described as one, but the
  report format invites the confusion.** A well-formed wrong claim is visually
  identical to a well-formed right one. Only the Prover separates them, which
  is the same conclusion the evaluation reached from the other side.
- **Bind findings on symbols, not lines.** Every finding named the correct
  function. One was reported 140 lines from where the function actually is.

**What is still wrong.** Nothing in the pipeline reads what a repository is
*for*, so a lab fixture and a payment service get the same security brief.
That is the cause of both context-blind findings, and it is not fixed.

---

## 18. The five seeds were one call repeated

**What prompted it.** Wiring replay so a judge can reproduce without a key.
The recording ran, and the resulting table had zero spread: recall
`0.700-0.700` and `0.800-0.800` across five seeds, against a live run whose
seeds visibly differ.

**What the evidence said.** The cassette keys on (model id, prompt, schema).
Five seeds collapsed to one recording, which means all five sent byte-identical
prompts. Reading `runner.run_arm` confirms it: `seed` is passed straight to
`score(...)` as a label and reaches nothing else. It does not vary the prompt,
the temperature, the case, or the order modules are read in.

**What was decided.** The cassette is right and the vocabulary was wrong. The
seed-to-seed range in the published results measures **provider
nondeterminism at temperature 0**, not sampling variation, and the README now
says so in those words. `tests/test_what_a_seed_varies.py` pins it: the label
reaches the score, and every repeat receives an identical case.

This also explains something previously recorded as unexplained -- that point
estimates moved by several points between whole runs while the within-run
range looked tight. Both numbers were measuring the same thing, at different
sample sizes, and neither was measuring the harness varying anything.

**What it costs.** `make eval-replay` reproduces a run in which all five
repeats are identical, because that is what the recording contains. It
reproduces the pipeline, the routing, the findings and the grading exactly and
for free; it cannot reproduce provider jitter, which is by definition not
recorded. Said plainly in `REPRODUCE.md` rather than left for a judge to
notice from a suspiciously tidy table.

---

## 19. Two review agents, and what they found in a day-old codebase

**What prompted it.** The MCP server, the replay wiring and the symbol locator
were all written in one sitting, all with tests written first, all green. Two
agents were pointed at them: one told to break the code, one told to check
every documented claim against the code by running it.

**What the evidence said.** Twenty-four defects between them. The ones worth
recording here are the ones a passing test suite actively concealed.

*The seal that was not sealed.* Replay's guarantee is that a missing recording
stops the run rather than falling through to a provider. The reviewer replaced
`SealedModel`'s two methods with ones returning empty objects and ran the
suite: **465 passed.** No test constructed the class. Replay could have
fabricated answers at $0.00 and been indistinguishable from a correct free
reproduction -- the mock-that-lies shape again, at the exact point this project
has already been burned by it, in code written the same day as a document
describing that risk.

*The enforcement that enforced nothing.* `test_no_module_outside_the_provider_
calls_build_model_directly` matched only a bare `build_model(...)`. The reviewer
added a module calling `provider.build_model(...)` -- the mistake as anyone
would actually write it -- and the test passed.

*The locator made lines worse.* It was added because findings named the right
function and the wrong line. On a shadowed name it returned the first match, so
a correctly-named line 47 became line 2 with the authority of "the parser
confirmed it". Seven of its nineteen declared node types could never match at
all, and its one-case-per-language suite reported full six-language coverage.

*The cost bug, again.* `CassetteModel` bracketed the inner adapter's cumulative
usage counter -- exactly what `provider.py`'s docstring says not to do, three
files away, in the comment explaining why `Completion` exists. Two concurrent
$1.00 calls reported $3.00. Record mode is the only mode that reports a
non-zero cost and it was the one inflating it, which means the recorded cost
figures published before this were wrong and the cassettes were re-recorded.

*A batch killed the server.* A JSON-RPC batch is a top-level array; several MCP
clients send one. `handle` did `request.get("id")` and the AttributeError
escaped the stdio loop, ending the session. The only transport test sent four
well-formed objects.

**What was decided.** All twenty-four fixed, each with a test that fails
against the old behaviour. The pattern across them is one thing: **every defect
lived in the gap between what a docstring promised and what a test checked.**
The docstrings were accurate about the danger and no test held anyone to them.

**What it cost to learn.** Two agents, about half an hour of wall clock. That
is cheaper than the four withdrawn claims in this file, each of which took a
full evaluation run to discover.

---

## 20. The comparison was unfair, and fixing it reversed a result

**What prompted it.** A review of the prompts, asked one question: is anything
present in the analyst's instructions and absent from the baseline's?

**What the evidence said.** Four asymmetries, every one favouring the pipeline.

1. `analyst.md` stated exactly what the falsifiability validator rejects -- a
   threshold of zero, a band wider than a hundredfold. `baseline.md` did not.
   A rejected prediction lands in the falsifiable-precision denominator, so one
   arm held the answer key to a metric both arms are scored on.
2. `to_report` keeps a finding whose prediction failed validation *and* records
   a `Dropped` for it, and `aggregate` added both. A malformed prediction cost
   two observations; no prediction cost one. The arm not told the rules
   produced more malformed predictions and was charged double for each.
3. `reconcile` ran on the pipeline arm only. It is deterministic, costs no
   model call, and removes duplicate findings from the denominator.
4. `baseline.md` said to omit `prediction` entirely when none could be derived.
   The schema requires the field and permits null; strict providers reject the
   whole response, and this arm is a single call, so a rejection can cost the
   run.

Two tests were enforcing the asymmetry rather than catching it.
`test_the_analyst_is_told_what_a_vacuous_prediction_is` asserted the rule for
one arm by name. `test_a_prompt_describes_every_field_the_schema_requires`
accepted a `nested` schema argument and never used it, so a prompt describing
none of the six prediction sub-fields passed -- and `baseline.md` was in
exactly that state.

**What happened when it was fixed.**

| metric | before (unfair) | after (fair) |
|---|---|---|
| seeded recall | 0.800 / 0.900 | 0.800 / 0.800 |
| falsifiable precision | 0.778 / **0.833** | **0.909** / 0.583 |
| hit rate | 0.833 / 0.889 | 0.833 / **1.000** |

The falsifiable-precision result **reversed**. The pipeline's advantage there
was the coaching. Recall converged to a tie. And the hit rate separated in the
other direction: 30 of 30 against 25 of 30, Fisher p = 0.052, which the harness
reports as *suggestive, not significant* and which is the correct thing to say.

**What was decided.** Republish all of it, including the reversal. This is the
fifth claim this file has had to withdraw, and the first where the correction
made the pipeline look worse on a metric it had been winning.

**What it means.** The pipeline states fewer testable claims and a higher share
of the ones it states survive measurement. That is a coherent trade rather than
a contradiction, and it is not the trade the project set out to demonstrate.
One sweep at these denominators cannot establish it either way.

---

## 21. The one result favouring the pipeline was one observation counted five times

**What prompted it.** An adversarial review of the evaluation harness itself --
the code that decides every published number -- with one instruction it had not
been given before: mutate a constant, run the suite, and report every mutation
that stays green.

**What the evidence said.** Two defects, both in numbers published an hour
earlier, both found by mutation rather than by reading.

*The Fisher test was unguarded.* Iteration 18 established that repeats are not
independent under replay, and guards were added to `compare` and to
`recall_permutation_p`. `fisher_exact` was left un-guarded, and it was the one
being handed pooled counts. The observation is 5 of 6 against 6 of 6; pooling
five identical repeats made it 25 of 30 against 30 of 30, and

    fisher_exact(30, 30, 25, 30) = 0.0522
    fisher_exact(6, 6, 5, 6)     = 1.0000

The published "suggestive, not significant" was one observation counted five
times. It was the only result in this project's history pointing at the
pipeline.

*The denominator fix never reached the number.* Iteration 20 changed the
falsifiable-precision denominator in `score()`. The published figure comes from
`aggregate()`, which was not touched and still carried the old expression. The
test written to catch this -- `test_aggregate_agrees_with_the_single_score` --
used a report with zero falsifiable findings, where 0/1 and 0/2 are both 0.0.
Published 0.583; correct 0.667.

**What was decided.** `observations` is now carried on `Score`, computed once,
so the metric cannot have two definitions again. Pooling counts one repeat when
the repeats are not independent, and the same guard now covers the cost and
duration means, which were reporting a fifth of one sweep. `prediction
coverage` and `broken` are printed: they were computed and withheld, and the
hit rate cannot be read honestly without knowing that one arm was graded on 43%
of its claims and the other on 60%.

**The result.** No metric separates the arms. Recall identical, precision to
the baseline, hit rate to the pipeline by a single prediction with no p-value
attached. The honest statement is the one the harness now prints on every row:
not measured.

**What it says about the method.** Of 36 mutations applied to the scoring and
significance code, 33 were killed by the suite. Three survived, and those three
are precisely how two wrong numbers reached the README. A test suite that kills
92% of mutations is not a test suite that protects the published result; the
8% it misses is not randomly distributed, it clusters exactly where the tests
were written to confirm a fix rather than to falsify one.

---

## 22. Two more units that were wrong, both found by the same review

**What prompted it.** The same adversarial pass that produced iteration 21 had
five findings left in it.

**The hit rate was a rate over findings.** `_distinct_experiments` was written
because "one k6 run can answer twenty findings that share a mechanism, and
counting it twenty times inflates the denominator by the reviewer's own
verbosity". That argument was applied to the gate that decides whether a rate
may be published and never to the rate. On the published run two of the
pipeline's B01 findings both predict `queries_per_request` and are both settled
by one measurement, so one experiment moved two units on one arm and one on the
other. Scored at the unit the module already argued for, the margin is 5/5
against 5/6 rather than 6/6 against 5/6.

An experiment counts as a hit only when every claim it settled held. Anything
weaker lets an arm buy a hit by pairing a correct prediction with a wrong one
the same run decides.

**`reconcile._strictest` ranked malformed predictions best.** It selects the
narrowest `BETWEEN` band, and the shapes `Prediction` rejects -- an upper bound
at or below the lower, or none at all -- have width zero or less. Reconcile runs
on the draft, before validation, so a malformed sibling selected itself and
discarded a valid prediction with it. Only an arm producing two findings at one
construct can reach this, so it fell on the pipeline alone.

**What was decided.** Both fixed. Both moved the numbers against the pipeline
or, in reconcile's case, removed a penalty that had been applied to it. The
published table has now been corrected four times in two days, every time by a
review rather than by reading, and every correction has moved the result toward
"no difference".

**The pattern is the finding.** Across four adversarial reviews, every defect
that changed a number was found by mutation testing or by an agent told to
break something. The defects found by reading were cosmetic. A suite that kills
92% of mutations does not protect a published result, because the 8% it misses
is not randomly distributed: it sits exactly where a test was written to
confirm a fix rather than to falsify one. Three of the fixes in this changelog
shipped with tests that passed without the fix working.

---

## Still open

- The pipeline costs five times the baseline. It finds the same defects, states
  fewer testable claims, and -- on one sweep, at p = 0.052 -- is right more
  often about the claims it does state. Either that last effect is real and the
  crossover is at a repository size not yet tested, or it is noise and the
  architecture does not pay for itself. Ten seeded defects over three cases
  cannot separate those, and neither can more repeats of the same cases:
  repeats vary nothing but the provider.
- The one result now pointing at the pipeline is the one least able to bear
  weight. 30/30 against 25/30 is a five-prediction margin, and a single tested
  prediction moving would change the p-value materially. It needs a fourth
  case, not a sixth repeat.
- Two metrics in the published vocabulary, `http_req_duration_p99` and
  `memory_bytes`, have no experiment in any case. A prediction naming one of
  them is Broken however good it is, so which metric an arm happens to choose
  partly decides whether its claim reaches the hit-rate denominator at all.
  This is the Iteration 10 artefact, reduced but not gone.
