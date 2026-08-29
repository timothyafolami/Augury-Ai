# What existed before, and what was built for this

The competition asks for this to be clear. It is also just useful: a reader
should be able to tell which parts of a submission are the work and which are
the ground it was built on.

---

## Built during the competition

Everything under `src/`, `tests/`, `eval/` and `docs/`. Every commit in this
repository was made during the competition window, one file per commit, and
each message says what changed in that file.

| | |
|---|---|
| `src/augury/core/cartography/` | Repository mapping across six languages, import resolution, signal detection |
| `src/augury/core/scheduling/` | Budget-bounded module selection and coverage reporting |
| `src/augury/core/adapters/` | Provider adapters, pricing, record-and-replay cassettes |
| `src/augury/core/` | Prediction and finding types, scoring, the metric vocabulary |
| `src/augury/agents/` | Baseline reviewer, triage, the pipeline arm |
| `src/augury/evaluation/` | Cases, runner, prover, reconciler, sweep |
| `src/augury/prompts/` | Every prompt, including the eight layer briefs |
| `src/augury/cli/` | The command line |
| `eval/cases/` | Both case repositories and all five experiments |
| `tests/` | 321 tests |

---

## Prior work this is built on

### The software engineering practice lab

A private multi-layer lab of mine that predates the competition by months. It
is the source of the engineering knowledge in this system, and it is why the
specialists have any authority.

**What was taken:** the *arguments*. The eight layer briefs in
`src/augury/prompts/layers/` were written for this submission, but they say
what the corresponding lab layer teaches. The defect taxonomy in
`docs/DEFECT_TAXONOMY.md` traces every seeded defect to the lab topic that
defines it.

**What was not taken:** no lab file is copied into this repository. The
competition's terms transfer ownership of what is submitted, and the lab is not
mine alone to hand over in full.

Three lines from it are quoted in the README and the taxonomy, because they
state this project's thesis better than anything written for it, and they were
written before it existed:

- `03-data/01` — the profile of a bug that survives review
- `03-data/06` — N+1 is detectable by counting, not by reading
- `08-craft/03` — a swallowed exception becomes a fast, successful, empty response

**One thing deliberately left out.** Part of that lab was itself AI-generated
and carries known unverified content, recorded in its own `DEFECTS.md`. Feeding
unverified AI-generated engineering material to an agent as authoritative
knowledge is precisely the failure this project exists to catch, so only
material I have personally verified informed the briefs. That cost real
coverage, and saying so is more useful than a corpus with no caveats.

### The compose harness and load scenarios

The same lab contains a working `docker-compose` stack, k6 scenarios
(`pool_ramp`, `arrival_rate`, `fanout`), a Prometheus configuration and fifteen
captured load runs. **None of it is used in this submission.** The Prover ended
up running in-process experiments instead, which need no Docker and which a
judge can run in two seconds. The harness is listed here because it shaped the
design before that decision, not because it is present.

---

## Third-party dependencies

All standard, all pinned in `uv.lock`, all used as intended.

| | |
|---|---|
| `autogen-core`, `autogen-ext` 0.7.5 | Model client abstraction and the agent runtime |
| `pydantic` 2.x | Every schema and validator |
| `tree-sitter`, `tree-sitter-language-pack` | Parsing the five non-Python languages |
| `typer`, `rich` | Command line |
| `sqlalchemy`, `aiosqlite`, `httpx` | Only the case experiments; not the reviewer |
| `pytest`, `ruff`, `mypy` | Development |

The case repositories under `eval/cases/` contain deliberately defective code
written for this submission. They are excluded from our linters, because
linting them would fight the seeding.

---

## Tools used to build this

Claude Code throughout, as the competition requires and discloses. The
trajectories are in `docs/trajectories/`.

Worth stating plainly, because it is the same claim this project makes about
everyone else's code: **the reviews that shaped this repository were done by
adversarial review agents, and they found real defects in it.** Among them, a
cost-accounting bug that inflated reported spend quadratically, a metric that
scored a reviewer emitting `p99 >= 0ms` at a perfect 1.000, and a `.env` loader
that let a repository under review set environment variables in the process
reviewing it. Each is recorded in `docs/CHANGELOG.md` with what it cost to
find.
