# Differential — Product Requirements Document

**Root-cause diagnosis for services nobody read.**

| Field | Value |
|---|---|
| Author | Timothy Afolami |
| Status | Draft for approval |
| Created | 2026-08-28 |
| Context | micro1 Frontier Engineering Challenge 2026 (Agentic Workflows Hackathon) |
| Deadline | 2026-08-31, 18:00 UTC |
| Working name | `differential` (changeable) |

## Decisions locked

| Decision | Choice | Rationale |
|---|---|---|
| Language | **Python** | Explicitly recommended by the tech policy; the testbed is itself a FastAPI/Celery stack; the workload is I/O-bound on model calls, so a faster runtime buys nothing. Framework fluency is the binding constraint at 68 hours, not execution speed. Rust is a post-hackathon rewrite, not a weekend one. |
| Distribution | **MCP server** | Thin adapter (~2h) over a tool layer we must build regardless. Reaches Claude Code, Cursor, Windsurf, Claude Desktop and VS Code in one move. |
| VS Code extension | **Cut** | Strictly dominated by MCP: a separate TypeScript codebase, manifest, packaging and UI for zero rubric points MCP does not already earn. |
| Scope shape | **One stack, twelve scenarios, two modes** | Breadth comes from cases and modes, never from industries. The problem PDF asks explicitly for tight scope. |
| Knowledge source | **Curated subset of the engineering-practice lab** | See §8.3. Verified layers only, with per-chunk provenance. |

---

## 1. TL;DR

Production services are increasingly written by coding agents and increasingly
operated by humans who never read them. When one breaks, the bottleneck is no
longer writing a fix. It is working out what is actually wrong, at speed, in a
system you did not author.

**Differential** is an agentic diagnostic system that takes a degraded service
and returns a ranked, evidence-backed root cause. It does this the way a good
on-call engineer does: it forms competing hypotheses, deliberately chooses the
cheapest observation that best distinguishes between them, and refuses to commit
to an answer it has not tried to disprove.

We evaluate it against a live, deliberately broken docker-compose stack with
twelve injected faults whose ground truth we control. We measure it against a
fair baseline on the same cases. The headline number is root-cause accuracy at
rank one; the number we care most about is how often the system is confidently
wrong.

---

## 2. The story

### 2.1 What actually changed

Two years ago, the expensive part of software was producing it. That is no
longer true. A working FastAPI service with a Celery worker, a Redis broker, a
Postgres backing store, a Dockerfile and a compose file is now roughly one
prompt away. Most engineers reading this have shipped something that way in the
last month.

What did not get cheaper is understanding that service at 2am when it starts
returning 502s.

This is the actual shift, and it is under-discussed because it is unflattering:
**code volume went up, code comprehension went down, and the gap between them is
absorbed entirely by whoever is on call.** The person paged is now routinely
debugging a system that no human read line by line — not because anyone was
careless, but because reviewing generated code with the same intensity you would
review hand-written code destroys the speed advantage that made you generate it.
So reviews got shallower. Everyone knows this. Nobody says it in the standup.

### 2.2 The specific shape of the damage

Generated infrastructure code does not fail randomly. It fails in a small,
boringly predictable set of ways, because coding agents are optimised to produce
something that *runs*, and the difference between "runs" and "survives contact
with production" lives almost entirely in configuration that has no effect on
the happy path:

- Defaults are never tuned, because the default worked in the demo.
- Timeouts are omitted, because nothing was slow in the demo.
- Retries are added without backoff or jitter, because nothing failed in the demo.
- Connection pools are sized by copy-paste, because there was one client in the demo.
- Health checks return `200 OK` unconditionally, because there was nothing to be unhealthy in the demo.
- Restart policies are set to `always`, which makes a crash-looping worker look, from the outside, exactly like a healthy one.

Every one of those is invisible in code review, invisible in tests, and
invisible in staging. All of them surface for the first time under real load,
usually at the worst possible moment, and always as a symptom several layers
away from the cause.

### 2.3 The incident this comes from

This project exists because of a specific outage.

In August 2026 a Redis restart-policy misconfiguration took down a production
FastAPI/Celery/Redis/Qdrant service I operate. The externally visible symptom
pointed somewhere else entirely. The configuration in question had been
scaffolded, had been reviewed, had looked completely reasonable, and had been
wrong the entire time it was in production.

