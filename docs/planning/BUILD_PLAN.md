# Augury — Build Plan

**Read the code. Make a falsifiable claim. Run the experiment.**

| | |
|---|---|
| Written | 2026-08-28 |
| Deadline | 2026-08-31 18:00 UTC |
| Budget | ~54 working hours inside a 68-hour window |
| Language | Python 3.12 |
| Agent runtime | `autogen-core` |
| Name check | `augury` free on PyPI; GitHub clear; Angular's Augury devtool is dead |

---

## 1. The one-sentence product

Every AI code reviewer on the market emits **vibes** — "may have concurrency
issues", "consider adding timeouts". Augury emits **numbers with thresholds**,
and then runs the load test to see if it was right.

That is the entire submission. Everything below serves it.

---

## 2. What makes this buildable in 54 hours

The expensive part already exists in the engineering-practice lab and is
declared as prior work in `docs/PROVENANCE.md`:

| Asset | Path | Role here |
|---|---|---|
| Compose stack (FastAPI gateway, FastAPI+SQLAlchemy api, Postgres, Prometheus, Grafana, k6) | `10-edge/lab/docker-compose.yml` | The system under test |
| Pool profile toggle `default \| sized \| budgeted` | `api` service env | A defect switch, already written |
| k6 scenarios `pool_ramp`, `arrival_rate`, `fanout` | `10-edge/lab/scripts/` | The verification harness |
| 15 captured runs across rates 2–400, fixed and exponential arrival | `10-edge/lab/out/` | **Ground truth already on disk** |
| `fake_upstream.py` | `10-edge/lab/tools/` | Slow-upstream fault |
| Prediction discipline (falsifiable, H/M/B scoring) | `PREDICTIONS.md` | The scoring rubric for the agent |

`PREDICTIONS.md` is the conceptual core: *"'Slower' is not a prediction;
'3-8x slower' is."* Augury applies that discipline to a codebase, and is scored
by it.

---

## 3. Architecture

One core. Three surfaces. The surfaces are thin on purpose — only the core is
evaluated.

```
  CLI (typer)      MCP server       VS Code extension
       \               |                  /
        \              |                 /  (HTTP to localhost)
         +-------------+----------------+
                       |
              FastAPI control plane
              POST /reviews  ·  GET /reviews/{id}  ·  SSE progress
                       |
              AutoGen Core runtime  (SingleThreadedAgentRuntime)
                       |
   +--------+----------+-----------+-----------+----------+
   |        |          |           |           |          |
Cartographer Scheduler  Analysts   Refiner    Prover     Editor
 (no LLM)   (no LLM)   (3 lenses)  (gate)   (runs k6)   (ranks)
                       |
              Knowledge corpus  +  Model adapters
```

### 3.1 Repository layout

```
augury/
  core/
    schemas.py        # pydantic: ModuleNode, Finding, Prediction, Verdict, Report
    adapters/         # ChatModel Protocol + anthropic/, openai/, cassette/
    corpus/           # indexed subset of the practice lab, provenance-stamped
    cartography/      # ast walk, import graph, git churn  (no LLM)
    scheduling/       # next-module selection under budget  (no LLM)
    agents/           # AutoGen Core RoutedAgents, one file each
    prover/           # k6 driver, prometheus reader, H/M/B scorer
    pipeline.py       # runtime wiring, topic constants
  cli/                # `augury review .`   <- what the eval harness drives
  api/                # FastAPI
  mcp/                # MCP server over the same core operations
extension/            # TypeScript, thin client  [GATED]
eval/
  cases/              # seeded-defect repos + expected predictions
  runner.py  scorer.py  cassettes/
docs/
  PRD.md  BUILD_PLAN.md  PROVENANCE.md  CHANGELOG.md  HOT_TAKE.md
```

### 3.2 The agent mesh

Verified against `autogen-core` / `autogen-ext` **0.7.5** (current). Both the
`anthropic` and `openai` extras exist and both are used: one for headline
numbers, the other for the cross-model robustness run.

Three composition patterns, each used where it is actually the right tool:

**Handoff** (`core-user-guide/design-patterns/handoffs.ipynb`) — a Triage agent
reads a module's cartography signature and delegates, by tool call, to the
specialists that can say something useful about it. A pure data-access module
never pays for a concurrency analysis. This is a cost mechanism, not decoration:
it is the difference between 8 analyses per module and ~2.

**Layer specialists** — one `LayerAnalyst` class, instantiated eight times from
a layer spec (topics, corpus slice, finding types, prompt). The specialists are
the lab's own layers, so the agent that hunts a defect is the one that owns the
layer defining it:

