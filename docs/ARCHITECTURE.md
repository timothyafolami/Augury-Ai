# Architecture

What is built, as of the latest commit. `docs/planning/` describes what was
planned and is wrong in most places.

---

## The claim

**Seven stages. Two of them consult a language model.**

Everything a parser, a graph or a registry can answer is answered that way,
because those answers are the same every run and cost nothing. The model is
asked only the question nothing else can answer: *given this file, this
concern, this runtime and these versions, what breaks under load?*

```
augury review --path REPO --scope backend --budget 0.25
  │
  ├─ 1  Surveyor .................................. no model, $0
  │       docker-compose.yml → services, commands, ports, depends_on
  │       "backend/ is a service, redis is a broker, --concurrency=1"
  │       a worker's capacity ceiling exists in no source file
  │
  ├─ 2  Cartographer .............................. no model, $0
  │       six languages, scoped, excludes vendored trees
  │       imports — including the ones written as strings
  │       BFS from entrypoints → depth per module, unreachable set
  │
  ├─ 3  Scheduler ................................. no model, $0  ←┐
  │       ranks by depth from an entrypoint, fan-in, signals,      │
  │       churn, ÷ cost. Stops when nothing left is worth its      │
  │       price, and records what it skipped and why               │
  │                                                                │
  ├─ 4  Triage ...................... one model call per module    │
  │       signals allow {data, network, craft}; triage narrows     │
  │       it can narrow, never widen                               │
  │                                                                │
  ├─ 5  LayerAnalyst × N ............ one model call each          │
  │       concurrent. Each reads for one concern, briefed with     │
  │       its lab layer, its language's failure modes, and the     │
  │       versions this file actually runs against                 │
  │                                                                │
  ├─ 6  ──────────────────────────────────────────────────────────┘
  │       until the budget is spent
  │
  └─ 7  Five deterministic passes ................. no model, $0
          reconcile   merge findings colliding on one construct
          gate        withdraw claims that are not falsifiable
          disprove    withdraw index claims the migrations settle
          collapse    one sentence about sixteen files is one finding
          rank        by evidence, not by the model's adjective
```

The loop at 3↔6 is the progressive part: the Scheduler re-ranks after every
module, and a module whose neighbours produced findings is promoted.

---

## Why the orchestration is not an agent framework

`autogen-core` and `autogen-ext` are dependencies, and every import of them is
in one file — `core/adapters/provider.py` — where they supply the model client
for Groq, OpenAI and Anthropic behind one `ChatModel` protocol.

No `AssistantAgent`, no `Swarm`, no `RoundRobinGroupChat`, no `GraphFlow`. The
orchestration is `asyncio` and a scheduler loop. That is a decision, and these
are the reasons:

| pattern | where it would fit | why it is not used |
|---|---|---|
| Handoff / `Swarm` | triage → specialists | Triage returns a *set*, not a delegation. Handoff lets the model choose the next agent; here that choice is a deterministic narrowing, so a hallucinated layer name cannot buy a model call. |
| `RoundRobin` / `Selector` group chat | the eight specialists | They never see each other's output. Reconciliation is deterministic on `(path, symbol)`. In a group chat one specialist's wrong claim anchors the next one's. |
| Sequential | survey → map → schedule | It *is* sequential, as a function pipeline rather than as agents, because five of the seven stages contain no model. |

A framework that made every stage an agent would make five stages
non-deterministic to no benefit.

---

## The eight specialists

One `LayerAnalyst` class, instantiated eight times from a layer spec. Each is
one layer of the practice lab, so the agent hunting a defect is the one that
owns the layer defining it.

| specialist | lab layer | routed by |
|---|---|---|
| `concurrency` | `01-machine` | concurrency |
| `network` | `02-network` | network, entrypoint |
| `data` | `03-data` | data |
| `distributed` | `04-distributed` | distributed |
| `failure` | `05-failure` | failure |
| `observability` | `06-observability` | observability |
| `security` | `07-security` | security |
| `craft` | `08-craft` | craft |

Each call carries three briefs: the **layer** brief (what this concern is), the
**language** brief (how that concern shows up in this runtime — a blocking call
in `async def`, a goroutine with no context, one of libuv's four threads), and
the **versions** this file imports, so a claim about a library's defaults is
grounded in what is installed rather than in a training cutoff.

---

## What the model is never asked

- **Where a symbol is.** The specialist names it; tree-sitter finds the line.
  Measured: every finding named the right function and one named a line 140
  away from it.
- **Whether a column is indexed.** The migrations say. Three claims of a
  missing index were withdrawn on one real repository, one with an invented
  row count.
- **Which version of a library is installed.** The registry says.
- **Whether a claim is falsifiable.** A validator says. A rule that can be
  written down does not need a model to apply it, and a model applying it can
  be argued with.
- **How severe a finding is.** It is asked, and the answer is used only to
  break ties: told nothing anchors the word, it answered "high" 92 times out
  of 141.

---

## Where things live

| | |
|---|---|
| `core/survey/` | The deployment: services, commands, backing services, entrypoints |
| `core/cartography/` | Six languages, imports, signals, depth, reachability |
| `core/scheduling/` | Budget-bounded selection and coverage |
| `core/schema/` | Migrations read as a schema, and what they do to live tables |
| `core/reference/` | Registry versions, dependency staleness, changelog links |
| `core/adapters/` | Providers, pricing, record-and-replay |
| `core/layers.py`, `prompts/layers/` | The eight concerns |
| `core/languages.py`, `prompts/languages/` | How each runtime fails |
| `core/priority.py`, `reachability.py`, `repetition.py`, `indexes.py` | The passes over a finished report |
| `core/report.py` | The document a team acts on |
| `agents/` | Baseline, triage, the pipeline |
| `evaluation/` | Cases, runner, prover, significance |
| `cli/` | `survey`, `review`, `report`, `evaluate`, `mcp` |
