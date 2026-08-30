import { describe, expect, it } from "vitest";

import { EMPTY, fold } from "./useRun";
import type { RunState } from "./useRun";
import type { Step } from "./types";

/** The reducer that turns one server event into what is on screen.
 *
 * This file exists because the spend panel read $0.0000 for entire runs and
 * nothing caught it. The engine had 1372 tests and the interface had none, so
 * the only thing that could find a reducer bug was a person looking at a
 * screenshot -- and the bug was found exactly that way, by the user, during a
 * demonstration.
 *
 * `fold` is pure: one prior state, one step, one new state. There was never a
 * reason not to test it.
 */

const after = (steps: Step[], from: RunState = EMPTY): RunState =>
  steps.reduce((state, step) => fold(state, step), from);

const call = (usd: number): Step => ({
  agent: "analyst:data",
  action: "model_call",
  model_call: true,
  usage: { input_tokens: 100, output_tokens: 50, usd },
});

describe("spend", () => {
  it("adds up what each call reports", () => {
    const state = after([call(0.001), call(0.002), call(0.0005)]);

    expect(state.usd).toBeCloseTo(0.0035, 6);
    expect(state.calls).toBe(3);
  });

  it("reads usage from the step, where the trajectory writes it", () => {
    // The bug. `usage` sits beside `agent` and `action`, not inside `data`,
    // and reading it from `data` found nothing on every call ever made.
    const state = after([call(0.004)]);

    expect(state.usd).toBeCloseTo(0.004, 6);
  });

  it("still reads usage nested under data", () => {
    const nested: Step = { event: "agent.finished", data: { usage: { usd: 0.007 } } };

    expect(after([nested]).usd).toBeCloseTo(0.007, 6);
  });

  it("counts nothing for a step that reports no usage", () => {
    const state = after([{ event: "agent.started", data: { module: "app/db.py" } }]);

    expect(state.calls).toBe(0);
    expect(state.usd).toBe(0);
  });

  it("reports zero cost over a positive call count when replaying", () => {
    // A replayed run genuinely spends nothing. The count is what separates it
    // from a stalled one, which is the whole reason it is on screen.
    const state = after([call(0), call(0), call(0)]);

    expect(state.usd).toBe(0);
    expect(state.calls).toBe(3);
  });

  it("bills each model for its own calls", () => {
    const state = after([
      { kind: "model", provider: "groq", model: "gpt-oss-120b" },
      call(0.002),
      { kind: "model", provider: "openai", model: "gpt-5" },
      call(0.01),
    ]);

    expect(state.byModel["groq/gpt-oss-120b"]).toBeCloseTo(0.002, 6);
    expect(state.byModel["openai/gpt-5"]).toBeCloseTo(0.01, 6);
  });

  it("lets the finished report overrule the running total", () => {
    // The report counts calls the stream never saw, so it wins at the end.
    const state = after([call(0.002), { event: "review.completed", data: { report: { usd: 0.09 } } }]);

    expect(state.usd).toBeCloseTo(0.09, 6);
  });
});

describe("the file tree", () => {
  it("marks a module as being read when a specialist opens it", () => {
    const state = after([{ event: "agent.started", data: { module: "app/db.py" } }]);

    expect(state.files["app/db.py"]).toBe("reading");
  });

  it("settles everything still reading when the run completes", () => {
    // A file left in `reading` animates on an infinite repeat, so a finished
    // review had files breathing in the tree and read as one that never ended.
    const state = after([
      { event: "agent.started", data: { module: "app/db.py" } },
      { event: "agent.started", data: { module: "app/api.py" } },
      { event: "review.completed", data: {} },
    ]);

    expect(state.files["app/db.py"]).toBe("read");
    expect(state.files["app/api.py"]).toBe("read");
  });

  it("keeps a flagged file flagged through completion", () => {
    const state = after([
      { event: "finding.detected", data: { finding: { path: "app/db.py", line: 9, symbol: "engine" } } },
      { event: "review.completed", data: {} },
    ]);

    expect(state.files["app/db.py"]).toBe("flagged");
  });
});

describe("findings", () => {
  const detected = (path: string, line: number): Step => ({
    event: "finding.detected",
    data: { finding: { path, line, symbol: "engine", layer: "data", mechanism: "pool" } },
  });

  it("collects them as they arrive", () => {
    expect(after([detected("a.py", 1), detected("b.py", 2)]).findings).toHaveLength(2);
  });

  it("does not show the same finding twice after a reconnect", () => {
    // The replay buffer redelivers, so the same event arrives again.
    expect(after([detected("a.py", 1), detected("a.py", 1)]).findings).toHaveLength(1);
  });

  it("keeps two findings that differ only by line", () => {
    expect(after([detected("a.py", 1), detected("a.py", 2)]).findings).toHaveLength(2);
  });
});

describe("stages", () => {
  it("marks everything before the reached stage as done", () => {
    // Derived rather than announced: the events say what happened, and the
    // stage is an interpretation. Anything earlier is finished by definition.
    const state = after([{ event: "agent.started", data: { module: "app/db.py" } }]);

    expect(state.stages.survey).toBe("done");
    expect(state.stages.map).toBe("done");
    expect(state.stages.specialists).toBe("running");
  });

  it("finishes every stage when the run completes", () => {
    const state = after([{ event: "review.completed", data: {} }]);

    expect(Object.values(state.stages).every((s) => s === "done")).toBe(true);
  });
});

describe("failure", () => {
  it("keeps the reason the server gave", () => {
    const state = after([{ event: "review.failed", data: { detail: "the provider refused" } }]);

    expect(state.failed).toBe("the provider refused");
  });

  it("never leaves a failure without a reason", () => {
    expect(after([{ event: "review.failed", data: {} }]).failed).toBeTruthy();
  });
});

describe("counts", () => {
  it("takes the module total from the structure event", () => {
    const state = after([{ event: "structure.discovered", data: { modules: 476 } }]);

    expect(state.total).toBe(476);
  });

  it("prefers the scheduler's own read count at the end", () => {
    // It knows which modules it declined to spend on; the live stream does not.
    const state = after([
      { event: "agent.started", data: { module: "a.py" } },
      { event: "review.completed", data: { report: { coverage: { analysed: ["a.py", "b.py", "c.py"] } } } },
    ]);

    expect(state.read).toBe(3);
  });
});
