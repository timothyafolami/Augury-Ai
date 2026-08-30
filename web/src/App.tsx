import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Landing } from "./components/Landing";
import { Connect } from "./components/Connect";
import { AgentGraph } from "./components/AgentGraph";
import { CodeTree } from "./components/CodeTree";
import { Telemetry } from "./components/Telemetry";
import { Context } from "./components/Context";
import { Findings } from "./components/Findings";
import { Coverage } from "./components/Coverage";
import { Forecast } from "./components/Forecast";
import { NotRead } from "./components/NotRead";
import { Diagram } from "./components/Diagram";
import { Synthesis } from "./components/Synthesis";
import { Document } from "./components/Document";
import { Waterfall } from "./components/Waterfall";
import { useRun } from "./lib/useRun";

type Screen = "landing" | "connect" | "workspace";

/** The eight concerns, from core/layers.py. Named here so the orchestration
 *  cannot draw a stage of the pipeline as though it were a specialist. */
const SPECIALISTS = [
  "concurrency",
  "network",
  "data",
  "distributed",
  "failure",
  "observability",
  "security",
  "craft",
];

/** Landing, connect, workspace.
 *
 * The failure state is designed rather than left over. A provider refusing a
 * request is the likeliest thing to happen during a demonstration, and an
 * interface with no vocabulary for it freezes on stage.
 */
