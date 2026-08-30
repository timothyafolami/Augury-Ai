/** Agent handoffs, drawn on real elapsed time.
 *
 * Each bar's width is how long that agent actually took, from the timestamps
 * on its own steps. A percentage bar can be faked by a `setInterval`; this
 * cannot, which is the reason for choosing it.
 */
/** "analyst:security" is the specialist; "triage:a/b/c.py" is where it looked. */
function shorten(agent: string): string {
  const [head, ...rest] = agent.split(":");
  if (head === "analyst") return rest.join(":") || head;
  return head;
}

export function Waterfall({
  spans,
  now,
}: {
  spans: { agent: string; startedAt: number; endedAt: number | null }[];
  now: number;
}) {
  if (spans.length === 0) {
    return <p className="py-6 text-center text-xs text-mist">No agent has run yet.</p>;
  }
  const span = Math.max(now, ...spans.map((s) => s.endedAt ?? now), 1);

  return (
    <div className="flex flex-col gap-1.5">
      {spans.slice(-14).map((entry, index) => {
        const end = entry.endedAt ?? now;
        const left = (entry.startedAt / span) * 100;
        const width = Math.max(((end - entry.startedAt) / span) * 100, 0.8);
        return (
          <div key={`${entry.agent}-${entry.startedAt}-${index}`} className="flex items-center gap-3">
            <span
              className="w-28 shrink-0 truncate font-mono text-[11px] text-mist"
              title={entry.agent}
            >
              {shorten(entry.agent)}
            </span>
            <div className="relative h-2.5 flex-1 rounded-full bg-ink">
              <div
                className={`absolute h-2.5 rounded-full ${
                  entry.endedAt === null ? "bg-augur-500 animate-pulse" : "bg-augur-600/70"
                }`}
                style={{ left: `${left}%`, width: `${width}%` }}
              />
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-[11px] text-mist">
              {((end - entry.startedAt) / 1000).toFixed(1)}s
            </span>
          </div>
        );
      })}
    </div>
  );
}
