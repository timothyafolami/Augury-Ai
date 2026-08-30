import { describe, expect, it } from "vitest";

import { place } from "./Convergence";
import type { Pressure } from "../lib/types";

/** The layout behind the forecast diagram.
 *
 * Two defects in this maths shipped and were found by looking at the screen:
 * a layer label rendered on top of an evidence dot, and two one-finding
 * mechanisms on adjacent rows rendering one label over the other. The second
 * is the kind a test catches and an eye might not, because it only appears
 * when two mechanisms happen to be small and adjacent.
 *
 * A diagram is hard to assert on. An array of numbers is not.
 */

const evidence = (path: string, line: number, layer = "data") => ({
  path,
  line,
  symbol: `sym${line}`,
  layer,
  trigger: "held open across",
});

const pressure = (mechanism: string, marks: number, band = "isolated"): Pressure =>
  ({
    mechanism,
    band,
    independent_findings: marks,
    derivation: "several findings named the same mechanism",
    rule: "a rule",
    evidence: Array.from({ length: marks }, (_, at) => evidence(`app/f${at}.py`, at + 1)),
  }) as Pressure;

describe("laying out the convergence", () => {
  it("gives every finding its own row", () => {
    const { placed } = place([pressure("a", 2), pressure("b", 3)]);

    const rows = placed.flatMap((group) => group.evidence.map((piece) => piece.y));

    expect(new Set(rows).size).toBe(5);
  });

  it("puts a mechanism at the middle of the rows that feed it", () => {
    const { placed } = place([pressure("a", 3)]);

    const marks = placed[0].evidence.map((piece) => piece.y);
    expect(placed[0].y).toBe((marks[0] + marks[marks.length - 1]) / 2);
  });

  it("never lets two mechanisms land on top of each other", () => {
    // The shipped bug: "secret exposure" and "undiagnosable failure", both
    // isolated, both one finding, both on adjacent rows.
    const { placed } = place([
      pressure("secret exposure", 1),
      pressure("undiagnosable failure", 1),
      pressure("another isolated one", 1),
    ]);

    for (let index = 1; index < placed.length; index++) {
      expect(placed[index].y - placed[index - 1].y).toBeGreaterThanOrEqual(30);
    }
  });

  it("keeps the order the pressures arrived in", () => {
    // Pushing nodes apart must not reorder them, or a curve would meet the
    // wrong mechanism and the diagram would misattribute evidence.
    const { placed } = place([pressure("first", 1), pressure("second", 1)]);

    expect(placed.map((group) => group.mechanism)).toEqual(["first", "second"]);
  });

  it("grows tall enough to hold the lowest node it placed", () => {
    // Nodes pushed apart can end up below the last evidence row, and a
    // viewBox measured only from the rows would clip them.
    const { placed, height } = place([
      pressure("a", 1),
      pressure("b", 1),
      pressure("c", 1),
      pressure("d", 1),
    ]);

    expect(height).toBeGreaterThan(placed[placed.length - 1].y);
  });

  it("labels a mark by its symbol, and falls back to the file", () => {
    const nameless = {
      mechanism: "m",
      band: "isolated",
      independent_findings: 1,
      derivation: "d",
      rule: "r",
      evidence: [{ path: "app/services/checkout.py", line: 4, symbol: "", layer: "data" }],
    } as unknown as Pressure;

    expect(place([nameless]).placed[0].evidence[0].label).toBe("checkout.py");
  });

  it("survives a pressure with no evidence at all", () => {
    // The engine should not emit one, and a diagram that throws takes the
    // whole panel with it.
    const empty = { ...pressure("m", 0), evidence: [] } as Pressure;

    expect(() => place([empty])).not.toThrow();
  });

  it("handles nothing to draw", () => {
    const { placed, height } = place([]);

    expect(placed).toEqual([]);
    expect(height).toBeGreaterThan(0);
  });
});
