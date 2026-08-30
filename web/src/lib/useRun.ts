import { useCallback, useRef, useState } from "react";
import type { Discovery, Report, Stage, StageKey, StageState, Step } from "./types";

/** What the file tree knows about one module while a review is running. */
export type FileState = "unread" | "reading" | "read" | "flagged";

interface RunState {
  steps: Step[];
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

/** One step, applied to what is on screen. Pure, so it is testable on its own. */
export function fold(prior: RunState, step: Step): RunState {
  const next: RunState = { ...prior, steps: [...prior.steps, step].slice(-400) };

  // The typed vocabulary. The server names its own phases now, so the
  // interface reads those rather than guessing from a shape.
  const data = step.data ?? {};
  if (step.event === "review.started" && data.model) next.model = String(data.model);
  if (step.event === "review.failed") next.failed = String(data.detail ?? "the run failed");
  if (step.event === "structure.discovered" && typeof data.modules === "number") {
    next.total = data.modules;
  }
  if (step.event === "agent.started" && typeof data.module === "string") {
    next.files = { ...next.files, [data.module]: "reading" };
  }
  if (step.event === "finding.detected") {
    const found = (data.finding ?? {}) as { path?: string };
    if (found.path) next.files = { ...next.files, [found.path]: "flagged" };
  }

  if (step.kind === "model" && step.model) next.model = `${step.provider}/${step.model}`;
  // The report is authoritative about cost. Module events carry a running
  // total that stops the moment the last module lands, so a review whose last
  // work was the deterministic passes reported nothing.
  if (step.kind === "done" && step.report) next.usd = step.report.usd;
  if (step.event === "review.completed") {
    const report = data.report as { usd?: number } | undefined;
    if (report?.usd !== undefined) next.usd = report.usd;
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
