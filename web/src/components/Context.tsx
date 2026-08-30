import { motion, AnimatePresence } from "framer-motion";

/** What the review is carrying.
 *
 * Small and persistent rather than a panel of its own. Every number here is a
 * count of something that exists: modules mapped, findings held, cache hits the
 * Memo actually recorded. A percentage nobody measured would be the one
 * fabricated number on the screen.
 */
export function Context({
  entries,
  recent,
}: {
  entries: { label: string; value: string }[];
  recent: string[];
}) {
  return (
    <div className="border border-edge bg-ink/70 p-4">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.28em] text-mist">context</h3>

      <dl className="mt-3 flex flex-col gap-1.5">
        {entries.map((entry) => (
          <div key={entry.label} className="flex items-baseline justify-between gap-3">
            <dt className="font-mono text-[11px] text-mist">{entry.label}</dt>
            <dd className="font-mono text-[11px] tabular-nums text-chalk">{entry.value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-3 min-h-[3.2rem] border-t border-edge/60 pt-2.5">
        <AnimatePresence initial={false}>
          {recent.slice(-3).map((line, index) => (
            <motion.p
              key={`${line}-${index}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="truncate font-mono text-[10px] text-augur-300"
            >
              + {line}
            </motion.p>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
