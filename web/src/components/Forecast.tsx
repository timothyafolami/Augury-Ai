import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Pressure } from "../lib/types";

/** Where the review kept arriving, drawn.
 *
 * A list of sentences buried what this is: several separate findings, from
 * different specialists in different files, all pointing at one mechanism. So
 * it is a map. Each mechanism is a spine, each finding on it is a mark, and the
 * marks are coloured by which specialist reported them, because a mechanism
 * three specialists reached independently is a different fact from one that
 * three files of the same kind produced.
 *
 * There is no percentage anywhere, deliberately. A probability would imply a
 * measurement nobody took. What is drawn is how many separate places the review
 * arrived from, which is a count of evidence rather than a claim about the
 * future, and the sentence saying so travels with it.
 */

const LAYER_TONE: Record<string, string> = {
  concurrency: "bg-augur-400",
  network: "bg-sky-400",
  data: "bg-emerald-400",
  distributed: "bg-indigo-400",
  failure: "bg-verdict-miss",
  observability: "bg-amber-400",
  security: "bg-rose-400",
  craft: "bg-violet-400",
};

export function Forecast({ items }: { items: Pressure[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <p className="py-6 text-center font-mono text-[11px] leading-relaxed text-mist/50">
        Nothing was reached from enough directions to name a pressure. That is an
        absence of evidence, not a clean bill of health.
      </p>
    );
  }

  const widest = Math.max(...items.map((item) => item.independent_findings));
  const layers = [...new Set(items.flatMap((i) => i.evidence.map((e) => e.layer)))].sort();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        {items.map((item, index) => (
          <motion.div
            key={item.mechanism}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: index * 0.06 }}
          >
            <button
              onClick={() => setOpen(open === item.mechanism ? null : item.mechanism)}
              className="flex w-full items-center gap-3 text-left"
            >
              <span className="w-44 shrink-0 truncate font-mono text-[11px] text-chalk">
                {readable(item.mechanism)}
              </span>

              {/* The spine, and one mark per place the review arrived from. */}
              <span className="relative flex h-6 flex-1 items-center">
                <span className="absolute inset-x-0 h-px bg-edge" />
                <span className="relative flex items-center gap-1">
                  {item.evidence.map((piece, at) => (
                    <motion.span
                      key={`${piece.path}:${piece.line}`}
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ duration: 0.25, delay: index * 0.06 + at * 0.03 }}
                      title={`${piece.layer} · ${piece.symbol} · ${piece.path}:${piece.line}`}
                      className={`h-3 w-3 ${LAYER_TONE[piece.layer] ?? "bg-mist"}`}
                    />
                  ))}
                </span>
              </span>

              <span
                className={`w-24 shrink-0 text-right font-mono text-[10px] uppercase tracking-wider ${
                  item.band === "systemic"
                    ? "text-verdict-miss"
                    : item.band === "repeated"
                      ? "text-verdict-broken"
                      : "text-mist"
                }`}
                style={{ opacity: 0.5 + (item.independent_findings / widest) * 0.5 }}
              >
                {item.band}
              </span>
            </button>

            <AnimatePresence initial={false}>
              {open === item.mechanism && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="ml-44 mt-2 border-l border-edge pl-4">
                    <p className="font-mono text-[10px] leading-relaxed text-augur-200">
                      {item.derivation}
                    </p>
                    <p className="mt-2 text-[11px] leading-relaxed text-mist">{item.rule}</p>
                    <ul className="mt-2 flex flex-col gap-1">
                      {item.evidence.map((piece) => (
                        <li
                          key={`${piece.path}:${piece.line}:${piece.symbol}`}
                          className="flex items-baseline gap-2 font-mono text-[10px]"
                        >
                          <span
                            className={`h-2 w-2 shrink-0 ${LAYER_TONE[piece.layer] ?? "bg-mist"}`}
                          />
                          <span className="w-20 shrink-0 truncate text-mist">{piece.layer}</span>
                          <span className="min-w-0 flex-1 truncate text-chalk">
                            {piece.symbol}{" "}
                            <span className="text-mist">
                              {piece.path}:{piece.line}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-edge pt-3">
        {layers.map((layer) => (
          <span key={layer} className="flex items-center gap-1.5 font-mono text-[10px] text-mist">
            <span className={`h-2 w-2 ${LAYER_TONE[layer] ?? "bg-mist"}`} />
            {layer}
          </span>
        ))}
      </div>

      <p className="font-mono text-[10px] leading-relaxed text-mist/60">
        One mark per separate place the review arrived at the same mechanism. There
        is no probability here: systemic does not mean three times isolated, it
        means the review reached it from enough directions that it is a property of
        the service rather than of one file.
      </p>
    </div>
  );
}

function readable(mechanism: string): string {
  const words = mechanism.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