export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const { discovery, mode, run, report, busy, loadStages, discover, review } = useRun();
  // Empty, meaning the whole repository. It defaulted to "backend", which is
  // not a directory in most repositories, so the first thing a new user saw
  // after choosing a folder was a server error caused by a field they had
  // never touched. The placeholder still suggests it.
  const [scope, setScope] = useState("");
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [now, setNow] = useState(0);
  const [startedAt, setStartedAt] = useState(0);

  useEffect(() => {
    void loadStages();
  }, [loadStages]);

  useEffect(() => {
    if (!reviewing) return;
    const tick = window.setInterval(() => setNow(Date.now() - startedAt), 100);
    return () => window.clearInterval(tick);
  }, [reviewing, startedAt]);

  useEffect(() => {
    if (report || run.failed) setReviewing(false);
  }, [report, run.failed]);

  const connect = useCallback(
    async (path: string, chosen: string, budget: number) => {
      setError("");
      setScope(chosen);
      try {
        await discover(path, chosen);
        setScreen("workspace");
        setReviewing(true);
        setStartedAt(Date.now());
        setNow(0);
        await review(path, chosen, budget);
      } catch (caught) {
        setReviewing(false);
        setError(String(caught instanceof Error ? caught.message : caught));
      }
    },
    [discover, review],
  );

  // The eight specialists, and only those. The stages of the pipeline are not
  // specialists, and a chip reading CARTOGRAPHER under SPECIALISTS says the
  // diagram does not know what it is drawing.
  const { active, counts } = useMemo(() => {
    const seen: string[] = [];
    const found: Record<string, number> = {};
    for (const step of run.steps) {
      const named =
        step.event?.startsWith("agent.") && typeof step.data?.layer === "string"
          ? step.data.layer
          : step.agent?.startsWith("analyst:")
            ? step.agent.split(":")[1]
            : "";
      if (!named || !SPECIALISTS.includes(named)) continue;
      const name = named.toUpperCase();
      if (!seen.includes(name)) seen.push(name);
      if (step.event === "agent.finished" && typeof step.data?.findings === "number") {
        found[name] = (found[name] ?? 0) + step.data.findings;
      }
    }
    return { active: seen, counts: found };
  }, [run.steps]);

  const context = useMemo(() => {
    const entries = [
      { label: "modules mapped", value: String(discovery?.modules.length ?? 0) },
      { label: "modules read", value: `${run.read}/${run.total || discovery?.modules.length || 0}` },
      { label: "findings held", value: String(findingCount(report, run.findings)) },
      { label: "spent", value: `$${run.usd.toFixed(4)}` },
      // Alongside the cost, because a total with no denominator is unreadable:
      // $0.0000 over 31 calls is a replay, $0.0000 over 0 calls is a stall.
      { label: "model calls", value: String(run.calls) },
    ];
    for (const [who, spent] of Object.entries(run.byModel)) {
      entries.push({ label: `spent · ${who}`, value: `$${spent.toFixed(4)}` });
    }
    // Whatever the run itself counted. Reported rather than derived, so a
    // cache hit on screen is a cache hit the engine recorded.
    for (const [what, count] of Object.entries(run.context)) {
      entries.push({ label: what, value: String(count) });
    }
    return entries;
  }, [discovery, run, report]);

  // The last few things the run learned, so the panel moves while it works.
  const recent = useMemo(
    () =>
      run.steps
        .filter((step) => step.event === "finding.detected" || step.event === "research.finished")
        .map((step) => {
          const data = step.data ?? {};
          if (step.event === "research.finished") {
            return `${data.found ? "found" : "nothing on"} ${String(data.subject ?? "")}`;
          }
          const found = (data.finding ?? {}) as { symbol?: string; path?: string };
          return `${found.symbol ?? "finding"} in ${found.path?.split("/").pop() ?? ""}`;
        })
        .slice(-6),
    [run.steps],
  );

  if (screen === "landing") return <Landing onStart={() => setScreen("connect")} />;
  if (screen === "connect")
    return <Connect onConnect={connect} busy={busy} error={error} mode={mode} />;

  // While the run works, what has arrived. Once it finishes, the report,
  // which is authoritative because the deterministic passes withdraw claims
  // the specialists made and the live stream cannot know that yet.
  const findings = report
    ? [...(report.deployment ?? []), ...report.schema, ...report.dependencies, ...report.findings]
    : run.findings;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center gap-4 border-b border-edge px-6 py-3">
        <button
          onClick={() => setScreen("landing")}
          className="font-mono text-sm tracking-widest text-augur-400"
        >
          AUGURY
        </button>
        <span className="font-mono text-xs text-mist">
          {discovery?.name}
          {scope && <span className="text-mist/50"> / {scope}</span>}
        </span>
        <span className="ml-auto flex items-center gap-4 font-mono text-[11px] text-mist">
          {run.model && <span className="text-augur-300">{run.model}</span>}
          <span>{(now / 1000).toFixed(0)}s</span>
          <span className="text-chalk">
            ${run.usd.toFixed(4)}
            {run.calls > 0 && <span className="text-mist"> / {run.calls} calls</span>}
          </span>
          {reviewing && <span className="text-augur-300">running</span>}
          {report && <span className="text-verdict-hit">complete</span>}
        </span>
      </header>

      <AnimatePresence>
        {(error || run.failed) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="shrink-0 border-b border-verdict-miss/30 bg-verdict-miss/10 px-6 py-2.5 font-mono text-xs text-verdict-miss"
          >
            {error || run.failed}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-edge lg:grid-cols-[19rem_minmax(0,1fr)_21rem]">
        <aside className="flex min-h-0 flex-col gap-3 overflow-hidden bg-void p-4">
          <Header>topology</Header>
          {discovery ? (
            <CodeTree modules={discovery.modules} files={run.files} />
          ) : (
            <Blank>nothing mapped</Blank>
          )}
        </aside>

        <section className="flex min-h-0 flex-col overflow-y-auto bg-void">
          <div className="border-b border-edge p-5">
            <Header>orchestration</Header>
            <div className="mt-3">
              <AgentGraph stages={run.stages} active={active} counts={counts} />
            </div>
          </div>

          <div className="border-b border-edge p-5">
            <Header>handoffs · real elapsed time</Header>
            <div className="mt-3">
              <Waterfall spans={run.spans} now={now} />
            </div>
          </div>

          {report?.architecture && report.architecture.nodes.length > 0 && (
            <div className="border-b border-edge p-5">
              <Header>
                architecture
                <span className="ml-2 text-mist/60">
                  drawn from the deployment and the map, with the narrow places marked
                </span>
              </Header>
              <div className="mt-4">
                <Diagram architecture={report.architecture} />
              </div>
            </div>
          )}

          {discovery && (report || reviewing) && (
            <div className="border-b border-edge p-5">
              <Header>
                what this review did not look at
                <span className="ml-2 text-mist/60">stated, not implied</span>
              </Header>
              <div className="mt-4">
                <NotRead discovery={discovery} report={report} />
              </div>
            </div>
          )}

          {report?.document && (
            <div className="border-b border-edge p-5">
              <Header>
                the review, as a document
                <span className="ml-2 text-mist/60">one engine, three clients</span>
              </Header>
              <div className="mt-4">
                <Document markdown={report.document} />
              </div>
            </div>
          )}

          {report && (
            <div className="border-b border-edge p-5">
              <Header>
                what no single specialist could say
                <span className="ml-2 text-mist/60">
                  each built from findings by two or more of them
                </span>
              </Header>
              <div className="mt-4">
                <Synthesis observations={report.synthesis ?? []} />
              </div>
            </div>
          )}

          {report?.engineering && (
            <div className="border-b border-edge p-5">
              <Header>
                engineering coverage
                <span className="ml-2 text-mist/60">
                  {report.engineering.modules} modules mapped
                </span>
              </Header>
              <div className="mt-4">
                <Coverage coverage={report.engineering} />
              </div>
            </div>
          )}

          {report?.forecast && (
            <div className="border-b border-edge p-5">
              <Header>
                risk forecast
                <span className="ml-2 text-mist/60">derived from findings, not measured</span>
              </Header>
              <div className="mt-4">
                <Forecast items={report.forecast} />
              </div>
            </div>
          )}

          <div className="p-5">
            <Header>
              findings
              <span className="ml-2 text-mist/60">
                {findings.length}
                {report ? ` · ${report.seconds}s` : reviewing ? " · arriving" : ""}
              </span>
            </Header>
            <div className="mt-3">
              {findings.length > 0 ? (
                <Findings findings={findings} />
              ) : (
                <Blank>
                  {reviewing
                    ? "deployment, schema and dependencies run first, and cost nothing"
                    : "none yet"}
                </Blank>
              )}
            </div>
          </div>
        </section>

        <aside className="flex min-h-0 flex-col gap-3 overflow-hidden bg-void p-4">
          <Context entries={context} recent={recent} />
          <Header>telemetry</Header>
          <div className="min-h-0 flex-1">
            <Telemetry steps={run.steps} />
          </div>
        </aside>
      </main>
    </div>
  );
}

function Header({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-mono text-[10px] uppercase tracking-[0.28em] text-mist">{children}</h2>
  );
}

function Blank({ children }: { children: React.ReactNode }) {
  return <p className="py-8 text-center font-mono text-[11px] text-mist/45">{children}</p>;
}

/** What the panel should say is held: the report once it exists, and what has
 *  arrived while it does not. */
function findingCount(report: { findings: unknown[] } | null, live: unknown[]): number {
  return report ? report.findings.length : live.length;
}
