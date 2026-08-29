You write one experiment. It measures a single number and prints it.

Something claimed a defect exists in this repository and predicted what a
measurement would show. Your job is to settle that, not to agree with it. An
experiment that can only produce the predicted answer has measured nothing.

## The claim

File: `{path}`, symbol `{symbol}`
Mechanism: {mechanism}

**Prediction:** `{metric} {comparator} {value}{unit}` under `{condition}`

## The code

```{language}
{source}
```

## What you must write

A standalone Python script. It may import from the repository -- the repository
root is on `PYTHONPATH` and also in `AUGURY_CASE_REPO`.

- **Print the measurement as the last line, alone.** Nothing after it. The last
  number printed is read as the answer, so a trailing log line becomes the
  result.
- Print what you are doing before that, so a reader can follow it.
- **No network, no external services.** No real database, no HTTP to anything
  that is not localhost, no credentials. If the claim cannot be measured
  without them, say so in `refusal` and write nothing.
- Exit non-zero if the thing you meant to measure did not happen. A script that
  cannot do its job must fail rather than print a plausible number.

## What makes an experiment broken rather than a prediction wrong

Write it so these cannot happen, and say in `explanation` which one you guarded:

- It ran for under about ten milliseconds, so it measured the scheduler.
- It counted its own setup: a query issued by the harness, a connection the
  test opened.
- The code path you meant to exercise was never reached. Assert that it was.
- The optimiser removed the work. Consume the result.
- A fixed number of workers self-throttles when the service slows, so no queue
  can form. Drive it at a fixed arrival rate instead.

This last section is the difference between an experiment and a demonstration.
A measurement you cannot defend is worse than no measurement, because it is
believed.

## Respond with

- `source`: the whole script
- `explanation`: what it measures, and which broken-experiment trap you guarded
- `refusal`: empty, or why this claim cannot be measured without a real service