> **TODO before submission:** replace this paragraph with the first-hand
> account — what the first symptom looked like, what I checked first and why it
> was the wrong thing, how long the diagnosis actually took, and the moment the
> real cause became obvious. Judges can tell the difference between a war story
> and a summary of a war story. This has to be the real one, in my own words.

The part worth generalising is not that a config was wrong. It is that the
diagnosis was slow for a structural reason: **the loudest signal was not the
causal one.** I anchored on the first alarming thing I saw and spent my
attention defending that hypothesis instead of trying to kill it. That is not a
personal failing, it is the standard human failure mode under time pressure, and
it is the exact failure mode that a naive LLM reproduces with total confidence
and no hesitation.

### 2.4 Why an agent, and why this agent

The obvious move — paste the logs into a chat model and ask what is wrong — is
genuinely useful and genuinely insufficient. It produces a fluent, plausible,
specific answer in eight seconds. Sometimes that answer is right. The problem is
that its tone is identical whether it is right or wrong, and under pressure a
confident wrong answer is worse than no answer, because it costs you the twenty
minutes you spend acting on it.

So the interesting engineering question is not "can an agent diagnose an
incident". It is:

**Can an agent be built that is less confidently wrong than the humans and the
naive models it is replacing?**

That is a measurable question, it has an unambiguous ground truth if you inject
the faults yourself, and it is worth answering.

---

## 3. Users

### 3.1 Primary user: the solo or small-team on-call engineer

Operates between one and ten services. Has no dedicated SRE, no incident
commander, and no runbook for the specific thing that just broke. Wrote perhaps
40% of the running code personally; the rest was generated, inherited, or both.
Gets paged directly. Success for this person is measured in minutes, and the
first ten minutes are spent purely on orientation.

**Their bottleneck, precisely:** not fixing, not deploying, not communicating.
It is *forming a correct hypothesis about an unfamiliar system while the clock
runs*, from evidence scattered across container logs, process metrics,
configuration files, queue state, and recent deploy history — five surfaces that
do not share a schema, a timestamp format, or a query language.

**Why solving it is valuable:** the diagnosis phase is the longest and most
variable part of an incident, and it is the only part where being wrong actively
costs you more time. Remediation is usually fast once the cause is known.

### 3.2 Secondary user: the engineer inheriting a generated codebase

Joined last week. The service predates them. There is no one to ask, because the
person who prompted it into existence has moved on. Uses the same tool for
"why is this slow" as for "why is this down".

### 3.3 Explicit non-user

Large organisations with mature observability, distributed tracing, an SRE
rotation and institutional runbooks. They have already solved the orientation
problem with money and headcount. Differential is for everyone who has not.

---

## 4. Goals and non-goals

### 4.1 Goals

| # | Goal | How we know we hit it |
|---|---|---|
| G1 | Correctly identify the root cause of a degraded service | Root-Cause Accuracy@1 on 12 held-out injected faults |
| G2 | Be honest about uncertainty | False-Confident Rate strictly lower than baseline |
| G3 | Justify every conclusion with retrievable evidence | Evidence Precision against ground-truth evidence sets |
| G4 | Be cheaper and faster than a human doing it manually | USD and wall-clock per incident vs. timed manual runs |
| G5 | Be reproducible by a stranger from a clean machine | Judge runs three commands, gets our headline numbers |

### 4.2 Non-goals

- **Automated remediation.** Differential proposes fixes; it never applies them.
  This is a deliberate product decision as well as a hackathon ground-rule
  requirement, and it is also just correct: an agent that is 80% accurate at
  diagnosis is valuable, and an agent that is 80% accurate at *acting* is a
  liability.
- **Replacing observability tooling.** We consume logs, metrics and config. We
  do not build a metrics platform.
- **Generality across all infrastructure.** We target one realistic stack shape
  (Python API + broker + worker + relational store) and say so plainly. Claiming
  universality we have not measured would violate our own evidence rule.
- **Beating a well-resourced SRE team.** The comparison that matters is against
  what our user actually does today.

---

## 5. Product overview

Differential runs in two modes over one knowledge corpus, exposed through two
surfaces. Mode A is what you reach for when it is already broken. Mode B is what
would have stopped you reaching for Mode A.

### 5.1 Mode A — diagnose (after it breaks)

The user points the CLI at a running compose project that is misbehaving:

```
differential diagnose --project acme-api --symptom "p99 latency spiked, some 502s"
```

It returns a structured diagnosis:

