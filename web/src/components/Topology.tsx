import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

/** A system, re-reading itself.
 *
 * The nodes are the shapes this reviewer actually finds in a compose file: an
 * entrypoint, workers, a store, a broker, a cache. They rearrange because that
 * is the claim being made -- the same seven parts admit several architectures,
 * and understanding which one you have is the work that happens before any
 * judgement.
 *
 * Nothing here is data. It is the mark, not the product, and the product's real
 * topology appears the moment a repository is connected.
 */

interface Node {
  id: string;
  label: string;
  kind: "edge" | "compute" | "store";
}

const NODES: Node[] = [
  { id: "api", label: "API", kind: "edge" },
  { id: "svc", label: "Service", kind: "compute" },
  { id: "wrk", label: "Worker", kind: "compute" },
  { id: "db", label: "Postgres", kind: "store" },
  { id: "q", label: "Queue", kind: "store" },
  { id: "cache", label: "Cache", kind: "store" },
];

type Spot = Record<string, [number, number]>;

/** Four real shapes: layered, fan-out, event-driven, and a hub. */
const SHAPES: { spots: Spot; edges: [string, string][] }[] = [
  {
    spots: {
      api: [50, 12], svc: [50, 40], wrk: [50, 66],
      db: [22, 90], q: [50, 90], cache: [78, 90],
    },
    edges: [["api", "svc"], ["svc", "wrk"], ["wrk", "db"], ["wrk", "q"], ["svc", "cache"]],
  },
  {
    spots: {
      api: [50, 14], svc: [22, 48], wrk: [78, 48],
      db: [10, 86], q: [50, 86], cache: [90, 86],
    },
    edges: [["api", "svc"], ["api", "wrk"], ["svc", "db"], ["wrk", "q"], ["wrk", "cache"], ["svc", "q"]],
  },
  {
    spots: {
      api: [14, 26], q: [50, 26], wrk: [86, 26],
      svc: [14, 74], db: [50, 74], cache: [86, 74],
    },
    edges: [["api", "q"], ["q", "wrk"], ["wrk", "db"], ["api", "svc"], ["svc", "db"], ["wrk", "cache"]],
  },
  {
    spots: {
      svc: [50, 50], api: [50, 12], wrk: [88, 40],
      db: [76, 86], q: [24, 86], cache: [12, 40],
    },
    edges: [["api", "svc"], ["svc", "wrk"], ["svc", "db"], ["svc", "q"], ["svc", "cache"], ["wrk", "db"]],
  },
];

const HOLD = 3400;

export function Topology({ className = "" }: { className?: string }) {
  const still = useReducedMotion();
  const [shape, setShape] = useState(0);

  useEffect(() => {
    if (still) return;
    const tick = window.setInterval(() => setShape((n) => (n + 1) % SHAPES.length), HOLD);
    return () => window.clearInterval(tick);
  }, [still]);

  const { spots, edges } = SHAPES[shape];

  return (
    <div className={`relative aspect-[5/4] w-full ${className}`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
        {edges.map(([from, to]) => {
          const [x1, y1] = spots[from];
          const [x2, y2] = spots[to];
          return (
            <motion.line
              key={`${from}-${to}`}
              stroke="var(--color-augur-500)"
              strokeWidth="0.35"
              strokeOpacity={0.5}
              initial={false}
              animate={{ x1, y1, x2, y2 }}
              transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
            />
          );
        })}
      </svg>

      {NODES.map((node) => {
        const [x, y] = spots[node.id];
        return (
          <motion.div
            key={node.id}
            initial={false}
            animate={{ left: `${x}%`, top: `${y}%` }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
            className="absolute -translate-x-1/2 -translate-y-1/2"
          >
            <div
              className={`whitespace-nowrap border px-3 py-1.5 font-mono text-[11px] tracking-wide ${
                node.kind === "edge"
                  ? "border-augur-400/70 bg-augur-600/20 text-augur-100"
                  : node.kind === "compute"
                    ? "border-edge bg-slate-panel text-chalk"
                    : "border-edge bg-ink text-mist"
              }`}
            >
              {node.label}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
