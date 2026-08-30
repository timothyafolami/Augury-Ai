import { motion } from "framer-motion";
import type { Pressure } from "../lib/types";

/** Where separate findings meet, drawn as the convergence it is.
 *
 * A pressure is not one finding. It is several, reported by different
 * specialists reading different files, that turn out to name the same
 * mechanism. That claim was being rendered as a row of dots on a line, which
 * shows the count and hides the thing worth seeing: which files, from which
 * concerns, arrive at the same place.
 *
 * So the left edge is the evidence, one entry per finding, coloured by the
 * specialist that reported it. The right edge is the mechanism. The lines
 * between them are the convergence, and a mechanism three colours arrive at is
 * visibly different from one that three files of the same kind produced.
 *
 * No probability anywhere, for the reason the panel has always given: a
 * percentage would imply a measurement nobody took. Thickness and emphasis
 * encode how many independent places the review arrived from, which is a count
 * of evidence rather than a claim about the future.
 */

const TONE: Record<string, string> = {
  concurrency: "#a78bfa",
  network: "#38bdf8",
  data: "#34d399",
  distributed: "#818cf8",
  failure: "#fb7185",
  observability: "#fbbf24",
  security: "#f472b6",
  craft: "#c084fc",
  serving: "#2dd4bf",
};

const ROW = 26;
const TOP = 18;
const LEFT_EDGE = 250;
const RIGHT_EDGE = 470;
const WIDTH = 760;
// The symbol ends here and the layer starts after it, so the two never share
// a pixel with each other or with the dot on the spine.
const SYMBOL_END = LEFT_EDGE - 78;
const LAYER_START = LEFT_EDGE - 72;
// Two mechanisms closer than this render one label on top of the other, which
// is what "secret exposure" and "undiagnosable failure" did: both isolated,
// both one finding, both landing on adjacent rows.
const CLEARANCE = 34;

interface Placed {
  mechanism: string;
  band: string;
  independent: number;
  y: number;
  evidence: { key: string; label: string; where: string; layer: string; y: number }[];
}

export function Convergence({
  items,
  onPick,
  picked,
}: {
  items: Pressure[];
  onPick: (mechanism: string) => void;
  picked: string | null;
}) {
  // Laid out top to bottom in one pass: every finding gets a row, and each
  // mechanism sits at the middle of the rows that feed it, so the lines fan
  // rather than cross.
  let row = 0;
  const placed: Placed[] = items.map((item) => {
    const evidence = item.evidence.map((piece) => ({
      key: `${piece.path}:${piece.line}:${piece.symbol}`,
      label: piece.symbol || piece.path.split("/").pop() || "finding",
      where: `${piece.path.split("/").slice(-2).join("/")}:${piece.line}`,
      layer: piece.layer,
      y: TOP + row++ * ROW,
    }));
    const first = evidence[0]?.y ?? TOP;
    const last = evidence[evidence.length - 1]?.y ?? first;
    return {
      mechanism: item.mechanism,
      band: item.band,
      independent: item.independent_findings,
      y: (first + last) / 2,
      evidence,
    };
  });

  // Pushed apart where they would collide. The line still meets the node, so
  // moving the node moves the curve with it and nothing is misattributed.
  for (let index = 1; index < placed.length; index++) {
    const above = placed[index - 1];
    const here = placed[index];
    if (here.y - above.y < CLEARANCE) here.y = above.y + CLEARANCE;
  }

  const lowest = placed.length ? placed[placed.length - 1].y : TOP;
  const height = Math.max(TOP + row * ROW, lowest + ROW) + 12;

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="w-full"
      style={{ maxHeight: `${height}px` }}
      role="img"
      aria-label="which findings converge on which mechanism"
    >
      {placed.map((group, groupIndex) =>
        group.evidence.map((piece, index) => {
          const midpoint = (LEFT_EDGE + RIGHT_EDGE) / 2;
          return (
            <motion.path
              key={`${group.mechanism}-${piece.key}`}
              d={`M ${LEFT_EDGE} ${piece.y} C ${midpoint} ${piece.y}, ${midpoint} ${group.y}, ${RIGHT_EDGE} ${group.y}`}
              fill="none"
              stroke={TONE[piece.layer] ?? "#8e89a3"}
              strokeWidth={picked === group.mechanism ? 1.6 : 1}
              strokeOpacity={picked && picked !== group.mechanism ? 0.12 : 0.5}
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.5, delay: groupIndex * 0.08 + index * 0.04 }}
            />
          );
        }),
      )}

      {placed.map((group) =>
        group.evidence.map((piece) => (
          <g key={piece.key} opacity={picked && picked !== group.mechanism ? 0.3 : 1}>
            <text
              x={SYMBOL_END}
              y={piece.y + 3}
              textAnchor="end"
              className="font-mono"
              fontSize="10"
              fill="#e8e6f0"
            >
              {piece.label.length > 20 ? `${piece.label.slice(0, 19)}…` : piece.label}
            </text>
            <text
              x={LAYER_START}
              y={piece.y + 3}
              className="font-mono"
              fontSize="8"
              fill="#8e89a3"
            >
              {piece.layer}
            </text>
            <circle cx={LEFT_EDGE} cy={piece.y} r={3} fill={TONE[piece.layer] ?? "#8e89a3"} />
            <title>{`${piece.layer} · ${piece.where}`}</title>
          </g>
        )),
      )}

      {placed.map((group) => (
        <g
          key={group.mechanism}
          onClick={() => onPick(group.mechanism)}
          className="cursor-pointer"
          opacity={picked && picked !== group.mechanism ? 0.4 : 1}
        >
          <circle
            cx={RIGHT_EDGE}
            cy={group.y}
            r={4 + Math.min(group.independent, 5)}
            fill="none"
            stroke={group.band === "systemic" ? "#fb7185" : "#8b5cf6"}
            strokeWidth={1.4}
          />
          <circle cx={RIGHT_EDGE} cy={group.y} r={2.5} fill="#8b5cf6" />
          <text
            x={RIGHT_EDGE + 16}
            y={group.y - 1}
            className="font-mono"
            fontSize="11"
            fill="#e8e6f0"
          >
            {readable(group.mechanism)}
          </text>
          <text
            x={RIGHT_EDGE + 16}
            y={group.y + 11}
            className="font-mono"
            fontSize="8.5"
            fill={group.band === "systemic" ? "#fb7185" : "#8e89a3"}
          >
            {group.band} · {group.independent} independent
          </text>
        </g>
      ))}
    </svg>
  );
}

function readable(mechanism: string): string {
  return mechanism.replace(/[_-]/g, " ");
}
