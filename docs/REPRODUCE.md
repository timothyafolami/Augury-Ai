# Reproducing the results

Written for someone starting from a clean machine who has never seen this
repository. Every number in the README and the changelog is produced by a
command here.

---

## What you need

| | |
|---|---|
| Python | 3.12 (uv installs it; no system Python is used) |
| uv | https://docs.astral.sh/uv/ |
| Disk | about 400 MB, mostly the tree-sitter grammars |
| API key | Groq, OpenAI or Anthropic. **Not needed** for the test suite |

No Docker is required. The experiments run against an in-process database.

---

## Setup

```bash
git clone <this repository>
cd augury
make install
```

`make install` creates a virtual environment on Python 3.12, installs from the
committed `uv.lock` so your dependency versions match the ones that produced
the numbers, and points git at the tracked hooks directory.

Takes about 90 seconds, most of it downloading tree-sitter grammars.

---

## Check it works, with no API key

```bash
make check
```

Runs ruff, ruff format, mypy strict over `src` and `tests`, and the full test
suite. Expect **388 passed, 2 skipped**, in about 30 seconds. Nothing here
reaches the network.

This is the same command CI runs and the same command the pre-commit hook runs.
There is one definition of green.

---

## Run the experiments, with no API key

The experiments are the ground truth. They run the case repository's own code
and measure what it does, and they are the part a reviewer's claims are checked
against, so they are worth running first and reading.

```bash
.venv/bin/python eval/cases/B01-orders-service/experiments/queries_per_request.py
.venv/bin/python eval/cases/B01-orders-service/experiments/final_balance.py
.venv/bin/python eval/cases/B01-orders-service/experiments/http_status.py
```

Expected, in about two seconds each:

| experiment | correct | what you should see | what it means |
|---|---|---|---|
| `queries_per_request` | 2 | **51** | one query per order plus the listing: the N+1 |
| `final_balance` | 0.00 | **90.0** | nine of ten concurrent debits silently lost |
| `http_status` | 500 | **200** | a broken database returning a successful empty list |

The last line each prints is the measurement. Everything above it is the
experiment narrating what it did.

Read `eval/cases/B01-orders-service/experiments/final_balance.py` if you read
only one file in this repository. It imports the service's own `debit` and
supplies nothing but concurrency.

---

## Run a review

```bash
cp .env.example .env
# add GROQ_API_KEY=...   (or set AUGURY_PROVIDER and the matching key)
```

Defaults to `openai/gpt-oss-120b` on Groq at temperature 0. Set
`AUGURY_MODEL=openai/gpt-oss-20b` to run the smaller model of the same family,
which is how the capability question is separated from the architecture
question.

```bash
make review-baseline    # one prompt over the whole repository
make review-augury      # schedule, triage, specialise, reconcile
```

Roughly 10 seconds and $0.004 for the baseline; 45 seconds and $0.027 for
Augury, on case B01.

---

## Reproduce the published comparison

```bash
make evaluate           # both arms, three seeds each, with proving
```

About 4 minutes and $0.09 total. Prints the table in the README, with the
per-seed spread beside every mean.

**A difference smaller than the spread is reported as `inconclusive`.** That is
not editorial caution, it is what `SweepResult.compare` returns; there is no
path by which an overlapping result can be printed as a win.

---

## What you should and should not expect to match

The **experiments are deterministic**. 51, 90.0 and 200 will reproduce exactly.
If they do not, that is a real difference in your environment and worth
reporting.

The **reviews are not**. Both arms were observed changing their answer between
runs at temperature 0: over eight seeds the baseline returned three different
answers on the same case with nothing changed. Expect your recall to land inside the published
range rather than on the published mean, and expect the hit-rate numbers, which
rest on single-digit denominators, to move more than that.

Where a rate rests on too few measurements to be a rate, the harness reports
the counts and declines to publish the ratio.

---

## Costs

| run | calls | approximate cost |
|---|---|---|
| `make check` | 0 | free |
| the three experiments | 0 | free |
| `make review-baseline` | 1 | $0.004 |
| `make review-augury` | ~40 | $0.027 |
| `make evaluate` | ~130 | $0.09 |

Costs are measured from provider token counts against the table in
`src/augury/core/adapters/pricing.py`, never estimated. A model with no entry
there is refused at construction rather than reported as free.
