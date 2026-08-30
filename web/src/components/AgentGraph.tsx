import { AnimatePresence, motion } from "framer-motion";
import type { StageKey, StageState } from "../lib/types";

/** The pipeline as it actually runs, loop included.
 *
 * Drawn straight, this said the specialists run once. They do not: the
 * scheduler re-ranks after every module, promotes the neighbours of anything
 * that produced a finding, and hands out the next batch, so triage and the
 * specialists are inside a loop that runs until the budget is spent or nothing
 * left is worth reading. A straight line is a diagram of a simpler system than
 * the one being watched.
 *
 * The free stages say so. Five of the seven consult no model, and that is the
 * argument this project makes about cost, so it is on the diagram rather than
 * in a paragraph underneath it.
 */

interface Tier {
  key: StageKey;
  label: string;
  free: boolean;
  note?: string;
}

const BEFORE: Tier[] = [
  { key: "survey", label: "SURVEYOR", free: true, note: "the deployment, before any code" },
  { key: "map", label: "CARTOGRAPHER", free: true, note: "six languages, imports, request path" },
  {
    key: "schema",
    label: "DEPLOYMENT · SCHEMA · DEPENDENCIES",
    free: true,
    note: "deterministic, and the largest source of findings",
  },
];

const AFTER: Tier[] = [
  {
    key: "report",
    label: "RECONCILE · GATE · RANK",
    free: true,
    note: "five passes that withdraw claims the specialists made",
  },
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
  const looping = stages.specialists === "running";

  return (
    <div className="flex flex-col items-center">
      {BEFORE.map((tier, index) => (
        <Step key={tier.key} tier={tier} state={stages[tier.key]} first={index === 0} />
      ))}

      <Joint lit={stages.specialists !== "waiting"} />

      {/* The loop. Everything inside it runs once per batch, not once. */}
      <div className="relative w-full max-w-lg border border-dashed border-edge px-4 py-4">
        <span className="absolute -top-2 left-4 bg-void px-2 font-mono text-[9px] uppercase tracking-widest text-mist">
          per batch, until the budget is spent
        </span>
        {looping && (
          <motion.span
            className="absolute -top-2 right-4 bg-void px-2 font-mono text-[9px] uppercase tracking-widest text-augur-300"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.6, repeat: Infinity }}
          >
            looping
          </motion.span>
        )}

        <div className="flex flex-col items-center">
          <Box label="SCHEDULER" state={stages.specialists} note="ranks by yield per dollar" />
          <Joint lit={stages.specialists !== "waiting"} />
          <Box label="TRIAGE" state={stages.specialists} note="narrows, never widens" />
          <Joint lit={stages.specialists !== "waiting"} />

          <Box label="SPECIALISTS" state={stages.specialists} note="concurrent, one concern each" />

          <div className="mt-3 flex min-h-[2rem] flex-wrap items-start justify-center gap-1.5">
            <AnimatePresence>
              {active.map((name) => (
                <motion.span
                  key={name}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  className="border border-augur-500/40 bg-augur-900/30 px-2 py-0.5 font-mono text-[10px] tracking-wider text-augur-200"
                >
                  {name}
                  {counts[name] ? <span className="ml-1.5 text-augur-400">{counts[name]}</span> : null}
                </motion.span>
              ))}
            </AnimatePresence>
            {active.length === 0 && (
              <span className="font-mono text-[10px] text-mist/40">
                routed by the signals each file raises
              </span>
            )}
          </div>
        </div>

        {/* The return edge, which is the whole point of the box. */}
        <svg className="pointer-events-none absolute inset-y-4 -left-px w-6" aria-hidden>
          <motion.path
            d="M 22 12 C 4 12, 4 12, 4 60 C 4 120, 4 120, 22 120"
            fill="none"
            stroke={looping ? "var(--color-augur-500)" : "var(--color-edge)"}
            strokeWidth="1"
            strokeDasharray="3 3"
            animate={looping ? { strokeDashoffset: [0, -12] } : {}}
            transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
          />
        </svg>
      </div>

      <Joint lit={stages.report !== "waiting"} />
      {AFTER.map((tier) => (
        <Step key={tier.key} tier={tier} state={stages[tier.key]} />
      ))}
      <Joint lit={stages.report === "done"} />
      <Box
        label="SYNTHESIS"
        state={stages.report === "done" ? "done" : "waiting"}
        note="what no one specialist could say"
      />
    </div>
  );
}

function Step({ tier, state, first }: { tier: Tier; state: StageState; first?: boolean }) {
  return (
    <>
      {!first && <Joint lit={state !== "waiting"} />}
      <Box label={tier.label} state={state} note={tier.note} free={tier.free} />
    </>
  );
}

function Box({
  label,
  state,
  note,
  free,
}: {
  label: string;
  state: StageState;
  note?: string;
  free?: boolean;
}) {
  return (
    <motion.div
      animate={{ opacity: state === "waiting" ? 0.35 : 1 }}
      className={`flex flex-col items-center border px-4 py-1.5 text-center ${
        state === "running"
          ? "border-augur-400 bg-augur-600/20"
          : state === "done"
            ? "border-edge bg-slate-panel"
            : "border-edge/60"
      }`}
    >
      <span className="flex items-center gap-2 font-mono text-[11px] tracking-widest text-chalk">
        {label}
        {free && (
          <span className="rounded-sm bg-augur-900/40 px-1 text-[9px] tracking-normal text-augur-200">
            $0
          </span>
        )}
        {state === "running" && (
          <motion.span
            className="h-1.5 w-1.5 rounded-full bg-augur-300"
            animate={{ opacity: [1, 0.2, 1] }}
            transition={{ duration: 1.4, repeat: Infinity }}
          />
        )}
      </span>
      {note && <span className="mt-0.5 font-mono text-[9px] text-mist">{note}</span>}
    </motion.div>
  );
}

function Joint({ lit }: { lit: boolean }) {
  return (
    <motion.div
      className="h-4 w-px"
      style={{ background: lit ? "var(--color-augur-500)" : "var(--color-edge)" }}
      initial={{ scaleY: 0 }}
      animate={{ scaleY: 1 }}

      transition={{ duration: 0.3 }}
    />
  );
}
