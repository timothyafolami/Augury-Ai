import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

/** AUGURY, drawn the way the product works.
 *
 * An augury is a reading taken before the thing happens, so the word is not
 * faded in. A read-head travels the baseline; each letter it reaches is first
 * UNCERTAIN, flickering through other forms it might have been, then STROKED as
 * the head passes, then SETTLED. Uncertain, read, certain, which is the order
 * the reviewer works in and the reason the mark is worth animating at all.
 *
 * The letterforms are hand-drawn paths rather than a font: a font cannot be
 * stroke-animated reliably, and these all sit on one grid (70 wide, 100 tall,
 * 10 stroke), which is why the word spaces so evenly and why a glyph can be
 * swapped for another mid-animation without the layout moving.
 */

interface Glyph {
  d: string;
  /** Forms this letter passes through before it resolves. Same grid, so a
   *  swap changes what is drawn and never where it sits. */
  maybe: string[];
}

const A = "M4 100 L35 2 L66 100 M17 64 H53";
const U = "M5 2 V64 A30 30 0 0 0 65 64 V2";
const G = "M64 27 A33 33 0 1 0 64 73 V55 H41";
const R = "M8 100 V2 H39 A25 25 0 0 1 39 52 H8 M39 52 L66 100";
const Y = "M4 2 L35 50 L66 2 M35 50 V100";

// Forms borrowed from the other letters, plus two that are nobody: a reading
// that has not resolved should not look like a tidy alphabet.
const V = "M4 2 L35 100 L66 2";
const O = "M35 2 A31 33 0 1 0 35 99 A31 33 0 1 0 35 2";
const H = "M8 2 V100 M62 2 V100 M8 51 H62";
const X = "M6 2 L64 100 M64 2 L6 100";

const LETTERS: Glyph[] = [
  { d: A, maybe: [V, X, H] },
  { d: U, maybe: [O, V, U] },
  { d: G, maybe: [O, U, G] },
  { d: U, maybe: [V, O, U] },
  { d: R, maybe: [H, O, R] },
  { d: Y, maybe: [V, X, Y] },
];

const WIDTH = 70;
const GAP = 22;
const TOTAL = LETTERS.length * WIDTH + GAP * (LETTERS.length - 1);

const FLICKER = 0.055; // seconds each uncertain form is held
const FORMS = 3; // how many it passes through
const DRAW = 0.42; // seconds to stroke the settled form
const STEP = 0.17; // between letters, so the head travels

const UNCERTAIN = FLICKER * FORMS;
const PER_LETTER = UNCERTAIN + DRAW;
const WHOLE = PER_LETTER + STEP * (LETTERS.length - 1);

export function Wordmark({ onSettled }: { onSettled?: () => void }) {
  const still = useReducedMotion();
  const [settled, setSettled] = useState(Boolean(still));

  useEffect(() => {
    if (still) {
      onSettled?.();
      return;
    }
    const done = setTimeout(() => {
      setSettled(true);
      onSettled?.();
    }, WHOLE * 1000);
    return () => clearTimeout(done);
  }, [still, onSettled]);

  return (
    <div className="relative w-full max-w-[42rem] pr-6">
      <svg viewBox={`-8 -10 ${TOTAL + 16} 132`} className="w-full overflow-visible">
        <defs>
          <linearGradient id="augur-read" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-augur-600)" />
            <stop offset="55%" stopColor="var(--color-augur-400)" />
            <stop offset="100%" stopColor="var(--color-augur-50)" />
          </linearGradient>

          {/* Transparent at both edges, or the idle sweep renders as a
              rectangle sitting on the artwork instead of a pass of light. */}
          <linearGradient id="augur-sweep" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-augur-200)" stopOpacity="0" />
            <stop offset="50%" stopColor="var(--color-augur-50)" stopOpacity="0.85" />
            <stop offset="100%" stopColor="var(--color-augur-200)" stopOpacity="0" />
          </linearGradient>

          <filter id="augur-bloom" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Confines the idle sweep to the letters, so it lights the word
              rather than the space around it. */}
          <mask id="augur-letters">
            <g
              stroke="#fff"
              strokeWidth="13"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            >
              {LETTERS.map((letter, index) => (
                <path
                  key={index}
                  d={letter.d}
                  transform={`translate(${index * (WIDTH + GAP)} 0)`}
                />
              ))}
            </g>
          </mask>
        </defs>

        {/* The baseline the head runs along, drawn ahead of the letters so the
            word looks measured rather than placed. */}
        <motion.line
          x1={0}
          y1={116}
          x2={TOTAL}
          y2={116}
          stroke="var(--color-edge)"
          strokeWidth="1.5"
          initial={still ? { pathLength: 1 } : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: WHOLE * 0.9, ease: "linear" }}
        />

        {LETTERS.map((letter, index) => (
          <Letter key={index} glyph={letter} index={index} still={Boolean(still)} />
        ))}

        {/* The head itself: it is between the letters, which is where the
            transformation happens. */}
        {!still && !settled && (
          <motion.g
            initial={{ x: -10 }}
            animate={{ x: TOTAL + 6 }}
            transition={{ duration: WHOLE * 0.92, ease: "linear" }}
          >
            <line
              x1={0}
              y1={-6}
              x2={0}
              y2={116}
              stroke="var(--color-augur-400)"
              strokeWidth="1.5"
              opacity={0.5}
            />
            <circle cx={0} cy={116} r={4} fill="var(--color-augur-50)" filter="url(#augur-bloom)" />
          </motion.g>
        )}

        {settled && !still && (
          <g mask="url(#augur-letters)">
            <motion.rect
              y={-12}
              width={150}
              height={130}
              fill="url(#augur-sweep)"
              initial={{ x: -170 }}
              animate={{ x: TOTAL + 30 }}
              transition={{ duration: 1.9, repeat: Infinity, repeatDelay: 4.5, ease: "easeInOut" }}
            />
          </g>
        )}
      </svg>
    </div>
  );
}

