# Agent trajectories

A recording of what each agent did, produced by the run rather than written
about it afterwards. Line-delimited JSON, one step per line, so it can be
grepped and so a file from an interrupted run is readable up to where it
stopped.

## What is here

| file | what it is |
|---|---|
| `augury-B01.jsonl` | One full pipeline review of case B01: 59 steps, 8 findings, $0.028 |

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
of that single call, and the number of retries it took. Retries are recorded
rather than smoothed over: a run that needed three attempts is a different run
from one that needed none.

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
