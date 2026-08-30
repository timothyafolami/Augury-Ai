import { motion, AnimatePresence } from "framer-motion";
import type { Finding } from "../lib/types";

/** What the review found.
 *
 * The predicted number and the measured number sit next to each other,
 * deliberately plain. Styling a refutation would make it read as theatre, and
 * a refutation is the most valuable line here.
 */
export function Findings({ findings }: { findings: Finding[] }) {
  return (
    <div className="flex flex-col gap-2">
      <AnimatePresence initial={false}>
        {findings.map((finding, index) => (
          <motion.article
            key={`${finding.path}:${finding.line}:${finding.symbol}:${index}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="rounded-xl bg-slate-panel p-4 hairline"
          >
            <header className="flex flex-wrap items-baseline gap-2">
              <Severity level={finding.severity} />
              <span className="font-mono text-sm text-chalk">
                {finding.symbol || finding.rule}
              </span>
              <span className="font-mono text-xs text-mist">
                {finding.path}
                {finding.line ? `:${finding.line}` : ""}
              </span>
              {finding.layer && (
                <span className="ml-auto rounded-full bg-augur-900/40 px-2 py-0.5 text-[10px] text-augur-200">
                  {finding.layer}
                </span>
              )}
            </header>

            <p className="mt-2 text-sm leading-relaxed text-mist">{finding.mechanism}</p>

            {finding.prediction && (
              <div className="mt-3 rounded-lg bg-void/60 p-3 font-mono text-xs">
                <div className="text-mist">
                  <span className="text-augur-300">predicted</span>{" "}
                  {finding.prediction.metric} {finding.prediction.comparator}{" "}
                  {finding.prediction.value}
                  {finding.prediction.upper !== null && ` and ${finding.prediction.upper}`}
                  {finding.prediction.unit} — {finding.prediction.condition}
                </div>
                {finding.measurement && (
                  <div className="mt-1 text-chalk">
                    <span className="text-augur-300">measured</span>{" "}
                    {finding.measurement.value ?? "nothing"} — {finding.measurement.detail}
                  </div>
                )}
              </div>
            )}

            {finding.remediation && (
              <p className="mt-3 text-sm text-chalk/80">
                <span className="text-augur-300">Fix.</span> {finding.remediation}
              </p>
            )}
          </motion.article>
        ))}
      </AnimatePresence>
    </div>
  );
}

function Severity({ level }: { level: Finding["severity"] }) {
  const tone =
    level === "high"
      ? "bg-verdict-miss/15 text-verdict-miss"
      : level === "medium"
        ? "bg-verdict-broken/15 text-verdict-broken"
        : "bg-mist/10 text-mist";
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${tone}`}>
      {level}
    </span>
  );
}