| Specialist | Lab layer | Hunts |
|---|---|---|
| `ConcurrencyAnalyst` | `01-machine` | Races, atomicity, memory visibility |
| `NetworkAnalyst` | `02-network` | Pools, timeouts, keep-alive, HOL blocking |
| `DataAnalyst` | `03-data` | Isolation, indexes, N+1, deadlocks, plans |
| `DistributedAnalyst` | `04-distributed` | Idempotency, partial failure, clocks |
| `FailureAnalyst` | `05-failure` | Little's Law, retries, backpressure, metastability |
| `ObservabilityAnalyst` | `06-observability` | Signals, correlation IDs, real p99, cardinality |
| `SecurityAnalyst` | `07-security` | Injection, IDOR, SSRF, JWT, secrets |
| `CraftAnalyst` | `08-craft` | Module depth, coupling, errors as interface, test levels |

Eight instances of one class is cheap. Eight bespoke agents would not be, and
would be worse code.

**Group chat** — used in exactly one place. When two or more specialists raise
findings on the same module touching the same symbol, a bounded `Reconciler`
round reconciles them before the Refiner sees anything. Pool exhaustion is
simultaneously a `02-network`, `03-data` and `05-failure` finding; three near
-duplicate entries in a report is a defect in the reviewer, not a thorough
review.

| Agent | Subscribes | Publishes | LLM? |
|---|---|---|---|
| **Cartographer** | `review.requested` | `repo.mapped` | No — `ast`, import graph, `git log --numstat` |
| **Scheduler** | `repo.mapped`, `finding.proposed` | `module.selected` | No — scoring function |
| **Triage** | `module.selected` | `handoff.*` | Yes (small model) |
| **LayerAnalyst** x8 | `handoff.<layer>` | `finding.proposed` | Yes |
| **Reconciler** | `finding.proposed` (collided) | `finding.merged` | Yes, bounded rounds |
| **Refiner** | `finding.merged` | `prediction.made` \| `finding.dropped` | Yes |
| **Prover** | `prediction.made` | `verdict.reached` | No — k6, Prometheus, probes |
| **Editor** | `verdict.reached`, `finding.dropped` | `report.ready` | Yes (small) |

Two of the ten roles use no LLM at all, and they are the two doing the hardest
work. Knowing which parts must not be a language model is the engineering
claim this project is making.

**Dropped findings are reported, never silent.** The Refiner publishes
`finding.dropped` with the finding, the reason it could not be made falsifiable,
and what evidence would have been needed. The Editor renders these in a
`Not falsifiable` appendix with counts by reason. Silently discarding a
reviewer's output is precisely the "fast, successful, empty response" failure in
`08-craft/03`, and it would be embarrassing to ship it in this tool. Drop rate
and drop reasons are reported metrics.

### 3.3 The two components that carry the 30 engineering points

**Scheduler — the large-codebase answer.** A repo does not fit in context, so
the agent cannot "read everything". The Scheduler holds a budget and repeatedly
picks the next module by expected yield over cost: entrypoints and IO
boundaries first, weighted by git churn, fan-in from the import graph, and
down-weighted once neighbouring modules have come back clean. It stops when
marginal yield falls below a floor. This is the answer to *"he has to take it
one after the other"*, and it is measurable: coverage and findings-per-dollar
against a naive breadth-first sweep.

**Refiner — the falsifiability gate.** Analysts produce prose. The Refiner
either converts a finding into a claim with a number, a unit and a threshold, or
drops it. This single component is what separates Augury from every other AI
reviewer, and it is where the primary metric comes from.

### 3.4 Model adapters

One `Protocol`, three implementations, chosen by config and never by import
site:

```python
class ChatModel(Protocol):
    async def structured(self, *, prompt: str, schema: type[T]) -> T: ...
    @property
    def usage(self) -> Usage: ...   # tokens in/out, USD, latency
```

- `AnthropicAdapter`, `OpenAIAdapter` — the cross-model robustness run
- `CassetteAdapter` — a decorator that content-hashes `(provider, model,
  messages, schema)` and records/replays. Makes dev iteration free and lets
  judges reproduce every number with **no API key**.

Every adapter reports usage, so cost-per-review is measured rather than
estimated.

---

## 4. What the user actually sees

### 4.1 CLI — primary, and the only evaluated surface

```
augury review .                      # full pass
augury review . --budget 2.00        # stop at $2
augury review . --prove              # run the experiments, not just the claims
augury baseline .                    # the comparison arm
```

Terminal output, plus `augury-report.json`:

```
FORECAST-02   api/db.py:31                                     high
  Claim    p99 crosses 1000ms at ~250 req/s
  Basis    pool_size=5, 8 workers, ~40ms mean service time.
           Little's Law puts saturation at ~125 concurrent.
  Proof    k6 pool_ramp @ 250 rps  ->  measured p99 1240ms      HIT
```

