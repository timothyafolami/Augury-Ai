# The falsifiability gate

**This is not a prompt. Nothing sends it to a model.**

It was written as one — a Refiner agent that would read each finding and decide
whether it could be made testable. It is kept, rewritten, as the specification
of what replaced it: every rule below is enforced by a pydantic validator on
`Prediction` in `src/augury/core/schemas.py`, and by `_validate` in
`src/augury/core/drafts.py`.

The reason it is a validator and not an agent is worth stating, because it is
the whole architectural argument of this project in one example: **a rule that
can be written down does not need a model to apply it, and a model applying it
can be talked out of it.** A gate that costs a model call per finding, varies
between runs, and can be argued with is worse than one that cannot.

An earlier version of this file described a gate that does not exist. It is
recorded in `docs/CHANGELOG.md` because a document that confidently describes
the wrong rule is exactly the failure this project is about.

## What a prediction must have

All four, all present, or it does not validate:

- a **metric** from the published vocabulary in `src/augury/core/metrics.py`.
  Nothing else can be measured, because the metric names the experiment.
- a **comparator**: `at_least`, `at_most`, or `between`
- a **value with a unit**: `1000 ms`, `51 queries`, `8 to 27 x`
- a **condition** it holds under: `rate=250rps`, `50 rows`, `two concurrent
  writers`

## What is rejected, exactly

A prediction has to exclude some part of the outcome space. These do not:

| shape | why it is refused |
|---|---|
| `at_least` with value ≤ 0 | every measurement of a magnitude is at least zero |
| `at_most` with value ≥ 1e9 | no realisable measurement exceeds it |
| `between` with a lower bound ≤ 0 | a band starting at zero excludes nothing |
| `between` spanning more than 100x | a band that wide admits almost every outcome |
| `between` with no upper bound, or an upper below the lower | nothing could Hit |

The first version of this validator rejected the never-hit shape — an inverted
band — and accepted the always-hit shape. That asymmetry was fatal: a reviewer
emitting only `p99 >= 0ms` scored a perfect hit rate while saying nothing, and
beat an honest reviewer on both headline metrics.

Note the tension in the fourth row against the advice both arms are given, that
a wide range is honest when the mechanism is uncertain. Both are true, and 100x
is where this project draws the line between the two. It is a judgement, not a
derivation.

## What happens to a rejected prediction

**The finding is kept and the claim is withdrawn.** This is the part an agent
would have got wrong: dropping the finding as well would let a reviewer
improve its own precision by discarding whatever it could not quantify.

So a rejected prediction produces a `Dropped` record naming the symbol, the
path and the reason, and the finding survives without a prediction. Both are
reported. `falsifiable_precision` counts that finding once — it is one
observation that produced nothing testable, which is exactly what a finding
with no prediction at all is worth.

## What is deliberately not enforced here

A validator can see the shape of a claim and not its truth. It cannot tell that
a number was invented, that a mechanism was not established by the evidence, or
that a finding restates a framework default. `docs/FIELD_RUN.md` records a
prediction that passed every rule above and was completely false.

**The gate makes a claim checkable. Only the Prover makes it true.**
