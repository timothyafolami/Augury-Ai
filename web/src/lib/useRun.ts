import { useCallback, useRef, useState } from "react";
import type { Discovery, Finding, Report, Stage, StageKey, StageState, Step } from "./types";

/** What the file tree knows about one module while a review is running. */
export type FileState = "unread" | "reading" | "read" | "flagged";

interface RunState {
  steps: Step[];
  /** Findings as they arrive, so the panel fills while the run is working.
   *  Rendering only the finished report meant a minute of agents moving over
   *  an empty panel, which reads as a simulation of a review. */
  findings: Finding[];
  stages: Record<StageKey, StageState>;
  files: Record<string, FileState>;
  spans: { agent: string; startedAt: number; endedAt: number | null }[];
  usd: number;
  read: number;
  total: number;
  model: string;
  failed: string;
}

const EMPTY: RunState = {
  steps: [],
  findings: [],
  stages: { survey: "waiting", map: "waiting", schema: "waiting", specialists: "waiting", report: "waiting" },
  files: {},
  spans: [],
  usd: 0,
  read: 0,
  total: 0,
  model: "",
  failed: "",
};

/** Drives one review: discovery, then the live stream, then the report. */
export function useRun() {
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [run, setRun] = useState<RunState>(EMPTY);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const source = useRef<EventSource | null>(null);

  const loadStages = useCallback(async () => {
    const answer = await fetch("/api/stages");
    setStages(await answer.json());
  }, []);

  const discover = useCallback(async (path: string, scope: string) => {
    setBusy(true);
    setReport(null);
    setRun(EMPTY);
    try {
      const answer = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, scope }),
      });
      if (!answer.ok) {
        const { detail } = await answer.json().catch(() => ({ detail: answer.statusText }));
        throw new Error(String(detail));
      }
      const found: Discovery = await answer.json();
      setDiscovery(found);
      return found;
    } finally {
      setBusy(false);
    }
  }, []);

  const review = useCallback(
    async (path: string, scope: string, budget: number) => {
      const started = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, scope, budget }),
      });
      if (!started.ok) {
        const { detail } = await started.json().catch(() => ({ detail: started.statusText }));
        throw new Error(String(detail));
      }
      const { runId } = await started.json();

      source.current?.close();
      const stream = new EventSource(`/api/runs/${runId}/events`);
      source.current = stream;
      const openedAt = Date.now();

      stream.onmessage = (raw) => {
        const step: Step = { ...JSON.parse(raw.data), at: Date.now() - openedAt };
        setRun((prior) => fold(prior, step));
        const finished = step.event === "review.completed" || step.kind === "done";
        if (finished) {
          const report = (step.data?.report ?? step.report) as Report | undefined;
          if (report) setReport(report);
          stream.close();
        }
        if (step.event === "review.failed" || step.kind === "failed") stream.close();
      };
      stream.onerror = () => stream.close();
      return runId;
    },
    [],
  );

  return { discovery, stages, run, report, busy, loadStages, discover, review };
}

const ORDER: StageKey[] = ["survey", "map", "schema", "specialists", "report"];

/** Which stage an event proves the run has reached.
 *
 * Derived rather than announced, because the events name what happened and a
 * stage is an interpretation of that. Anything earlier than the stage an event
 * proves is finished by definition, which is what stops a stage that emits
 * nothing of its own from staying grey for the whole run.
 */
const STAGE_OF: Record<string, StageKey | undefined> = {
  "scout.started": "survey",
  "service.detected": "survey",
  "language.detected": "map",
  "structure.discovered": "map",
  "model.built": "map",
  "research.started": "schema",
  "research.finished": "schema",
  "agent.started": "specialists",
  "agent.handoff": "specialists",
  "agent.finished": "specialists",
  "coverage.computed": "report",
  "prediction.generated": "report",
};

