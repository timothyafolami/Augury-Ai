import { motion } from "framer-motion";
import type { Discovery, Report } from "../lib/types";

/** What the review did not look at.
 *
 * On a large repository this is most of it, and stating it is the product's
 * central claim rather than a footnote. Three separate populations, which are
 * routinely confused: files that never entered the map, modules the map holds
 * that no request reaches, and modules the scheduler declined to spend on.
 */
export function NotRead({
  discovery,
  report,
}: {
  discovery: Discovery;
  report: Report | null;
}) {
  const skipped = report?.coverage?.skipped ?? {};
  const reasons = new Map<string, number>();
  for (const why of Object.values(skipped)) {
    reasons.set(why, (reasons.get(why) ?? 0) + 1);
  }

  const read = report?.coverage?.analysed.length ?? 0;
  const mapped = discovery.modules.length;

  return (
    <div className="flex flex-col gap-3">
      <Line
        label="read by a specialist"
        count={read}
        total={mapped}
        tone="bg-augur-500"
        note="a model was asked about these"
      />
      <Line
        label="mapped, not read"
        count={Math.max(mapped - read, 0)}
        total={mapped}
        tone="bg-augur-900"
        note="the scheduler ranked them below what was left in the budget"
      />
      <Line
        label="no request reaches"
        count={discovery.unreachable.length}
        total={mapped}
        tone="bg-edge"
        note="migrations, scripts and entry points nothing imports"
      />

      {reasons.size > 0 && (
        <div className="mt-1 border-t border-edge pt-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-mist">
            why each was skipped
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {[...reasons.entries()]
              .sort((a, b) => b[1] - a[1])
              .slice(0, 6)
              .map(([why, count]) => (
                <li key={why} className="flex items-baseline gap-3 font-mono text-[10px]">
                  <span className="w-10 shrink-0 text-right tabular-nums text-chalk">{count}</span>
                  <span className="min-w-0 flex-1 truncate text-mist">{why}</span>
                </li>
              ))}
          </ul>
        </div>
      )}

      <p className="mt-1 border-t border-edge pt-2.5 font-mono text-[10px] leading-relaxed text-mist/60">
        Vendored trees, lockfile-installed dependencies and build output never
        enter the map at all. A .env is never read: it holds live credentials
        for the service under review, and .env.example is read instead.
      </p>
    </div>
  );
}

function Line({
  label,
  count,
  total,
  tone,
  note,
}: {
  label: string;
  count: number;
  total: number;
  tone: string;
  note: string;
}) {
  const share = total > 0 ? count / total : 0;
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="w-36 shrink-0 truncate font-mono text-[11px] text-chalk">{label}</span>
        <div className="relative h-2 flex-1 bg-ink">
          <motion.div
            className={`absolute inset-y-0 left-0 ${tone}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.round(share * 100)}%` }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
        <span className="w-16 shrink-0 text-right font-mono text-[11px] tabular-nums text-mist">
          {count}
        </span>
      </div>
      <p className="mt-0.5 pl-[9.5rem] font-mono text-[10px] text-mist/60">{note}</p>
    </div>
  );
}
