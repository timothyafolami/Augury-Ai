import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/** The printed sheet has to carry its own colours.
 *
 * Printing clones the sheet and attaches the copy directly to `<body>`, which
 * is the only way to escape the review column's scroll clipping. That means
 * the copy leaves every ancestor behind -- including whichever element the
 * paper palette was declared on.
 *
 * When those tokens lived on `.dossier-wrap`, the copy resolved every
 * `var(--paper-ink)` to nothing and inherited the application's pale chalk
 * instead. The PDF came out with washed-out headings, an invisible claim box
 * and an invisible "what to do" block, while the body paragraphs -- which use
 * literal hex -- stayed dark. Found by rendering the print copy under the
 * print rules and looking at it.
 *
 * So: anything the sheet uses must be declared somewhere the clone still
 * matches. `.sheet` itself, or `:root`.
 */

const css = readFileSync(fileURLToPath(new URL("../index.css", import.meta.url)), "utf8");

/** Selectors of every rule that declares `name`. */
function declaredIn(name: string): string[] {
  const found: string[] = [];
  const rule = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = rule.exec(css)) !== null) {
    if (match[2].includes(`${name}:`)) found.push(match[1].trim().split("\n").pop()!.trim());
  }
  return found;
}

const TOKENS = ["--paper", "--paper-ink", "--paper-mute", "--paper-rule", "--paper-accent"];

/** A selector the cloned sheet still matches once it is a child of body. */
const survivesTheClone = (selector: string) =>
  selector === ".sheet" || selector === ":root" || selector.split(",").some((s) => s.trim() === ".sheet");

describe("the paper palette", () => {
  it.each(TOKENS)("declares %s where the printed copy can still see it", (token) => {
    const where = declaredIn(token);

    expect(where.length).toBeGreaterThan(0);
    expect(where.some(survivesTheClone)).toBe(true);
  });

  it("does not leave the palette only on the wrapper", () => {
    // `.dossier-wrap` is exactly the ancestor the print copy escapes.
    for (const token of TOKENS) {
      const where = declaredIn(token);
      expect(where).not.toEqual([".dossier-wrap"]);
    }
  });

  it("uses no other custom property the clone would lose", () => {
    // Everything else the sheet reads must come from Tailwind's `@theme`,
    // which lands on `:root` and is therefore inherited by anything on body.
    const used = new Set<string>();
    for (const [, name] of css.matchAll(/var\((--[a-z0-9-]+)/g)) used.add(name);

    const paperish = [...used].filter((n) => n.startsWith("--paper"));

    for (const name of paperish) {
      expect(declaredIn(name).some(survivesTheClone)).toBe(true);
    }
  });
});
