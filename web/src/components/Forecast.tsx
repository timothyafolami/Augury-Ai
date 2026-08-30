import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Pressure } from "../lib/types";

/** What the review reached from several directions.
 *
 * There is no percentage here, and that is the design. A probability would
 * imply a measurement nobody took, so an item carries how many separate places
 * the review found the same mechanism, a band that is a position in a sequence
 * rather than a magnitude, and the sentence saying how it was worked out. The
 * evidence is one click away and the item cannot exist without it.
 */

const RUNGS = 3;

export function Forecast({ items }: { items: Pressure[] }) {
  if (items.length === 0) {
    return (
      <p className="py-6 text-center font-mono text-[11px] text-mist/50">
        Nothing was reached from enough directions to name a pressure. That is an
        absence of evidence, not a clean bill of health.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item, index) => (
        <Item key={item.mechanism} item={item} index={index} />
      ))}
      <p className="mt-2 border-t border-edge pt-2.5 font-mono text-[10px] leading-relaxed text-mist/60">
        Ordinal, deliberately. Systemic does not mean three times isolated, it
        means the review reached the same mechanism from enough separate places
        that it is a property of the service rather than of one file.
      </p>
    </div>
  );
}

function Item({ item, index }: { item: Pressure; index: number }) {
  const [open, setOpen] = useState(false);
  const rung = item.band === "systemic" ? 3 : item.band === "repeated" ? 2 : 1;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      className="border border-edge bg-ink/60"
    >
      <button
        onClick={() => setOpen((was) => !was)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-slate-panel/50"
      >
        <span className="flex shrink-0 gap-1" aria-hidden>
          {Array.from({ length: RUNGS }, (_, step) => (
            <span
              key={step}
              className={`h-4 w-1.5 ${step < rung ? tone(item.band) : "bg-edge"}`}
            />
          ))}
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[12px] text-chalk">
            {readable(item.mechanism)}
          </span>
          <span className="block truncate font-mono text-[10px] text-mist">
            {item.band} · reached from {item.independent_findings}{" "}
            {item.independent_findings === 1 ? "place" : "places"}
          </span>
        </span>

        <span className="shrink-0 font-mono text-[10px] text-mist/50">
          {open ? "hide" : "why"}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden border-t border-edge/60"
          >
            <div className="px-3 py-3">
              <p className="font-mono text-[10px] leading-relaxed text-augur-200">
                {item.derivation}
              </p>
              <p className="mt-2 text-[11px] leading-relaxed text-mist">{item.rule}</p>

              <ul className="mt-3 flex flex-col gap-1.5">
                {item.evidence.map((piece) => (
                  <li key={`${piece.path}:${piece.line}:${piece.symbol}`} className="flex gap-2">
                    <span className="shrink-0 font-mono text-[10px] text-augur-400">
                      {piece.layer}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-[10px] text-chalk">
                        {piece.symbol}{" "}
                        <span className="text-mist">
                          {piece.path}:{piece.line}
                        </span>
                      </span>
                      <span className="block truncate font-mono text-[10px] text-mist/60">
                        {piece.trigger}
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
  );
}

function tone(band: Pressure["band"]): string {
  if (band === "systemic") return "bg-verdict-miss";
  if (band === "repeated") return "bg-verdict-broken";
  return "bg-augur-500";
}

/** `connection_pool_exhaustion` is a key, not a sentence. */
function readable(mechanism: string): string {
  const words = mechanism.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
