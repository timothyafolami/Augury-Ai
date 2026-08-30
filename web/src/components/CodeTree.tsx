import { motion } from "framer-motion";
import { useMemo } from "react";
import type { Module } from "../lib/types";
import type { FileState } from "../lib/useRun";

/** The repository, illuminating as it is understood.
 *
 * A directory lights when something inside it has been read, and a file lights
 * when the reviewer actually touched it. Colour is keyed to a real event, never
 * to a timer, so a stalled review shows a stalled tree, which is the honest
 * behaviour and the one a viewer can check against the telemetry beside it.
 */

interface Branch {
  name: string;
  path: string;
  children: Map<string, Branch>;
  module?: Module;
}

export function CodeTree({
  modules,
  files,
}: {
  modules: Module[];
  files: Record<string, FileState>;
}) {
  const root = useMemo(() => build(modules), [modules]);

  return (
    <>
      {/* Named, because three shades of grey are not a vocabulary. A reader
          took "read, nothing found" for "never opened" and concluded the
          review had skipped most of the repository. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pb-2 font-mono text-[9px] text-mist/70">
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 bg-augur-400" /> finding
        </span>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 bg-mist" /> read, clean
        </span>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 border border-edge" /> not read
        </span>
      </div>

      <div className="max-h-[55vh] overflow-y-auto font-mono text-[11px] leading-[1.7] lg:max-h-none">
        {[...root.children.values()].map((branch) => (
          <Node key={branch.path} branch={branch} files={files} depth={0} />
        ))}
      </div>
    </>
  );
}

function Node({
  branch,
  files,
  depth,
}: {
  branch: Branch;
  files: Record<string, FileState>;
  depth: number;
}) {
  const isFile = branch.module !== undefined;
  const state: FileState = isFile ? (files[branch.path] ?? "unread") : folderState(branch, files);

  // Below this the tree stops being a map and starts being a wall of names.
  if (depth > 3) return null;

  return (
    <div>
      <motion.div
        className="flex items-center gap-1.5 truncate"
        style={{ paddingLeft: depth * 12 }}
        animate={state === "reading" ? { opacity: [0.5, 1, 0.5] } : { opacity: 1 }}
        transition={state === "reading" ? { duration: 1.3, repeat: Infinity } : { duration: 0.3 }}
      >
        <span className={`h-1.5 w-1.5 shrink-0 ${dot(state)}`} />
        <span className={`truncate ${text(state, isFile)}`}>{branch.name}</span>
        {!isFile && (
          <span className="ml-auto shrink-0 pl-2 text-[10px] text-mist/40">
            {count(branch)}
          </span>
        )}
        {isFile && state === "flagged" && (
          <span className="ml-auto shrink-0 pl-2 text-[10px] text-augur-300">●</span>
        )}
      </motion.div>

      {[...branch.children.values()]
        .sort((a, b) => Number(Boolean(a.module)) - Number(Boolean(b.module)) || a.name.localeCompare(b.name))
        .map((child) => (
          <Node key={child.path} branch={child} files={files} depth={depth + 1} />
        ))}
    </div>
  );
}

function build(modules: Module[]): Branch {
  const root: Branch = { name: "", path: "", children: new Map() };
  for (const module of modules) {
    const parts = module.path.split("/");
    let at = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      if (!at.children.has(part)) {
        at.children.set(part, { name: part, path, children: new Map() });
      }
      at = at.children.get(part)!;
      if (index === parts.length - 1) at.module = module;
    });
  }
  return root;
}

/** A directory is as read as the most-read thing inside it. */
function folderState(branch: Branch, files: Record<string, FileState>): FileState {
  let best: FileState = "unread";
  const rank: Record<FileState, number> = { unread: 0, read: 1, reading: 2, flagged: 3 };
  const walk = (node: Branch) => {
    if (node.module) {
      const state = files[node.path] ?? "unread";
      if (rank[state] > rank[best]) best = state;
    }
    node.children.forEach(walk);
  };
  walk(branch);
  return best;
}

function count(branch: Branch): string {
  let total = 0;
  const walk = (node: Branch) => {
    if (node.module) total += 1;
    node.children.forEach(walk);
  };
  walk(branch);
  return String(total);
}

// `read` used to be `bg-augur-900` and `unread` `bg-edge`, which are the same
// colour to anyone not comparing them side by side on a dark screen. A reader
// looking at a finished review concluded the files were skipped when sixteen
// of twenty-three had been read and found clean -- the most damaging thing
// this panel can get wrong, because it makes a thorough review look lazy.
function dot(state: FileState): string {
  if (state === "flagged") return "bg-augur-400";
  if (state === "reading") return "bg-augur-500";
  if (state === "read") return "bg-mist";
  return "border border-edge bg-transparent";
}

function text(state: FileState, isFile: boolean): string {
  if (state === "flagged") return "text-augur-200";
  if (state === "reading") return "text-chalk";
  if (state === "read") return "text-chalk/75";
  return isFile ? "text-mist/35" : "text-mist/60";
}
