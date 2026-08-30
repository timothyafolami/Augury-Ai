import { motion } from "framer-motion";
import type { Observation } from "../lib/types";

/** What no single specialist could have said.
 *
 * Eight specialists each read for one concern and none sees the others, which
 * is deliberate: in a group chat one wrong claim anchors the next. The cost is
 * that nobody looks at the whole board, and the most senior thing to say about
 * a service usually needs two specialists to see it.
 *
 * Every observation shows the findings it was built from, from at least two
 * different specialists. That is enforced where the observation is made, not
 * here, so a citation list this component renders can never be decorative.
 */
export function Synthesis({ observations }: { observations: Observation[] }) {
  if (observations.length === 0) {
    return (
      <p className="py-6 text-center font-mono text-[11px] leading-relaxed text-mist/50">
        No two findings connected into something neither specialist could say alone.
        That is the correct answer for this report, not a gap in it.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {observations.map((item, index) => (
        <motion.article
          key={item.mechanism}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: index * 0.06 }}
          className="border-l-2 border-augur-500 bg-ink/70 p-4"
        >
          <h3 className="text-[13px] font-medium leading-snug text-chalk">{item.mechanism}</h3>
          <p className="mt-2 text-[13px] leading-relaxed text-mist">{item.consequence}</p>

          <div className="mt-3 border-t border-edge/60 pt-2.5">
            <p className="font-mono text-[10px] uppercase tracking-widest text-mist/60">
              built from {item.citations.length} findings across{" "}
              {new Set(item.citations.map((c) => c.layer)).size} specialists
            </p>
            <ul className="mt-1.5 flex flex-col gap-1">
              {item.citations.map((cite) => (
                <li
                  key={`${cite.path}:${cite.line}:${cite.symbol}`}
                  className="flex gap-2 font-mono text-[10px]"
                >
                  <span className="w-20 shrink-0 truncate text-augur-400">{cite.layer}</span>
                  <span className="min-w-0 flex-1 truncate text-chalk">
                    {cite.symbol}{" "}
                    <span className="text-mist">
                      {cite.path}:{cite.line}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </motion.article>
      ))}
    </div>
  );
}
