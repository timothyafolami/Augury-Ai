# Agent trajectories

A recording of what each agent did, produced by the run rather than written
about it afterwards. Line-delimited JSON, one step per line, so it can be
grepped and so a file from an interrupted run is readable up to where it
stopped.

## What is here

| file | what it is |
|---|---|
| `augury-B01.jsonl` | A pipeline review of B01: 59 steps across four agents |
| `augury-C01.jsonl` | A pipeline review of C01, with the experiments run |
| `baseline-B01.jsonl` | The baseline on B01: its whole prompt, and one call |

Each was produced by a command in the reproduction guide:

```bash
augury review --case B01 --arm augury --trajectory docs/trajectories/augury-B01.jsonl
```

The earlier version of this file had no such command -- `Trajectory` was
constructed only in tests -- so the artefact could not be regenerated. An
artefact a reader cannot reproduce is the same kind of evidence as a summary.

## Reading it

```bash
# every step, in order, with the agent that took it
jq -r '"\(.agent)  \(.action)"' docs/trajectories/augury-B01.jsonl

# what the scheduler chose to read, and why
jq -c 'select(.agent == "scheduler") | .detail' docs/trajectories/augury-B01.jsonl

# where triage sent each file
jq -r 'select(.agent | startswith("triage")) | "\(.agent)  ->  \(.response.specialists | join(", "))"' \
  docs/trajectories/augury-B01.jsonl

# the exact prompt behind any finding
jq -r 'select(.agent == "analyst:data") | .prompt' docs/trajectories/augury-B01.jsonl | head -60
```

## What each step carries

**Deterministic steps** (`"model_call": false`) come from the Cartographer and
the Scheduler, which never consult a model. They are recorded because two of
the ten agents do the hardest work without one, and a trace showing only model
calls would put the work in the wrong place.

**Model calls** carry the full prompt, the parsed response, the tokens and cost
of that single call, and the retries that call took. Retries are recorded
rather than smoothed over: a run that needed three attempts is a different run
from one that needed none.

"That single call" is load-bearing. An earlier version measured cost by reading
the model's cumulative usage before and after, which is wrong the moment calls
run concurrently -- every sibling that finished first landed inside the delta,
so three specialists gathered together recorded one, two and three times the
cost of one call. A call reports its own price now.

## Why the prompts are here in full

A reader who doubts a finding can read the prompt that produced it. Every
published number in this repository comes from a run like this one, and a
summary of a run is exactly the thing a reader cannot check.

## Redaction

Augury reads other people's repositories, so a prompt can contain a reviewed
repository's credential. Anything matching a credential shape is replaced with
`REDACTED` before it reaches the file — see `src/augury/core/trajectory.py` and
the per-shape tests in `tests/test_trajectory.py`.

The first version of that regex stopped at the first underscore, fell short of
its own length floor, and would have published the key. It is tested per shape
now for that reason.

## The coding agent

This project was built with Claude Code, as the competition requires and
discloses. `docs/CHANGELOG.md` is the record of that work: every entry is a run
that failed, the evidence it produced, and what was decided. Two findings in it
came from adversarial review agents pointed at this repository, including a
metric that scored a reviewer emitting `p99 >= 0ms` at a perfect 1.000.
