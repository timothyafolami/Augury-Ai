# Hot take

**The reason AI code review does not work is not that the models are bad at
reading code. They are good at it. The reason is that nothing makes them say
anything a measurement could contradict, so nobody can tell the difference
between a review that is right and one that merely sounds right.**

---

## What the measurements say

On a seventeen-module service with five seeded defects, a single well-written
prompt found all of them. So did the pipeline. Recall was **inconclusive**
between the two across three seeds.

Both arms produced claims that looked falsifiable. Both had roughly the same
falsifiable precision.

The arms separated on one number only:

| | baseline | augury |
|---|---|---|
| seeded defect recall | 0.933 | 1.000 |
| falsifiable precision | 0.833 | 0.875 |
| **hit rate** | **0.250** | **0.500** |

The baseline's numbers were mostly wrong. Nothing about reading its report
would have told you that. It named real defects, in the right files, with
confident thresholds — and when the experiments ran, three quarters of its
thresholds did not hold.

That is the entire finding, and it is not the one I set out to prove. I
expected the pipeline to find more defects. It did not. What it improved was
whether the numbers it attached were true.

---

## Why this is worse than it sounds

A wrong finding with no number attached is cheap: you read it, you disagree,
you move on. A wrong finding *with* a number is expensive, because the number
is what makes you act. "p99 will exceed 1000ms at 250 requests per second"
sends someone to resize a pool. If the real threshold was 4000ms and the pool
was fine, that engineer spent their afternoon on the wrong thing and now trusts
the tool slightly less than they did, which is the worst of both outcomes.

The industry is currently optimising for the property that makes this worse.
Fluency, specificity and confidence all rose sharply; the rate at which the
claims survive testing is not measured by anyone, including by the tools' own
benchmarks.

---

## What I would build differently now

**Measure the claims, not the findings.** Every code review benchmark I know
of scores whether a defect was named. That is the easy half. Two reviewers that
both name the N+1 are not equivalent if one of them says "51 queries for 50
orders" and the other says "significantly more queries", and only one of those
is checkable.

**Ship the experiment with the claim.** The thing that made this measurable was
not a smarter reviewer, it was that each case carries runnable code that
settles its own defects. That took an afternoon and it is the most valuable
part of the repository. Any team could add three of them to their own codebase
this week and immediately know whether their AI reviewer is worth its cost.

**Withhold rates you cannot support.** One of my own baseline seeds produced a
hit rate of 1.000 from a single tested prediction, and I nearly published it.
The harness now refuses to print a rate under five measurements and prints the
counts instead. Almost every impressive number in this space rests on a
denominator nobody shows you.

---

## The uncomfortable part

The pipeline costs six and a half times the baseline and takes four times as
long. For that, on this case, it bought a doubled hit rate and no additional
defects.

Whether that is worth paying depends entirely on a number I do not have: how
often a wrong threshold sends an engineer down a wrong path, priced against a
one-cent review. On a seventeen-module repository I would not pay it. The
architecture is built for repositories where reading everything is not an
option, and I have not yet tested one.

I would rather end on that than on a chart where my system wins.
