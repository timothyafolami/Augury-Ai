import { useMemo, useState } from "react";
import { motion } from "framer-motion";

/** The review as the document a team acts on.
 *
 * The same markdown the CLI writes to disk, rendered rather than
 * reimplemented: there is one review engine, and a team reading this in a
 * browser and a team reading the file should be reading the same review.
 *
 * Rendered with a small deliberate subset. A full markdown parser is a
 * dependency and an attack surface for text that came out of a model, and this
 * document only ever contains headings, paragraphs, lists, tables and code.
 */
export function Document({ markdown }: { markdown: string }) {
  const [open, setOpen] = useState(false);
  const blocks = useMemo(() => parse(markdown), [markdown]);

  if (!markdown) return null;

  return (
    <div>
      <button
        onClick={() => setOpen((was) => !was)}
        className="flex w-full items-center gap-3 border border-edge bg-ink px-4 py-2.5 text-left transition hover:bg-slate-panel"
      >
        <span className="font-mono text-[11px] text-chalk">
          the document this review writes
        </span>
        <span className="font-mono text-[10px] text-mist">
          {markdown.split("\n").length} lines · identical to the file the CLI writes
        </span>
        <span className="ml-auto font-mono text-[10px] text-mist">{open ? "hide" : "read"}</span>
      </button>

      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-3 max-h-[36rem] overflow-y-auto border border-edge bg-void/60 px-6 py-5"
        >
          {blocks.map((block, index) => (
            <Block key={index} block={block} />
          ))}
        </motion.div>
      )}
    </div>
  );
}

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "text"; text: string }
  | { kind: "bullet"; text: string }
  | { kind: "code"; text: string }
  | { kind: "row"; cells: string[]; head: boolean };

function Block({ block }: { block: Block }) {
  if (block.kind === "heading") {
    const size =
      block.level === 1 ? "text-lg" : block.level === 2 ? "text-[15px]" : "text-[13px]";
    return (
      <h3 className={`mt-5 first:mt-0 font-medium text-chalk ${size}`}>
        <Inline text={block.text} />
      </h3>
    );
  }
  if (block.kind === "bullet") {
    return (
      <p className="mt-1.5 flex gap-2 text-[13px] leading-relaxed text-mist">
        <span className="text-augur-400">·</span>
        <span>
          <Inline text={block.text} />
        </span>
      </p>
    );
  }
  if (block.kind === "code") {
    return (
      <pre className="mt-3 overflow-x-auto bg-ink px-3 py-2 font-mono text-[11px] text-chalk/80">
        {block.text}
      </pre>
    );
  }
  if (block.kind === "row") {
    return (
      <div className="flex gap-3 border-b border-edge/40 py-1.5">
        {block.cells.map((cell, index) => (
          <span
            key={index}
            className={`min-w-0 flex-1 truncate text-[12px] ${
              block.head ? "font-mono text-[10px] uppercase tracking-widest text-mist" : "text-chalk/80"
            }`}
          >
            <Inline text={cell} />
          </span>
        ))}
      </div>
    );
  }
  return (
    <p className="mt-3 text-[13px] leading-relaxed text-mist">
      <Inline text={block.text} />
    </p>
  );
}

/** Backticks and bold. Everything else is left as written. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={index} className="bg-ink px-1 font-mono text-[11px] text-augur-200">
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={index} className="font-medium text-chalk">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

function parse(markdown: string): Block[] {
  const blocks: Block[] = [];
  let fenced: string[] | null = null;
  let head = true;

  for (const line of markdown.split("\n")) {
    if (line.startsWith("```")) {
      if (fenced) {
        blocks.push({ kind: "code", text: fenced.join("\n") });
        fenced = null;
      } else {
        fenced = [];
      }
      continue;
    }
    if (fenced) {
      fenced.push(line);
      continue;
    }
    if (!line.trim()) {
      head = true;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    if (line.startsWith("- ")) {
      blocks.push({ kind: "bullet", text: line.slice(2) });
      continue;
    }
    if (line.startsWith("|")) {
      const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
      // The dashed rule under a table header carries no content of its own.
      if (cells.every((cell) => /^-+$/.test(cell))) continue;
      blocks.push({ kind: "row", cells, head });
      head = false;
      continue;
    }
    blocks.push({ kind: "text", text: line });
  }
  if (fenced) blocks.push({ kind: "code", text: fenced.join("\n") });
  return blocks;
}