```json
{
  "root_cause": "db-pool-exhaustion",
  "confidence": 0.86,
  "reasoning": "...",
  "evidence": [
    {"source": "postgres:pg_stat_activity", "observation": "40 connections, 40 active, 0 idle"},
    {"source": "api:logs", "observation": "QueuePool limit of size 5 overflow 10 reached"},
    {"source": "config:app/db.py:14", "observation": "pool_size=5 against 40 concurrent workers"}
  ],
  "ruled_out": [
    {"hypothesis": "redis-memory-pressure", "disconfirmed_by": "used_memory 41MB of 512MB limit"}
  ],
  "proposed_remediation": "...",
  "remediation_applied": false
}
```

The `ruled_out` field is not decoration. It is the product. A diagnosis that
shows you what it eliminated and how is trustworthy in a way that a bare answer
is not, and it is the artefact that lets a human take over efficiently when the
agent is wrong.

### 5.2 Mode B — audit (before it breaks)

Incidents happen because knowledge was missing at the moment the code was
written. The knowledge usually exists; it is simply far away from the keyboard.
Mode B closes that distance.

```
differential audit --project acme-api
```

The audit reads the same surfaces the diagnostic agent reads — compose files,
service config, source, dependency manifests — and reports the **latent** faults:
the ones that will not show up in review, tests or staging, and will surface for
the first time under load.

This is not a second product. It is the same fault catalogue and the same
knowledge corpus, queried at a different moment in time. Every entry in §8 is
simultaneously three things:

- a **failure mode** — what breaks at 2am (Mode A)
- a **knowledge gap** — what you did not know when you scaffolded it (§8.3)
- a **static signature** — visible in config or code before it ever runs (Mode B)

`redis-noeviction` is not an incident *or* a lesson *or* a lint rule. It is one
piece of knowledge appearing at three moments.

**Operability score.** The audit also answers a meta-question: *could this
service even be diagnosed if it broke?* Structured logs, correlation IDs, a
health check that checks something, metrics on the things that actually fail.
Generated services routinely score near zero here, and that is a finding rather
than an accusation. It also tells the user whether Mode A would stand a chance.

### 5.3 Surfaces

| Surface | Role | Evaluated? |
|---|---|---|
| CLI | Primary interface; what the evaluation harness drives | Yes — all numbers come from here |
| MCP server | Distribution. Exposes the same tool layer and both modes to any MCP client | No — it is a channel, not a capability |

The MCP server is deliberately a thin adapter over the measured core. It is
presented as *how the work reaches the user*, never as a second thing built. A
distribution channel cannot be a measured improvement and we will not claim it
is one.

**Positioning note.** micro1's whole thesis is that using AI *is* the point —
coding-agent use is mandatory here. Any framing that reads as contempt for
people who ship generated code will land badly with these judges specifically.
The user is not careless, they are fast, and the tooling never put the knowledge
in front of them at the moment they needed it. Bring the knowledge closer. That
is the entire posture of this product.

---

## 6. The baseline (fair comparison)

Per the challenge rules the baseline must be a reasonable representation of how
this is handled today, given the same task and the same evaluation cases.

**Baseline B0 — single-prompt diagnosis.** One call to the same model, given the
same symptom description plus a dump of recent logs and `docker compose ps`
output — approximately what a competent engineer pastes into a chat window.
Same output schema, same scorer, same cases.

**Baseline B1 — timed manual diagnosis (n=3).** I personally diagnose three of
the twelve incidents with a stopwatch and no AI assistance, recording elapsed
time and whether I got it right. Small sample, honestly labelled as such, and
reported with that caveat. It exists to give the "human time per task" row a
real number rather than an estimate.

Resource parity is documented explicitly: B0 gets one shot and no tools by
construction, which is the point of the comparison, and the resource difference
is stated in the results table rather than hidden.

---

## 7. Solution architecture

The system is built as an explicit ladder of rungs. Each rung is a real
architectural change, is measured on the full case set before the next is built,
and becomes one row of the Improvement Changelog. This is not documentation
overhead bolted on at the end — it is the development process itself, and it is
why the changelog will contain honest negative results.

