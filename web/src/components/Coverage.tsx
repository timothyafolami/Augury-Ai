import { motion } from "framer-motion";
import type { EngineeringCoverage } from "../lib/types";

/** How much of each engineering concern this review actually exercised.
 *
 * A layer whose concern appears nowhere has no bar at all rather than a full
 * one, because "we looked at all zero of them" is not a reassuring fact and
 * must not render as complete. Every row states its basis: routed is measured,
 * signalled is an upper bound, and a bar without that word beside it reads as
 * a measurement nobody took.
 */
export function Coverage({ coverage }: { coverage: EngineeringCoverage }) {
  const rows = [...coverage.layers].sort(
    (a, b) => (b.share ?? -1) - (a.share ?? -1) || b.findings - a.findings,
  );

  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((row, index) => (
        <motion.div
          key={row.layer}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, delay: index * 0.04 }}
        >
          <div className="flex items-baseline gap-2">
            <span className="w-28 shrink-0 truncate font-mono text-[11px] text-chalk">
              {row.title}
            </span>

            <div className="relative h-2 flex-1 bg-ink">
              {row.share !== null && (
                <motion.div
                  className={`absolute inset-y-0 left-0 ${
                    row.basis === "routed" ? "bg-augur-500" : "bg-augur-600/50"
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.round(row.share * 100)}%` }}
                  transition={{ duration: 0.7, delay: index * 0.04, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
              {row.share === null && (
                <div className="absolute inset-0 border border-dashed border-edge" />
              )}
            </div>

            <span className="w-14 shrink-0 text-right font-mono text-[11px] tabular-nums text-mist">
              {row.share === null ? "n/a" : `${Math.round(row.share * 100)}%`}
            </span>
          </div>

          <div className="mt-0.5 flex items-baseline gap-2 pl-[7.5rem] font-mono text-[10px] text-mist/60">
            {row.share === null ? (
              <span>this concern appears in no module that was mapped</span>
            ) : (
              <span>
                {row.reviewed.length} of {row.occurrences.length} modules where it appears
                {row.findings > 0 && ` · ${row.findings} found`}
              </span>
            )}
            <span
              className={`ml-auto shrink-0 ${
                row.basis === "routed" ? "text-augur-300" : "text-mist/50"
              }`}
              title={
                row.basis === "routed"
                  ? "measured: the run recorded which specialists were asked about which module"
                  : "an upper bound: a module read counts for every layer its signals route to, and triage narrows further than this can see"
              }
            >
              {row.basis}
            </span>
          </div>
        </motion.div>
      ))}

      <p className="mt-2 border-t border-edge pt-2.5 font-mono text-[10px] leading-relaxed text-mist/60">
        A share is modules a specialist was asked about, over modules where its
        concern appears. It is not a grade, and a full bar means the review
        reached everywhere the concern was detected, not that the code is sound.
      </p>
    </div>
  );
}