/** One step, applied to what is on screen. Pure, so it is testable on its own. */
export function fold(prior: RunState, step: Step): RunState {
  const next: RunState = { ...prior, steps: [...prior.steps, step].slice(-400) };

  // The typed vocabulary. The server names its own phases now, so the
  // interface reads those rather than guessing from a shape.
  const data = step.data ?? {};
  if (step.event === "review.started" && data.model) next.model = String(data.model);

  // Stage state, derived from the typed events. The old explicit stage event
  // went away with the vocabulary and nothing replaced it, so every stage sat
  // grey for the whole run and the pipeline read as a diagram rather than as
  // a thing that was happening.
  const reached = STAGE_OF[step.event ?? ""];
  if (reached) {
    next.stages = { ...prior.stages };
    let seen = false;
    for (const key of ORDER) {
      if (key === reached) {
        next.stages[key] = "running";
        seen = true;
      } else if (!seen) {
        next.stages[key] = "done";
      }
    }
  }
  if (step.event === "review.completed") {
    next.stages = { survey: "done", map: "done", schema: "done", specialists: "done", report: "done" };
  }
  if (step.event === "review.failed") next.failed = String(data.detail ?? "the run failed");
  if (step.event === "structure.discovered" && typeof data.modules === "number") {
    next.total = data.modules;
  }
  if (step.event === "agent.started" && typeof data.module === "string") {
    next.files = { ...next.files, [data.module]: "reading" };
    // Modules a specialist actually opened. The old per-module progress event
    // is gone, so this is now the only live count, and a counter stuck at zero
    // while the tree lights up makes a working run look like a mock of one.
    next.read = Object.keys({ ...next.files }).length;
  }
  if (step.event === "finding.detected") {
    const found = (data.finding ?? {}) as Finding;
    if (found.path) next.files = { ...next.files, [found.path]: "flagged" };
    // Keyed on where it is, so a redelivered event after a reconnect does not
    // show the same finding twice.
    const already = prior.findings.some(
      (held) => held.path === found.path && held.line === found.line && held.symbol === found.symbol,
    );
    if (!already) next.findings = [...prior.findings, found];
  }

  if (step.kind === "model" && step.model) next.model = `${step.provider}/${step.model}`;
  // The report is authoritative about cost. Module events carry a running
  // total that stops the moment the last module lands, so a review whose last
  // work was the deterministic passes reported nothing.
  if (step.kind === "done" && step.report) next.usd = step.report.usd;
  if (step.event === "review.completed") {
    const report = data.report as
      | { usd?: number; coverage?: { analysed?: string[] } }
      | undefined;
    if (report?.usd !== undefined) next.usd = report.usd;
    // The scheduler's own count, which is authoritative: it knows which
    // modules it declined to spend on and the live stream does not.
    if (report?.coverage?.analysed) next.read = report.coverage.analysed.length;
  }
  if (step.kind === "failed") next.failed = String(step.detail ?? "the run failed");

  if (step.kind === "stage" && step.stage && step.state) {
    next.stages = { ...prior.stages, [step.stage]: step.state };
  }

  if (step.kind === "module" && step.path) {
    next.files = { ...prior.files, [step.path]: (step.findings ?? 0) > 0 ? "flagged" : "read" };
    next.usd = step.usd ?? prior.usd;
    next.read = step.read ?? prior.read;
    next.total = step.total ?? prior.total;
  }

  // A step recorded by an agent, from the trajectory the reviewer writes
  // anyway. The file it names is being read right now.
  const named = step.agent ?? (step.event?.startsWith("agent.") ? String(data.agent ?? "") : "");
  if (named) {
    const open = prior.spans.findIndex((s) => s.agent === named && s.endedAt === null);
    if (step.event === "agent.started" || open === -1) {
      next.spans = [...prior.spans, { agent: named, startedAt: step.at ?? 0, endedAt: null }];
    } else {
      next.spans = prior.spans.map((s, i) => (i === open ? { ...s, endedAt: step.at ?? null } : s));
    }
  }

  if (step.agent) {
    const path = typeof step.detail === "object" ? (step.detail?.path as string | undefined) : undefined;
    if (path && prior.files[path] === undefined) {
      next.files = { ...next.files, [path]: "reading" };
    }
    const open = prior.spans.findIndex((s) => s.agent === step.agent && s.endedAt === null);
    if (open === -1) {
      next.spans = [...prior.spans, { agent: step.agent, startedAt: step.at ?? 0, endedAt: null }];
    } else {
      next.spans = prior.spans.map((s, i) => (i === open ? { ...s, endedAt: step.at ?? null } : s));
    }
  }

  return next;
}
