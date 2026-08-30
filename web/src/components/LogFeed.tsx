import { useEffect, useRef } from "react";
import type { Step } from "../lib/types";

/** The raw stream, unstyled on purpose.
 *
 * Everything above this is a rendering of these lines. Showing them lets a
 * sceptical viewer check that the diagram is not a cartoon over a spinner,
 * which is the objection this whole category has earned.
 */
export function LogFeed({ steps }: { steps: Step[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [steps.length]);

  return (
    <div className="h-full overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed">
      {steps.map((step, index) => (
        <div key={index} className="flex gap-2 py-px">
          <span className="shrink-0 text-mist/40">
            {String(((step.at ?? 0) / 1000).toFixed(1)).padStart(5)}s
          </span>
          <span className="shrink-0 text-augur-400">
            {step.agent ?? step.kind ?? "·"}
          </span>
          <span className="min-w-0 flex-1 truncate text-mist">
            {describe(step)}
          </span>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

function describe(step: Step): string {
  if (step.kind === "module") {
    return `${step.path} — ${step.findings} found · read ${step.read}/${step.total} · $${(step.usd ?? 0).toFixed(4)}`;
  }
  if (step.kind === "stage") return `${step.stage} ${step.state}`;
  if (step.kind === "model") return `${step.provider}/${step.model}`;
  if (step.action) {
    const detail = typeof step.detail === "object" ? JSON.stringify(step.detail) : String(step.detail ?? "");
    return `${step.action} ${detail}`.slice(0, 300);
  }
  return typeof step.detail === "string" ? step.detail : JSON.stringify(step).slice(0, 240);
}