/** One letter: uncertain, then read, then settled. */
function Letter({ glyph, index, still }: { glyph: Glyph; index: number; still: boolean }) {
  const arrives = index * STEP;
  const [form, setForm] = useState(still ? glyph.d : glyph.maybe[0]);
  const [read, setRead] = useState(still);

  useEffect(() => {
    if (still) return;
    const timers: number[] = [];
    glyph.maybe.forEach((candidate, step) => {
      timers.push(
        window.setTimeout(() => setForm(candidate), (arrives + step * FLICKER) * 1000),
      );
    });
    timers.push(
      window.setTimeout(() => {
        setForm(glyph.d);
        setRead(true);
      }, (arrives + UNCERTAIN) * 1000),
    );
    return () => timers.forEach(clearTimeout);
  }, [glyph, arrives, still]);

  const settledAt = arrives + UNCERTAIN;

  return (
    <g transform={`translate(${index * (WIDTH + GAP)} 0)`}>
      {/* The form it currently might be. Dim while uncertain, gone once read. */}
      <motion.path
        d={form}
        fill="none"
        stroke="var(--color-augur-600)"
        strokeWidth="10"
        strokeLinecap="round"
        strokeLinejoin="round"
        animate={{ opacity: read ? 0 : 0.55 }}
        transition={{ duration: 0.12 }}
      />

      {/* Stroked as the head passes. */}
      <motion.path
        d={glyph.d}
        fill="none"
        stroke="url(#augur-read)"
        strokeWidth="10"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#augur-bloom)"
        initial={still ? { pathLength: 1 } : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: DRAW, delay: settledAt, ease: [0.65, 0, 0.35, 1] }}
      />

      {/* Settled: it stops glowing once it is known. */}
      <motion.path
        d={glyph.d}
        fill="none"
        stroke="var(--color-chalk)"
        strokeWidth="10"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={still ? { opacity: 1 } : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.45, delay: settledAt + DRAW * 0.8 }}
      />
    </g>
  );
}

/** The tagline, typed rather than faded, one character at a time. */
export function Typed({ text, delay = 0 }: { text: string; delay?: number }) {
  const still = useReducedMotion();
  const [shown, setShown] = useState(still ? text.length : 0);

  useEffect(() => {
    if (still) return;
    let index = 0;
    const start = window.setTimeout(() => {
      const tick = window.setInterval(() => {
        index += 1;
        setShown(index);
        if (index >= text.length) window.clearInterval(tick);
      }, 16);
    }, delay * 1000);
    return () => window.clearTimeout(start);
  }, [text, delay, still]);

  return (
    <span className="font-mono">
      {text.slice(0, shown)}
      {shown < text.length && (
        <motion.span
          className="inline-block w-[0.5ch] bg-augur-400"
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.9, repeat: Infinity }}
        >
          &nbsp;
        </motion.span>
      )}
    </span>
  );
}
