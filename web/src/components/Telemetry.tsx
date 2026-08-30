import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { Step } from "../lib/types";

/** Agent reasoning, as it is recorded.
 *
 * Every line here is one entry from the trajectory the reviewer writes anyway,
 * which is the file handed to a judge. It reads as reasoning rather than as
 * terminal output because that is what it is: the deterministic steps are in
 * here alongside the model calls, since two of the agents never call a model
 * and a feed showing only the calls would misrepresent where the work happens.
 */
export function Telemetry({ steps }: { steps: Step[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [steps.length]);

  return (
    <div className="h-full overflow-y-auto pr-1">
      {steps.length === 0 && (
        <p className="py-8 text-center font-mono text-[11px] text-mist/50">
          nothing has happened yet
        </p>
      )}
      {steps.map((step, index) => {
        const who = actor(step);
        return (
          <motion.div
            key={index}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="border-b border-edge/40 py-2.5 last:border-0"
          >
            <div className="flex items-baseline gap-2.5">
              <span className="font-mono text-[10px] tabular-nums text-mist/50">
                {clock(step.at ?? 0)}
              </span>
              <span
                className={`font-mono text-[10px] tracking-wider ${
                  step.model_call ? "text-augur-300" : "text-mist"
                }`}
              >
                {who}
              </span>
              {step.model_call && (
                <span className="rounded-sm bg-augur-900/50 px-1 font-mono text-[9px] text-augur-300">
                  model
                </span>
              )}
            </div>
            <p
              className={`mt-1 pl-[3.4rem] font-mono text-[11px] leading-relaxed ${
                step.event?.startsWith("research") ? "text-augur-200" : "text-chalk/75"
              }`}
            >
              {say(step)}
            </p>
          </motion.div>
        );
      })}
      <div ref={end} />
    </div>
  );
}

function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** Who this step belongs to.
 *
 * The typed events name a phase, and the trajectory names an agent. Both are
 * in the same feed on purpose: two of the agents never call a model, and a
 * feed showing only calls would misrepresent where the work happens.
 */
function actor(step: Step): string {
  if (step.event) return step.event.split(".")[0].toUpperCase();
  return (step.agent ?? step.kind ?? "system").toUpperCase();
}

/** Research is the reviewer going and finding something, so it is worth its
 *  own line rather than a JSON blob. */
function research(data: Record<string, unknown>, done: boolean): string {
  const subject = String(data.subject ?? "");
  const source = String(data.source ?? "");
  if (!done) return `asking ${source} about ${subject}`;
  return data.found ? `${source} answered about ${subject}` : `${source} had nothing on ${subject}`;
}

function say(step: Step): string {
  // The typed vocabulary, which is what the server emits now.
  if (step.event) {
    const data = step.data ?? {};
    if (step.event === "research.started") return research(data, false);
    if (step.event === "research.finished") return research(data, true);
    if (step.event === "review.started") {
      return `reviewing ${data.name} / ${data.scope || "all of it"} with ${data.model}`;
    }
    if (step.event === "language.detected") return `${data.modules} modules of ${data.language}`;
    if (step.event === "service.detected") {
      // A declared ceiling is the fact this whole stage exists to surface, so
      // it is spelled out rather than shown as a bare number.
      const ceiling =
        typeof data.capacity === "number" ? ` — runs ${data.capacity} at a time` : "";
      return `${data.service} built from ${data.sourceRoot}${ceiling}`;
    }
    if (step.event === "structure.discovered") {
      return `${data.modules} modules, ${data.reachable} reachable, ${data.unreachable} not`;
    }
    if (step.event === "agent.started") return `${data.agent} reading ${data.module ?? ""}`;
    if (step.event === "agent.handoff") return `${data.from} to ${data.to}: ${data.why ?? ""}`;
    if (step.event === "agent.finished") return `${data.agent} — ${data.findings} found`;
    if (step.event === "finding.detected") {
      const found = (data.finding ?? {}) as Record<string, unknown>;
      return `${found.symbol ?? found.rule ?? ""} in ${found.path ?? ""}`;
    }
    if (step.event === "context.updated") return `${data.what}: ${data.count}`;
    if (step.event === "review.failed") return String(data.detail ?? "the run failed");
    // A phase with nothing worth saying is still worth showing as a beat.
    const shown = Object.entries(data)
      .filter(([, value]) => typeof value !== "object")
      .slice(0, 3)
      .map(([key, value]) => `${key}=${trim(String(value))}`)
      .join("  ");
    return `${step.event.split(".").slice(1).join(" ")}  ${shown}`.trim();
  }

  if (step.kind === "module") {
    return `${step.path} — ${step.findings ?? 0} finding${step.findings === 1 ? "" : "s"}, ${step.read}/${step.total} read, $${(step.usd ?? 0).toFixed(4)}`;
  }
  if (step.kind === "stage") return `${step.stage} ${step.state}`;
  if (step.kind === "model") return `using ${step.provider}/${step.model}`;
  if (step.kind === "deterministic") return "schema and dependency passes, no model, no cost";
  if (step.action) {
    const detail =
      typeof step.detail === "object" && step.detail
        ? Object.entries(step.detail)
            .slice(0, 4)
            .map(([key, value]) => `${key}=${trim(String(value))}`)
            .join("  ")
        : String(step.detail ?? "");
    return `${step.action}  ${detail}`.trim();
  }
  return typeof step.detail === "string" ? step.detail : JSON.stringify(step).slice(0, 200);
}

function trim(value: string): string {
  return value.length > 54 ? `${value.slice(0, 54)}…` : value;
}
