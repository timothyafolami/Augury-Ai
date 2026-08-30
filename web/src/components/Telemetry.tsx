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
        const who = (step.agent ?? step.kind ?? "system").toUpperCase();
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
            <p className="mt-1 pl-[3.4rem] font-mono text-[11px] leading-relaxed text-chalk/75">
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

function say(step: Step): string {
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
