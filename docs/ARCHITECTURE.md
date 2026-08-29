# Architecture

What was built. `docs/planning/BUILD_PLAN.md` describes what was *planned* and
is wrong in several places; this document is written from the code and from one
recorded run.

---

## The shape of it

```
  augury review --case B01 --arm augury
        |
        v
  Cartographer .................... no model call
        |   maps the repository: AST or tree-sitter per language,
        |   import graph, fan-in, git churn, layer signals,
        |   deployment configuration
        v
  Scheduler ....................... no model call
        |   picks the next module worth reading by expected yield
        |   per dollar, under a budget; stops when nothing left is
        |   worth its cost; records every file it skipped and why
        v
  Triage .......................... one model call per module
        |   narrows the specialists the module's signals allow to
        |   the ones it needs. Can narrow, never widen.
        v
  LayerAnalyst x N ................ one model call per specialist
        |   run concurrently. Each reads for one concern only,
        |   briefed from the practice-lab layer that defines it.
        v
  Reconciler ...................... no model call
        |   merges findings colliding on one construct
        v
  falsifiability gate ............. no model call
        |   a prediction survives only if it validates: a metric
        |   from the published vocabulary, a comparator, a number
        |   with a unit, a condition, and a claim some measurement
        |   could contradict
        v
  Prover .......................... no model call
            runs the case's own experiment and records what it
            measured. Grades both arms identically.
```

**Four of the six stages consult no model.** That is the engineering claim this
project makes: knowing which parts must not be a language model.

---

## The eight specialists

One `LayerAnalyst` class, instantiated eight times from a layer spec. The
specialists are the practice lab's own layers, so the agent that hunts a defect
is the one that owns the layer defining it.

| specialist | lab layer | routed by signal |
|---|---|---|
| `concurrency` | `01-machine` | concurrency |
| `network` | `02-network` | network, entrypoint |
| `data` | `03-data` | data |
| `distributed` | `04-distributed` | distributed |
| `failure` | `05-failure` | failure |
| `observability` | `06-observability` | observability |
| `security` | `07-security` | security |
| `craft` | `08-craft` | craft |

Eight instances of one class is cheap. Eight bespoke agents would not be, and
would be worse code.

---

## Routing, in order

1. **Cartographer** detects `Signal`s. Import tables are per language: `sqlalchemy`
   in Python, `database/sql` in Go, `sqlx` in Rust and `java.sql` in Java all
   map to `DATA`. Plus AST detectors for what no import reveals -- a swallowed
   exception, an interpolated query, shared mutable state.
2. `specialists_for(signals)` gives the specialists the file *allows*.
3. **Triage** narrows that set with one small model call. It can narrow but
   never widen, so a hallucinated layer name cannot buy a model call.
4. The chosen specialists run **concurrently** on that module.

Routing on presence rather than certainty is deliberate: a specialist never
called cannot find anything, and nothing downstream recovers the miss.

---

## What one real review actually did

From [`trajectories/augury-B01.jsonl`](trajectories/augury-B01.jsonl), a
seventeen-module repository:

| | |
|---|---|
| steps recorded | 59 |
| model calls | 41 |
| deterministic steps | 18 |
| scheduler decisions | 17 |
| triage calls | 16 |
| specialist calls | 25 |

Specialists actually invoked: `data` 13, `network` 6, `observability` 3,
`security` 1, `craft` 1, `concurrency` 1. Two of the eight were never called,
which is the routing working: fanning out to all eight would have cost three
times as much and produced confident opinions from reviewers with nothing to
look at.

Roughly 1.6 specialists per module, not 8.

---

## Six languages

`tree-sitter-language-pack` parses Python, TypeScript/JavaScript, Go, Rust,
Java and C++ behind one `LanguageAdapter` boundary. Python keeps a native `ast`
adapter, because the source-level detectors need real Python semantics and it
keeps the common case free of a parser dependency.

Everything above cartography consumes `ModuleNode` and never learns which
language produced it.

**Known gap:** the AST-level detectors are Python-only, so `CRAFT` is
unreachable in the other five languages. Import-based signals work everywhere.

---

## The other arm

`BaselineReviewer` is one prompt containing the whole repository, no tools, one
call. It receives the same instructions, the same metric vocabulary, the same
experiment conditions and the same deployment configuration as the pipeline --
enforced by [`tests/test_arm_parity.py`](../tests/test_arm_parity.py), because
for a while it did not, and that made the comparison unfair in the pipeline's
favour.

It is not a strawman. On the published evaluation it is not beaten.

---

## What is not here

The planning documents describe these. None was built.

| | |
|---|---|
| VS Code extension | not built |
| FastAPI serving layer | not built |
| Live docker-compose stack, k6, Grafana | not built; experiments run in process |
| ReAct tool-calling loop | not built; each specialist is one structured call |
| Runbook retrieval corpus | not built; layer briefs are static prompts |
| A Refiner agent | not built, and not needed: the falsifiability gate is a validator, and a rule that can be written cannot hallucinate |

`src/augury/prompts/refiner.md` is on disk and unwired. It is kept because it
states the rule the validator enforces, and because deleting the thinking that
led to a deterministic answer would hide how it was reached.

---

## The MCP surface

`augury mcp --root <dir>` serves the same pipeline over the Model Context
Protocol on stdio, so the reviewer runs inside whatever agent the reader already
has rather than only behind this CLI.

```
  client  --JSON-RPC over stdio-->  serve()  -->  Server.handle(request)
                                     |                    |
                              no decisions        pure function,
                              only framing        no IO of its own
```

Three tools. Two of them are free and need no API key, because cartography is
deterministic and the layer briefs are files on disk:

| tool | what it returns | cost |
|---|---|---|
| `augury_map` | modules per language, concerns per file, what was skipped and why | free |
| `augury_explain` | one specialist's brief, or the metric vocabulary | free |
| `augury_review` | findings with predictions, plus what it spent | metered |

Being able to see the map and the cost before buying the review is the point of
splitting them.

**The root is a launch argument, not a call argument.** An MCP client is driven
by a language model, and a model that can name any path can read any file on the
machine. `Server._resolve` refuses anything outside the boundary it was
constructed with.

The stdio protocol is implemented directly rather than through the `mcp` SDK:
the framing is small, it keeps the dependency list installable offline, and it
made `handle` a pure request-to-response function that the tests drive without
spawning anything.

## Where things live

| | |
|---|---|
| `core/cartography/` | Repository mapping, six languages, signals |
| `core/scheduling/` | Budget-bounded selection and coverage |
| `core/adapters/` | Provider clients, pricing, record-and-replay |
| `core/schemas.py`, `core/findings.py` | Prediction, Finding, Measurement |
| `core/scoring.py`, `evaluation/significance.py` | Metrics and the tests that judge them |
| `core/layers.py`, `prompts/layers/` | The eight specialists and their briefs |
| `agents/` | Baseline, Triage, the pipeline |
| `evaluation/` | Cases, runner, prover, reconciler, sweep |
| `mcp/` | The MCP server: dispatch, tools, stdio framing |
| `cli/` | The only evaluated surface |