| Rung | Name | Change | Hypothesis being tested |
|---|---|---|---|
| L0 | Single prompt | Baseline B0 | How far does fluency alone get you? |
| L1 | ReAct + tools | Agent can query logs, metrics, config, deploys | Does grounding in real evidence beat guessing? |
| L2 | + Runbook memory | Retrieval over a corpus of known failure signatures | Does prior art help, or does it cause anchoring? |
| L3 | + Verification gate | Must state and test a falsifiable prediction before answering | Does forced disconfirmation reduce confident wrongness? |
| L4 | + Differential selection | Next observation chosen to maximally discriminate between live hypotheses | Does deliberate evidence choice beat greedy exploration? |

L4 is the target. **L1 is the insurance policy**: it is buildable early, it will
work, and if L4 underperforms we still ship a complete, measured, reproducible
submission — and a rung that lost is a more interesting changelog entry than a
rung that won.

### 7.1 The L4 mechanism, concretely

The agent maintains a live hypothesis set, each with a prior drawn from the
runbook corpus. On each step it does not ask "what should I look at next"; it
asks **"which single observation would most change my ranking?"** — scoring
candidate observations by expected discrimination between the top hypotheses,
divided by their cost to obtain. It gathers that one thing, updates, and repeats
until either one hypothesis dominates or its budget expires.

Before returning, the verification gate requires it to state a prediction that
would be *false* if its leading hypothesis were wrong, and to actually check it
against the live stack. A hypothesis that survives an honest attempt to kill it
earns high confidence. One that was never tested does not, and the reported
confidence reflects that.

This is the mechanism that makes "technical judgment" a property of the system
rather than an adjective in the README.

### 7.2 Tool surface

Read-only, sandboxed to the target compose network:

`logs.search`, `logs.tail`, `metrics.query`, `container.inspect`, `container.stats`,
`config.read`, `config.diff`, `deploy.history`, `db.stats`, `queue.stats`, `probe.http`

No tool mutates state. There is no tool that can restart, scale, delete or
deploy. This is enforced structurally, not by prompt instruction.

---

## 8. The testbed and fault catalogue

A `docker-compose` stack — FastAPI API, Celery worker, Redis broker, Postgres,
plus a load generator — with a deterministic fault-injection CLI:

```
testbed up --fault redis-noeviction --seed 42
```

Each fault is chosen because it is a documented failure mode of scaffolded
infrastructure, not because it is convenient to inject. That principle is what
makes the case set defensible rather than arbitrary.

| ID | Fault | Why generated code produces it |
|---|---|---|
| F01 | `redis-noeviction` | `maxmemory-policy` left at default; writes fail once full |
| F02 | `restart-masks-crashloop` | `restart: always` hides an OOM-looping worker behind a healthy-looking service |
| F03 | `db-pool-exhaustion` | `pool_size` copy-pasted from a single-client example |
| F04 | `no-timeout-cascade` | Outbound call with no timeout pins every worker on one slow upstream |
| F05 | `retry-storm` | Retries without backoff or jitter turn a blip into self-inflicted DoS |
| F06 | `missing-index` | Query fine at 1k rows, fatal at 1M; no one profiled it |
| F07 | `health-check-lies` | `/health` returns 200 without checking dependencies |
| F08 | `prefetch-starvation` | Default Celery prefetch lets one worker hoard long tasks |
| F09 | `unbounded-queue` | No dead-letter queue or TTL; failures accumulate silently |
| F10 | `connection-leak` | Connections not released on the exception path; degrades over ~10 min |
| F11 | `clock-skew-auth` | Container clock drift intermittently invalidates tokens |
| F12 | `serializer-mismatch` | Broker serializer mismatch fails silently on certain payloads |

### 8.3 The knowledge corpus

The runbook memory at rung L2 and the rule set behind Mode B are the same
artefact: a curated subset of my existing multi-layer software-engineering
practice lab, which predates this competition and is listed as prior work in
`docs/PROVENANCE.md`. Relevant layers cover machine and process fundamentals,
security and supply chain, and edge and load behaviour.

Two disciplines apply to ingestion, and both are non-negotiable:

**Provenance per chunk.** Part of that lab was itself AI-generated and carries
known unverified content. Feeding unverified AI-generated engineering material
to an agent as authoritative knowledge is *precisely* the failure this project
exists to catch. Only layers I have personally verified are ingested, every
chunk carries its provenance, and the README says plainly that applying our own
thesis to our own corpus cost us content we would have liked to ship. That
caveat is a stronger signal than a corpus with no caveats.

**Ownership.** Submissions are owned by micro1 under the Participation
Agreement and may be used for model training. The lab is otherwise private. Only
material I am content to hand over permanently gets embedded; the rest is
referenced, not included.

