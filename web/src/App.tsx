import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Landing } from "./components/Landing";
import { Connect } from "./components/Connect";
import { AgentGraph } from "./components/AgentGraph";
import { CodeTree } from "./components/CodeTree";
import { Telemetry } from "./components/Telemetry";
import { Context } from "./components/Context";
import { Findings } from "./components/Findings";
import { Waterfall } from "./components/Waterfall";
import { useRun } from "./lib/useRun";

type Screen = "landing" | "connect" | "workspace";

/** Landing, connect, workspace.
 *
 * The failure state is designed rather than left over. A provider refusing a
 * request is the likeliest thing to happen during a demonstration, and an
 * interface with no vocabulary for it freezes on stage.
 */
export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const { discovery, run, report, busy, loadStages, discover, review } = useRun();
  const [scope, setScope] = useState("backend");
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
    async (path: string, chosen: string) => {
      setError("");
      setScope(chosen);
      try {
        await discover(path, chosen);
        setScreen("workspace");
        setReviewing(true);
        setStartedAt(Date.now());
        setNow(0);
        await review(path, chosen, 0.15);
      } catch (caught) {
        setReviewing(false);
        setError(String(caught instanceof Error ? caught.message : caught));
      }
    },
    [discover, review],
  );

  // Which specialists have actually been routed to, from the trajectory.
  const { active, counts } = useMemo(() => {
    const seen: string[] = [];
    const found: Record<string, number> = {};
    for (const step of run.steps) {
      const agent = step.agent;
      if (!agent || agent === "triage" || agent === "scheduler") continue;
      // A trajectory records "analyst:security" and "triage:<path>". The
      // specialist is the name; the path is where it was pointed.
      const name = agent.split(":")[0] === "analyst"
        ? (agent.split(":")[1] ?? "analyst").toUpperCase()
        : agent.split(":")[0].toUpperCase();
      if (!seen.includes(name)) seen.push(name);
      if (step.action === "found") found[name] = (found[name] ?? 0) + 1;
    }
    return { active: seen.slice(0, 8), counts: found };
  }, [run.steps]);

  const context = useMemo(
    () => [
      { label: "modules mapped", value: String(discovery?.modules.length ?? 0) },
      { label: "modules read", value: `${run.read}/${run.total || discovery?.modules.length || 0}` },
      { label: "findings held", value: String(report?.findings.length ?? countFindings(run.steps)) },
      { label: "spent", value: `$${run.usd.toFixed(4)}` },
    ],
    [discovery, run, report],
  );

  const recent = useMemo(
    () =>
      run.steps
        .filter((step) => step.kind === "module" && (step.findings ?? 0) > 0)
        .map((step) => `${step.findings} in ${step.path?.split("/").pop()}`)
        .slice(-6),
    [run.steps],
  );

  if (screen === "landing") return <Landing onStart={() => setScreen("connect")} />;
  if (screen === "connect")
    return <Connect onConnect={connect} busy={busy} error={error} />;

  const findings = report ? [...report.schema, ...report.dependencies, ...report.findings] : [];

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
          <span className="text-chalk">${run.usd.toFixed(4)}</span>
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

          <div className="p-5">
            <Header>
              findings
              {report && (
                <span className="ml-2 text-mist/60">
                  {findings.length} · {report.seconds}s
                </span>
              )}
            </Header>
            <div className="mt-3">
              {findings.length > 0 ? (
                <Findings findings={findings} />
              ) : (
                <Blank>
                  {reviewing
                    ? "deterministic passes run first: schema and dependencies cost nothing"
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

function countFindings(steps: { kind?: string; findings?: number }[]): number {
  return steps.reduce(
    (total, step) => (step.kind === "module" ? total + (step.findings ?? 0) : total),
    0,
  );
}
