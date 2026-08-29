# Improvement Changelog

Every entry below came from a run that failed or disappointed, not from a
plan. Each names what was tried, what the evidence said, and what was decided.
Entries that made things worse, or that turned out to measure nothing, are kept
in place rather than removed: they are the ones that say most about the
problem.

Model throughout: `openai/gpt-oss-120b` on Groq, temperature 0.
Cases: `A04` (3 modules, 1 defect), `B01` (17 modules, 5 defects, 1 red herring).

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

**Consequence.** Built case B01: seventeen modules, five defects each traced to
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

## Removed

Nothing yet. When something is removed, it stays listed here with what it cost
to learn.

---

## Still open

- The pipeline costs roughly seven to ten times the baseline for a result that
  is not yet distinguishable from it beyond noise. Either the crossover is at a
  repository size not yet tested, or the architecture does not pay for itself,
  and both answers are worth reporting.
- The Prover is not built, so no prediction has yet been tested against a real
  measurement. Hit Rate is currently unmeasured for both arms.
