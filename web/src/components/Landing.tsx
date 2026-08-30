import { motion } from "framer-motion";
import { useState } from "react";
import { Topology } from "./Topology";
import { Typed, Wordmark } from "./Wordmark";

/** The opening screen.
 *
 * Minimal on purpose. The name, three words, and a system re-reading itself.
 * A marketing hero with paragraphs would be arguing for the product; the
 * topology rearranging is the product's actual claim, which is that
 * understanding what you have comes before judging it.
 */
export function Landing({ onStart }: { onStart: () => void }) {
  const [settled, setSettled] = useState(false);

  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-8 py-14">
      <div className="pointer-events-none absolute inset-0 grid-faint opacity-30" />

      <div className="relative flex w-full max-w-3xl flex-col items-center">
        <Wordmark onSettled={() => setSettled(true)} />

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: settled ? 1 : 0 }}
          transition={{ duration: 0.5 }}
          className="mt-7 text-center text-[13px] uppercase tracking-[0.42em] text-mist"
        >
          <Typed text="understand · review · predict" delay={0.1} />
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: settled ? 1 : 0, y: settled ? 0 : 16 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="mt-12 w-full max-w-lg"
        >
          <Topology />
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: settled ? 1 : 0 }}
          transition={{ duration: 0.6, delay: 0.7 }}
          className="mt-10 flex flex-col items-center gap-5"
        >
          <p className="max-w-md text-center text-sm leading-relaxed text-mist">
            An engineering review that reasons from named mechanisms, states what it
            expects to measure, and reports what it did not look at.
          </p>

          <button
            onClick={onStart}
            className="group border border-augur-500/60 bg-augur-600/10 px-9 py-3.5 font-mono text-sm text-augur-100 transition hover:bg-augur-600/25"
          >
            review a codebase
            <span className="ml-3 inline-block transition-transform group-hover:translate-x-1">→</span>
          </button>

          <p className="font-mono text-[11px] tracking-widest text-mist/70">
            NO SIGN-IN · CLI · MCP · WEB
          </p>
        </motion.div>
      </div>
    </section>
  );
}
