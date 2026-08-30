import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/** Choosing a directory by looking rather than by remembering.
 *
 * The server refuses anything outside its declared roots, so this cannot walk
 * anywhere the review could not read anyway. Directories a review would never
 * open are hidden, because node_modules and .venv are most of a tree by count
 * and none of it by meaning, and the ones that look like a repository are
 * marked so the list leads somewhere.
 */

interface Entry {
  name: string;
  path: string;
  looksLikeARepository: boolean;
}

export function Picker({
  path,
  onPick,
  onClose,
}: {
  path: string;
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [here, setHere] = useState(path);
  const [parent, setParent] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const open = useCallback(async (where: string) => {
    setBusy(true);
    setError("");
    try {
      const answer = await fetch("/api/browse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: where }),
      });
      if (!answer.ok) {
        const { detail } = await answer.json().catch(() => ({ detail: answer.statusText }));
        throw new Error(String(detail));
      }
      const seen = await answer.json();
      setHere(seen.here);
      setParent(seen.parent);
      setEntries(seen.directories);
    } catch (caught) {
      setError(String(caught instanceof Error ? caught.message : caught));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void open(path || ".");
  }, [open, path]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 p-8 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.97, y: 8 }}
        animate={{ scale: 1, y: 0 }}
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[70vh] w-full max-w-2xl flex-col border border-edge bg-ink"
      >
        <header className="flex items-center gap-3 border-b border-edge px-4 py-3">
          <button
            onClick={() => parent && open(parent)}
            disabled={!parent || busy}
            className="border border-edge px-2 py-1 font-mono text-[11px] text-mist transition hover:text-chalk disabled:opacity-30"
          >
            ↑ up
          </button>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-chalk" title={here}>
            {here}
          </span>
          <button onClick={onClose} className="font-mono text-[11px] text-mist hover:text-chalk">
            close
          </button>
        </header>

        {error && (
          <p className="border-b border-verdict-miss/30 bg-verdict-miss/10 px-4 py-2 font-mono text-[11px] text-verdict-miss">
            {error}
          </p>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          <AnimatePresence initial={false}>
            {entries.map((entry, index) => (
              <motion.button
                key={entry.path}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: Math.min(index * 0.012, 0.2) }}
                onClick={() => open(entry.path)}
                onDoubleClick={() => onPick(entry.path)}
                className="flex w-full items-center gap-3 border-b border-edge/40 px-4 py-2 text-left transition hover:bg-slate-panel"
              >
                <span className="font-mono text-[11px] text-mist">
                  {entry.looksLikeARepository ? "▣" : "▢"}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-chalk">
                  {entry.name}
                </span>
                {entry.looksLikeARepository && (
                  <span
                    onClick={(event) => {
                      event.stopPropagation();
                      onPick(entry.path);
                    }}
                    className="shrink-0 border border-augur-500/50 bg-augur-600/15 px-2 py-0.5 font-mono text-[10px] text-augur-200 transition hover:bg-augur-600/30"
                  >
                    review this
                  </span>
                )}
              </motion.button>
            ))}
          </AnimatePresence>

          {!busy && entries.length === 0 && (
            <p className="py-10 text-center font-mono text-[11px] text-mist/50">
              nothing here a review would read
            </p>
          )}
        </div>

        <footer className="flex items-center gap-3 border-t border-edge px-4 py-3">
          <span className="font-mono text-[10px] text-mist/60">
            ▣ has a compose file, a manifest or a git directory
          </span>
          <button
            onClick={() => onPick(here)}
            className="ml-auto bg-augur-600 px-4 py-1.5 font-mono text-[11px] text-white transition hover:bg-augur-500"
          >
            review this directory
          </button>
        </footer>
      </motion.div>
    </motion.div>
  );
}
