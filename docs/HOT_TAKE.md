# Hot take

**Everyone building AI code review is measuring whether the reviewer named the
defect. That is the easy half, it is nearly free to score, and it is why the
tools do not get better. The hard half is whether the reviewer's claim is
true — and almost nobody builds the apparatus to find out, because the moment
you do, it starts telling you things you did not want to hear.**

---

## What I set out to show, and what happened

The thesis was that an agentic pipeline — routing files to specialists briefed
from a real engineering knowledge base, under a budget — would review code
better than one well-written prompt.

Three cases, ten seeded defects, five seeds per arm. Every prediction that
could be settled was settled by an experiment shown to distinguish working code
from broken code -- one of the three cases ships no experiments, and its
predictions are recorded as untested rather than counted:

| metric | baseline | augury | |
|---|---|---|---|
| seeded recall (audited) | 0.700 | 0.800 | one observation |
| falsifiable precision | **0.909** | 0.667 | baseline, clearly |
| hit rate | 0.833 (5/6) | **1.000** (5/5) | not measured |
| prediction coverage | 0.600 | 0.429 | graded on fewer of its own claims |
| cost | $0.0017 | $0.0083 | 5.0x |

The thesis as stated -- that the pipeline reviews code *better* -- is not
supported. It finds the same defects. It states markedly fewer
testable claims than the baseline. It costs five times as much.

What it does do is be right more often about the claims it does make -- by one
experiment. Five of five against five of six. There is no p-value beside that
because the repeats are not independent and the harness now refuses to compute
one, which is the correct behaviour and also the end of the only result this
project ever had that pointed at the pipeline.

An earlier version of this paragraph said thirty of thirty against twenty-five
of thirty, p = 0.052, suggestive. Every number in that sentence was an
artefact: replay serves five repeats from one recording, and the significance
test was the one place the independence guard had not been added.

**And an earlier version of this table was unfair.** Falsifiable precision read
0.778 against 0.833 -- favouring the pipeline -- because the analyst prompt was
told exactly what the falsifiability validator rejects and the baseline prompt
was not, and a rejected prediction lands in that metric's denominator. Told the
same rules, the numbers above reverse. Three further asymmetries pointed the
same way. Two of the tests written to catch that were instead enforcing it.

I could have shipped a version of this that appeared to work. Three separate
times I had a table that showed one, and each time the apparatus was wrong
rather than the arms.

---

## The actual finding

**The measuring apparatus was the least trustworthy component in the
experiment, and it was the last thing anybody checked.**

Every published number in this project was wrong at least once. Never because
the scoring arithmetic was wrong — I could have unit-tested that all week:

- **A rate over the wrong denominator, twice.** Falsifiable precision first
  excluded the findings the pipeline had dropped, so any architecture with a
  filter scored near 1.0 by construction and the baseline near 0. Fixing that
  introduced the opposite error: a dropped finding was counted once as a
  finding and once as dropped, so a malformed prediction cost twice what an
  absent one did -- and only one arm had been told how to avoid malformed
  ones.
- **A matcher that scored `except` as a mention of `exception`.** When I fixed
  it, it then refused `leaks` as a mention of `leak` — and recall *inverted*:
  a review describing every defect correctly scored 0.000, while four findings
  whose mechanism was a single full stop scored 1.000.
- **Experiments that returned a number without measuring anything.**
  `worker_saturation` gave a perfect score to a correctly fixed HTTP client,
  because httpx already defaults to a five-second timeout and my deadline was
  three. `queries_per_request` reported 51 queries for a repository whose N+1
  had been removed, because the experiment looped over its own query instead
  of calling the endpoint. That number was the README's headline example.

None of it was visible from inside. Every one was found by an adversarial
reviewer given one instruction: **check each experiment by writing the fixed
version of the code and running it again.** That single instruction found three
dead experiments in one pass.

---

## What I would tell someone building this

**Score the claim, not the finding.** Two reviewers that both name the N+1 are
not equivalent if one says "51 queries for 50 orders" and the other says
"significantly more queries". Only one of those is checkable, and only one of
them is worth acting on at 3am.

**Ship the experiment with the case.** The thing that made any of this
measurable was not a smarter reviewer. It was ten defects that read correctly
line by line, each with runnable code that settles it. Three of those took an
afternoon each. Any team could add three to their own repository this week and
learn, that week, whether their AI reviewer is worth its subscription.

**Write the fixed version and re-run.** An experiment that cannot fail on
correct code cannot pass on incorrect code either. It just returns a number.
This is now two lines in a test file here, it runs on every commit, and it
would have saved me three published claims.

**Then do it again against a fix you did not write.** `queue_depth` passed the
test above and was still measuring nothing: it discriminated against the bound
my remediation used and against no other. Passing against one fix is necessary
and it is not sufficient.

---

## The uncomfortable part

Nine of the things listed above were found by adversarial review agents pointed
at my own work, not by me. I wrote the tests, I ran the experiments, I read the
output, and I published four numbers that were artefacts.

The reason is not carelessness, and that is what makes it worth saying. Every
one of those measurements was *plausible*: 51 queries for 50 orders is exactly
what an N+1 looks like, and it was the right answer arrived at by a mechanism
that would have produced the same answer from correct code. A number that
matches your expectation is the one you check least.

Which is the same reason AI code review fails, in the same shape. A fluent,
specific, confident finding about a real file is the one nobody verifies —
and being right in appearance is not a weaker version of being right. It is
the thing that stops you finding out.
