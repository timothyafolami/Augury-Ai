import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Picker } from "./Picker";

/** Choosing what to review.
 *
 * A path and a scope, and nothing else. No sign-in, no organisation, no
 * repository provider: the reviewer reads a directory, and every screen this
 * would have added is a screen that proves nothing about the product.
 */
export function Connect({
  onConnect,
  busy,
  error,
}: {
  onConnect: (path: string, scope: string, budget: number) => void;
  busy: boolean;
  error: string;
}) {
  const [path, setPath] = useState("../Interview-AI-Prod");
  const [scope, setScope] = useState("backend");
  // A dollar, because that is what a review of a real backend costs and a
  // ceiling low enough to stop one is a ceiling that hides the product.
  const [budget, setBudget] = useState(1);
  const [picking, setPicking] = useState(false);

  return (
    <section className="relative flex min-h-screen items-center justify-center px-8">
      <div className="pointer-events-none absolute inset-0 grid-faint opacity-25" />

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-xl"
      >
        <h1 className="text-center font-mono text-sm uppercase tracking-[0.32em] text-mist">
          connect a codebase
        </h1>

        <div className="mt-9 border border-edge bg-ink/70 p-8">
          <label className="block font-mono text-[11px] uppercase tracking-widest text-mist">
            project directory
          </label>
          <div className="mt-2 flex gap-2">
          <input
            value={path}
            onChange={(event) => setPath(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onConnect(path, scope, budget)}
            spellCheck={false}
            className="w-full min-w-0 border border-edge bg-void px-4 py-3 font-mono text-sm text-chalk outline-none transition focus:border-augur-500"
          />
          <button
            onClick={() => setPicking(true)}
            className="shrink-0 border border-edge px-4 font-mono text-[11px] text-mist transition hover:border-augur-500 hover:text-chalk"
          >
            browse
          </button>
          </div>

          <label className="mt-6 block font-mono text-[11px] uppercase tracking-widest text-mist">
            scope <span className="normal-case tracking-normal">— a subdirectory, or all of it</span>
          </label>
          <input
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onConnect(path, scope, budget)}
            spellCheck={false}
            placeholder="backend — leave empty for the whole repository"
            className="mt-2 w-full border border-edge bg-void px-4 py-3 font-mono text-sm text-chalk outline-none transition focus:border-augur-500"
          />

          <label className="mt-6 block font-mono text-[11px] uppercase tracking-widest text-mist">
            spend ceiling
            <span className="normal-case tracking-normal"> — 0 for no ceiling</span>
          </label>
          <div className="mt-2 flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={5}
              step={0.25}
              value={budget}
              onChange={(event) => setBudget(Number(event.target.value))}
              className="h-1 flex-1 appearance-none bg-edge accent-augur-500"
            />
            <span className="w-24 shrink-0 border border-edge bg-void px-3 py-2 text-right font-mono text-sm text-chalk">
              {budget === 0 ? "none" : `$${budget.toFixed(2)}`}
            </span>
          </div>
          <p className="mt-2 font-mono text-[10px] leading-relaxed text-mist/60">
            The ceiling is enforced before a module is issued, against a rate the
            run measures from its own first two modules rather than a guess.
          </p>

          <button
            onClick={() => onConnect(path, scope, budget)}
            disabled={busy}
            className="mt-8 w-full bg-augur-600 py-3.5 font-mono text-sm text-white transition hover:bg-augur-500 disabled:opacity-40"
          >
            {busy ? "reading the deployment…" : "start engineering review"}
          </button>

          {error && (
            <p className="mt-4 border-l-2 border-verdict-miss/60 bg-verdict-miss/10 px-3 py-2 font-mono text-xs text-verdict-miss">
              {error}
            </p>
          )}
        </div>

        <p className="mt-6 text-center font-mono text-[11px] leading-relaxed tracking-wide text-mist/70">
          SUPPORTED EXECUTION · CLI · MCP · WEB
          <br />
          <span className="text-mist/50">one review engine, three clients</span>
        </p>
      </motion.div>

      <AnimatePresence>
        {picking && (
          <Picker
            path={path}
            onPick={(chosen) => {
              setPath(chosen);
              setPicking(false);
            }}
            onClose={() => setPicking(false)}
          />
        )}
      </AnimatePresence>
    </section>
  );
}
