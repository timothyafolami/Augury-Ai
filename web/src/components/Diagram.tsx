import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import type { Architecture, ArchNode } from "../lib/types";

/** The service, with its narrow places showing.
 *
 * Laid out in columns by distance from an entrypoint, because that is the only
 * ordering the map actually knows. A node is sized by how much code it holds
 * and coloured by what was found inside it, and a declared capacity ceiling is
 * printed on the node itself: it appears in the deployment and in no source
 * file, which is the whole reason the survey runs before the code is read.
 */

const COLUMN = 210;
const ROW = 66;

export function Diagram({ architecture }: { architecture: Architecture }) {
  const [hovered, setHovered] = useState<string | null>(null);

  const { placed, width, height } = useMemo(() => {
    const columns = new Map<number, ArchNode[]>();
    for (const node of architecture.nodes) {
      const at = node.kind === "service" ? 0 : node.kind === "store" ? 3 : Math.min(node.depth ?? 2, 2) || 1;
      const column = columns.get(at) ?? [];
      column.push(node);
      columns.set(at, column);
    }

    const spots = new Map<string, { x: number; y: number }>();
    let tallest = 0;
    for (const [at, held] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
      held.forEach((node, index) => {
        spots.set(node.id, { x: at * COLUMN + 12, y: index * ROW + 16 });
      });
      tallest = Math.max(tallest, held.length);
    }

    return {
      placed: spots,
      width: (Math.max(...columns.keys(), 0) + 1) * COLUMN + 24,
      height: tallest * ROW + 32,
    };
  }, [architecture.nodes]);

  const worst = Math.max(1, ...architecture.nodes.map((node) => node.findings));

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height} className="min-w-full">
        {architecture.edges.map((edge, index) => {
          const from = placed.get(edge.source);
          const to = placed.get(edge.target);
          if (!from || !to) return null;
          const lit = hovered === edge.source || hovered === edge.target;
          return (
            <motion.path
              key={`${edge.source}-${edge.target}-${index}`}
              d={`M ${from.x + 150} ${from.y + 20} C ${from.x + 190} ${from.y + 20}, ${to.x - 40} ${to.y + 20}, ${to.x} ${to.y + 20}`}
              fill="none"
              stroke={lit ? "var(--color-augur-400)" : "var(--color-edge)"}
              strokeWidth={lit ? 1.4 : 1}
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.7, delay: 0.1 + index * 0.02 }}
            />
          );
        })}

        {architecture.nodes.map((node, index) => {
          const at = placed.get(node.id);
          if (!at) return null;
          const heat = node.findings / worst;
          return (
            <motion.g
              key={node.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.03 }}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: "default" }}
            >
              <rect
                x={at.x}
                y={at.y}
                width={150}
                height={40}
                fill={node.findings > 0 ? `rgba(139, 92, 246, ${0.1 + heat * 0.3})` : "var(--color-ink)"}
                stroke={
                  node.ceiling
                    ? "var(--color-verdict-broken)"
                    : node.findings > 0
                      ? "var(--color-augur-400)"
                      : "var(--color-edge)"
                }
                strokeWidth={node.ceiling ? 1.4 : 1}
              />
              <text
                x={at.x + 10}
                y={at.y + 17}
                className="fill-chalk font-mono"
                style={{ fontSize: 11 }}
              >
                {node.label.length > 19 ? `${node.label.slice(0, 18)}…` : node.label}
              </text>
              <text
                x={at.x + 10}
                y={at.y + 31}
                className="fill-mist font-mono"
                style={{ fontSize: 9 }}
              >
                {node.ceiling
                  ? node.ceiling
                  : node.kind === "code"
                    ? `${node.modules} modules${node.findings ? ` · ${node.findings} found` : ""}`
                    : node.detail}
              </text>
            </motion.g>
          );
        })}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-edge pt-2.5 font-mono text-[10px] text-mist/70">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 border border-verdict-broken" /> declared capacity ceiling
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 border border-augur-400 bg-augur-600/30" /> findings inside
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 border border-edge" /> read, nothing found
        </span>
      </div>

      <p className="mt-2 font-mono text-[10px] leading-relaxed text-mist/60">{architecture.basis}</p>
    </div>
  );
}