**The hard case (required by the rules).** `F03+F06 compound`: a missing index
causes slow queries, which exhausts the connection pool, while the loudest error
in the logs is an unrelated Redis warning. The correct answer is the index. An
agent that stops at the first plausible cause reports the pool. An agent that
stops at the loudest signal reports Redis. This case exists specifically to
detect anchoring, and I expect it to be where the rungs separate most clearly.

---

## 9. Evaluation design

### 9.1 Metrics

**Primary — Root-Cause Accuracy@1 (%).** The agent emits a `root_cause` field
constrained to the fault-ID vocabulary. Exact match against the injected fault.
No LLM judge, no rubric ambiguity, no grader to argue with.

**Guardrail — False-Confident Rate (%).** Share of incidents where the agent
reported confidence ≥ 0.8 and was wrong. Lower is better. This is the number
this product exists for, and I expect it to be the most interesting result in
the report.

**Supporting metrics:**

| Metric | Definition |
|---|---|
| Evidence Precision | Cited evidence items that appear in the ground-truth evidence set for that fault |
| Time to diagnosis | Wall-clock seconds, median across seeds |
| Cost per incident | USD from token accounting, median |
| Tool calls per incident | Proxy for efficiency of evidence gathering |
| Abstention rate | How often it correctly says "insufficient evidence" |

### 9.1b Prevention metrics (Mode B)

The prevention evaluation gets its ground truth **free**, because we already
built it. The twelve fault-injected stacks are audited *before* deployment; the
injected fault is the known answer. The clean stack is the control.

| Metric | Definition |
|---|---|
| Prevention Recall@k | Latent faults surfaced in the top k audit findings, of 12 |
| False-positive rate | Findings raised against the clean control stack |
| Time-to-signal delta | Seconds to catch pre-deploy vs. minutes to diagnose post-incident |
| Operability score | Whether the service emits what a diagnosis would need |

Same testbed, same ground truth, same scorer — roughly two hours of additional
harness work. It buys the strongest claim in the submission:

> We measured the same twelve faults twice. Once as incidents, diagnosed under
> pressure. Once as pre-deploy findings, caught in seconds. The knowledge
> required was identical. Only the timing differed.

That is the hot take, it is measurable, and it is true.

### 9.2 Protocol

- **12 cases**, 11 single-fault plus 1 compound hard case.
- **3 seeds per case per rung**, because agents are stochastic and a single run
  is not a measurement. Report mean and spread; a rung whose gain sits inside
  the noise band is reported as inconclusive, not as an improvement.
- **Identical cases and identical scorer across all rungs and the baseline.**
- **Cross-model robustness run** of L0 and L4 on a second provider, to show the
  result is a property of the architecture and not of one model.

Run budget: 5 rungs x 12 cases x 3 seeds = 180 runs, plus the robustness pass.

### 9.3 Reproducibility mechanism

Every model call is content-hashed on `(provider, model, messages, tools)` and
cached to `eval/cassettes/`. Consequences:

1. Re-running the full evaluation during development is free after the first pass.
2. **A judge can reproduce every headline number with no API key and no spend**,
   via `make eval-replay`.
3. `make eval-live` re-runs against the real API for anyone who wants to verify
   the cassettes are honest.

Committing the cassettes converts reproducibility from a promise into an
artefact. It is fifteen rubric points that most entries will leave on the table.

---

## 10. Safety and ground-rule compliance

| Rule | How we satisfy it |
|---|---|
| Sandboxed consequential actions | Agent operates only against the local compose network; no tool can mutate state |
| Human approval before action | Remediation is emitted as text only. There is no apply path in the product |
| Qualified human reviewer in the loop | Output is a decision aid for an on-call engineer, explicitly not an autonomous actor |
| Legal and ethical data | 100% synthetic. No production data, no personal data, no customer data |
| Credentials excluded | Keys via environment only; `.env.example` committed, `.env` git-ignored; secret scan in CI |
| Claims tied to evidence | Every number in the README is regenerable by a committed command |
| Judges can reproduce | `make eval-replay` needs Docker and nothing else |
| Prior vs. new work delineated | `docs/PROVENANCE.md` lists every pre-existing component and what was built this weekend |

---

## 11. Deliverables and rubric mapping