The `Proof` line is the product. Nothing else in this space has it.

### 4.2 MCP server

Same core operations exposed as MCP tools (`augury.review`, `augury.explain`,
`augury.prove`). Reaches Claude Code, Cursor, Windsurf and Claude Desktop in one
move. Thin adapter, ~2h, no new capability — a distribution channel, and it will
be described as one, never as a measured improvement.

### 4.3 VS Code extension — gated

Thin TypeScript client over the local FastAPI:

- One command: `Augury: Review Workspace`
- Progress notification while the run streams
- Findings rendered through `languages.createDiagnosticCollection` — squiggles
  in the editor and rows in the Problems panel, severity and source set
- Click through to a webview showing claim, basis and verdict
- Shipped as a `.vsix` committed to the repo; judges install with one command

**Not published to the marketplace.** Publisher verification is a delay outside
our control on a 68-hour clock.

---

## 5. Evaluation

### 5.1 Metrics

| Metric | Definition | Why |
|---|---|---|
| **Falsifiable Precision** *(primary)* | Findings carrying a number, unit and threshold, as a share of all findings | The baseline scores near zero. This is the headline |
| **Prediction Hit Rate** *(primary)* | H/M/B per `PREDICTIONS.md`, over findings the Prover tested | Correctness, empirically |
| False alarm rate | Findings against the known-good `sized` pool profile | Punishes a reviewer that flags everything |
| Coverage per dollar | Modules meaningfully analysed / USD | Justifies the Scheduler |
| Cost and wall-clock per review | From adapter usage accounting | Efficiency |

### 5.2 The baseline

A single well-written "review this codebase for production risks" prompt over
the same repo, same output schema, same scorer. This is what a competent
engineer does today, and it is a fair fight. It will produce a tidy, plausible,
**unfalsifiable** list. Reporting that gap honestly is the submission.

### 5.3 Ground truth

Two sources, both objective:

1. **Already-captured k6 runs** in `10-edge/lab/out/` — fifteen of them, across
   rates 2 to 400. The agent predicts a threshold; the curve already on disk
   says whether it was right. Zero marginal cost.
2. **Seeded defects** — a copy of the lab stack with N known defects introduced
   (unsized pool, missing timeout, unguarded concurrent update, no dead-letter,
   silent except, unindexed hot column). The Prover verifies each by running the
   matching k6 scenario.

3 seeds per case. A gain inside the noise band is reported as inconclusive, not
as an improvement.

---

## 6. Timeline

| Phase | h | Output | Exit condition |
|---|---|---|---|
| P0 Foundation | 2 | Register, repo, schemas, adapters + cassettes, CI | `pytest` green |
| P1 Cartography | 5 | Cartographer + Scheduler, no LLM | Maps the lab repo, ranks modules |
| P2 Harness | 4 | Cases, runner, scorer, baseline arm | `make eval` runs end to end |
| P3 Baseline | 3 | Baseline measured on all cases | **First number on the board** |
| P4 Analysts | 10 | 3 lenses + Refiner, measured after each | Falsifiable Precision beats baseline |
| P5 Prover | 8 | k6 driver, Prometheus reader, H/M/B verdicts | A claim is proved end to end |
| P6 Serving | 4 | FastAPI + MCP | Both drive the same core |
| P7 Extension | 5 | VS Code `.vsix` | **GATED at hour 45** |
| P8 Deliverables | 8 | README, changelog, repro guide, trajectories, video | Clean-clone rehearsal passes |
| Buffer | 5 | Slippage | — |

**Hard rule.** P8 begins no later than 12 hours before the deadline regardless of
what is unfinished. An incomplete submission is disqualified at the gate before
rubric scoring. A submission that stops after P5 with excellent evidence scores
well on most of the rubric. P6 and P7 are both cuttable without touching the
core; P7 goes first.

---

## 7. Cut list (decided, not deferred)

| Cut | Why |
|---|---|
| Live incident diagnosis | Needed a second testbed serving only ground truth. The story survives: the best time to diagnose an incident is three weeks before it happens |
| Hosted API | Reproducibility is 15 points and hosting is the opposite of reproducible |
| Marketplace publishing | Verification delay outside our control |
| Deep git history analysis | Keep `--numstat` churn for the Cartographer; drop the rest |
| Languages beyond Python | One stack shape, analysed well, stated plainly |

---

## 8. Open questions

1. How many seeded defects: 8 done excellently or 12 done adequately?
2. Which lab layers clear the verification bar for corpus ingestion, given the
   known unverified content in `DEFECTS.md`?
3. Anthropic or OpenAI for the headline numbers; the other for robustness?
4. Does the Refiner drop unfalsifiable findings silently, or report them in a
   separate low-confidence section? Dropping is cleaner; reporting is more
   honest to the user.
