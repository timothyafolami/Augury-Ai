import { AnimatePresence, motion } from "framer-motion";
import type { StageKey, StageState } from "../lib/types";

/** The orchestration, emerging as it happens.
 *
 * Nodes appear when the pipeline reaches them rather than all at once, because
 * a graph drawn in full before anything has run is a diagram of intent. The
 * eight specialists are the real ones from core/layers.py, and a specialist
 * only appears once a module has actually been routed to it.
 */

const TIERS: { key: StageKey; label: string; children?: string[] }[] = [
  { key: "survey", label: "SURVEYOR" },
  { key: "map", label: "CARTOGRAPHER" },
  { key: "schema", label: "SCHEMA · DEPENDENCIES" },
  { key: "specialists", label: "SPECIALISTS" },
  { key: "report", label: "RECONCILE · GATE · RANK" },
];

export function AgentGraph({
  stages,
  active,
  counts,
}: {
  stages: Record<StageKey, StageState>;
  active: string[];
  counts: Record<string, number>;
}) {
  return (
    <div className="flex flex-col items-center gap-0 py-1">
      {TIERS.map((tier, index) => {
        const state = stages[tier.key] ?? "waiting";
        const reached = state !== "waiting";
        return (
          <div key={tier.key} className="flex w-full flex-col items-center">
            {index > 0 && (
              <motion.div
                className="h-5 w-px"
                initial={{ scaleY: 0 }}
                animate={{ scaleY: reached ? 1 : 0.25 }}
                style={{
                  originY: 0,
                  background: reached ? "var(--color-augur-500)" : "var(--color-edge)",
                }}
                transition={{ duration: 0.4 }}
              />
            )}

            <motion.div
              initial={{ opacity: 0.3 }}
              animate={{ opacity: reached ? 1 : 0.3 }}
              className={`border px-4 py-1.5 font-mono text-[11px] tracking-widest ${
                state === "running"
                  ? "border-augur-400 bg-augur-600/20 text-augur-100"
                  : state === "done"
                    ? "border-edge bg-slate-panel text-chalk"
                    : "border-edge/60 text-mist/50"
              }`}
            >
              {tier.label}
              {state === "running" && <PulseDot />}
            </motion.div>

            {tier.key === "specialists" && (
              <div className="mt-4 flex min-h-[2.2rem] flex-wrap items-start justify-center gap-1.5">
                <AnimatePresence>
                  {active.map((name) => (
                    <motion.span
                      key={name}
                      initial={{ opacity: 0, y: -6, scale: 0.92 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      transition={{ duration: 0.25 }}
                      className="border border-augur-500/40 bg-augur-900/30 px-2.5 py-1 font-mono text-[10px] tracking-wider text-augur-200"
                    >
                      {name}
                      {counts[name] ? (
                        <span className="ml-1.5 text-augur-400">{counts[name]}</span>
                      ) : null}
                    </motion.span>
                  ))}
                </AnimatePresence>
                {active.length === 0 && (
                  <span className="font-mono text-[10px] text-mist/40">
                    routed by the signals each file raises
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PulseDot() {
  return (
    <motion.span
      className="ml-2 inline-block h-1.5 w-1.5 rounded-full bg-augur-300 align-middle"
      animate={{ opacity: [1, 0.2, 1] }}
      transition={{ duration: 1.4, repeat: Infinity }}
    />
  );
}
