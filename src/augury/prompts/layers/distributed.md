What happens when a message is delivered twice, not at all, or out of order,
and when the answer to "did it work" is genuinely unknown.

The defining problem is the ambiguous result: a call times out and the caller
cannot distinguish "it did not happen" from "it happened and the reply was
lost". Every retry in the system is built on top of that ambiguity, so every
handler a retry can reach has to be safe to run twice.

Specifically look for:

- Handlers that a retry or a redelivery can reach, which are not idempotent:
  they insert, increment, charge, send or append. Predict `duplicate_side_effects` under N redeliveries, and the `final_balance` that follows.
- Idempotency keys that are checked and then written non-atomically, which is
  the same race one level up.
- Side effects performed inside a transaction that commits separately from the
  message acknowledgement, so a crash between the two loses or duplicates work.
  Name which of the two it is.
- Ordering assumed across partitions, consumers or retries where none is
  guaranteed.
- Wall-clock time used to decide ordering, expiry or leadership. Clocks lie,
  and the skew is not bounded by anything you control.
- A lease or a lock with no fencing token, so a delayed holder can still act
  after losing it.

Say precisely what an operator would observe: the duplicate charge, the lost
job, the row that two writers both believe they own.
