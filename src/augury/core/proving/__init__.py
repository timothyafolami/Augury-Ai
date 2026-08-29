"""Proving a forecast instead of publishing it.

A finding that says `worker_saturation at_least 0.9x at stripe_latency=2s` is
falsifiable, which is not the same as settled. The seeded cases ship
hand-written experiments; a real repository ships none, so the experiment is
generated, run, and graded.

Every part of that is dangerous in its own way, and the design is mostly about
the danger:

- **Generated code executes.** It runs in a subprocess with a timeout, and its
  source is written to disk *before* it runs, so whatever the verdict someone
  can read what actually ran.
- **A broken experiment must not look like a result.** No number, a crash, or a
  timeout is Broken -- never zero, never a guess. Publishing a plausible number
  produced by a broken experiment is the failure this project has made four
  times and documented each one.
"""

from augury.core.proving.model import Experiment, Proof
from augury.core.proving.runner import prove_finding

__all__ = ["Experiment", "Proof", "prove_finding"]
