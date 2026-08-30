import { motion } from "framer-motion";
import { useState } from "react";

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
  onConnect: (path: string, scope: string) => void;
  busy: boolean;
  error: string;
}) {
  const [path, setPath] = useState("../Interview-AI-Prod");
  const [scope, setScope] = useState("backend");

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
          <input
            value={path}
            onChange={(event) => setPath(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onConnect(path, scope)}
            spellCheck={false}
            className="mt-2 w-full border border-edge bg-void px-4 py-3 font-mono text-sm text-chalk outline-none transition focus:border-augur-500"
          />

          <label className="mt-6 block font-mono text-[11px] uppercase tracking-widest text-mist">
            scope <span className="normal-case tracking-normal">— a subdirectory, or all of it</span>
          </label>
          <input
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onConnect(path, scope)}
            spellCheck={false}
            placeholder="backend"
            className="mt-2 w-full border border-edge bg-void px-4 py-3 font-mono text-sm text-chalk outline-none transition focus:border-augur-500"
          />

          <button
            onClick={() => onConnect(path, scope)}
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
    </section>
  );
}