| Rubric criterion | Pts | Primary artefact |
|---|---|---|
| Agent Solution & Engineering | 30 | L4 differential-selection agent, tool layer, verification gate |
| End to End Quality | 20 | Working CLI, clean diagnosis output, polished README |
| Problem & User Value | 15 | Section 2 of this document, told properly |
| Measured Improvement | 15 | `docs/CHANGELOG.md` with per-rung measured deltas |
| Reproducibility | 15 | `make eval-replay`, committed cassettes, pinned lockfiles |
| Hot Take / Insights | 5 | `docs/HOT_TAKE.md`: the same twelve faults, measured twice |

Required submission package: solution code + improvement changelog, reproduction
guide, video of up to 5 minutes, agent trajectories for every agent used.

Note that the published tie-break order is Agent Solution → Reproducibility →
Measured Improvement → End-to-End Quality. Problem framing and hot take do not
break ties. The story earns points but does not save a weak build, so the build
gets the hours.

---

## 12. Timeline

Deadline 2026-08-31 18:00 UTC. Roughly 69 hours available, ~50 working.

| Phase | Hours | Output | Gate |
|---|---|---|---|
| P0 Setup | 2 | Register, repo, CI, provenance | Registered before anything else |
| P1 Testbed | 10 | Compose stack + 12 injectable faults + tool layer | Every fault reproducible from seed |
| P2 Harness | 4 | Runner, scorer, cost accounting, cassettes | `make eval` runs end to end |
| P3 Baseline | 3 | L0 + first full evaluation | **First real number on the board** |
| P4 Rungs | 14 | L1 → L4, measured after each | Each rung measured before the next starts |
| P5 Final eval | 6 | Full run, robustness pass, results tables | All tables regenerable |
| P5b Stretch | 5 | Mode B audit + prevention eval + MCP server | **Gated: only if L4 is measured and working by hour 45** |
| P6 Deliverables | 8 | README, changelog, repro guide, trajectories, video | Clean-clone rehearsal passes |
| Buffer | 3 | Slippage | — |

**Hard rule:** P6 starts no later than 12 hours before the deadline regardless of
what is unfinished. An incomplete submission scores zero on everything; a
submission that stops at L2 with excellent evidence scores well on 70 of 100
points. The deliverables are not the victory lap, they are the deliverable.

---

## 13. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Testbed eats the schedule | High | Fault F01–F04 first; the catalogue is trimmable to 8 cases without breaking the design |
| L4 does not beat L3 | Medium | Report it honestly. A measured negative result with a clean explanation is a strong changelog entry and a better hot take than a win |
| Stochastic noise swamps the deltas | Medium | 3 seeds per case; report spread; call inconclusive results inconclusive |
| API spend overruns | Medium | Cassette caching after first pass; cheap model for dev iterations |
| Stretch scope (Mode B, MCP) eats the core | High | Hard gate at hour 45; both are additive and independently cuttable |
| Video is rushed at 3am | High | Script it during P5, record during P6, hard-stop at 5 minutes |
| Docker misbehaves on judge machines | Medium | Pin image digests; provide replay path requiring no live services |

---

## 14. Open questions

1. Which provider is primary for the headline numbers, and which is the robustness check?
2. Do we ship a `--symptom` free-text input, or only a symptom-free "here is a sick stack, go" mode? The second is harder and more impressive; the first is more realistic.
3. Does the runbook corpus at L2 help or cause anchoring? Genuinely unknown, which is why it is its own rung rather than folded into L1.
4. Eight faults done excellently, or twelve done adequately?
5. If the hour-45 gate is missed, do we ship Mode B unmeasured as a documented
   stretch, or cut it entirely? My instinct is cut it: an unmeasured feature
   dilutes End-to-End Quality and cannot earn Measured Improvement points.
6. Which lab layers clear the verification bar for ingestion, and how much of
   the corpus survives that filter?

---

## 15. Definition of done

- [ ] Registered on HackerEarth
- [ ] `git clone && make demo` works on a clean machine
- [ ] 12 faults inject deterministically from seed
- [ ] All five rungs measured on all cases, 3 seeds each
- [ ] `make eval-replay` reproduces every published number with no API key
- [ ] Changelog contains at least one honest negative result
- [ ] Trajectories exported for every agent used, including the coding agents that built this
- [ ] Video under 5 minutes, showing one real end-to-end run
- [ ] Repro guide rehearsed from a clean clone by following it literally
- [ ] No credentials anywhere in the repository
