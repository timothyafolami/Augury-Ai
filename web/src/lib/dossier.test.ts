import { describe, expect, it } from "vitest";

import {
  claimOf,
  everyFinding,
  filenameFor,
  headline,
  ranked,
  titleFor,
  verdictOf,
} from "./dossier";
import type { Finding, Report } from "./types";

/** The logic behind the printed report.
 *
 * Kept out of the component because a report is the artefact someone acts on:
 * if it puts a low-severity note above a high one, or calls an untested claim
 * a hit, the person reading it makes the wrong call on Monday. None of that is
 * presentation, so none of it lives in JSX.
 */

const finding = (over: Partial<Finding> = {}): Finding => ({
  path: "app/db.py",
  line: 12,
  layer: "data",
  symbol: "engine",
  severity: "medium",
  mechanism: "the pool is created per request",
  remediation: "create the engine once at import",
  rule: "",
  prediction: null,
  measurement: null,
  ...over,
});

const report = (over: Partial<Report> = {}): Report => ({
  name: "orders-service",
  usd: 0.0582,
  seconds: 43.1,
  modelId: "groq/openai/gpt-oss-120b",
  coverage: null,
  findings: [],
  dropped: [],
  schema: [],
  dependencies: [],
  ...over,
});

describe("ranking", () => {
  it("puts high severity first and low last", () => {
    const order = ranked([
      finding({ severity: "low", symbol: "a" }),
      finding({ severity: "high", symbol: "b" }),
      finding({ severity: "medium", symbol: "c" }),
    ]).map((f) => f.symbol);

    expect(order).toEqual(["b", "c", "a"]);
  });

  it("puts a measured claim above an unmeasured one at the same severity", () => {
    // A finding an experiment settled is worth more of the reader's attention
    // than one that is still an assertion, however confidently phrased.
    const order = ranked([
      finding({ severity: "high", symbol: "assertion" }),
      finding({
        severity: "high",
        symbol: "measured",
        prediction: {
          metric: "queries_per_request",
          comparator: "at_least",
          value: 51,
          upper: null,
          unit: "queries",
          condition: "GET /orders",
        },
        measurement: { value: 51, detail: "" },
      }),
    ]).map((f) => f.symbol);

    expect(order).toEqual(["measured", "assertion"]);
  });

  it("orders by file when nothing else separates two findings", () => {
    // Stable and readable: a reader working through a report wants one file at
    // a time, not the same file three sections apart.
    const order = ranked([
      finding({ path: "z.py", symbol: "z" }),
      finding({ path: "a.py", symbol: "a" }),
    ]).map((f) => f.symbol);

    expect(order).toEqual(["a", "z"]);
  });

  it("does not mutate what it was given", () => {
    const given = [finding({ severity: "low" }), finding({ severity: "high" })];
    ranked(given);

    expect(given[0].severity).toBe("low");
  });
});

describe("verdicts", () => {
  it("is untested when the finding carries no claim", () => {
    expect(verdictOf(finding())).toBe("untested");
  });

  it("is untested when a claim was made but nothing measured it", () => {
    expect(
      verdictOf(
        finding({
          prediction: {
            metric: "p99_latency",
            comparator: "at_least",
            value: 100,
            upper: null,
            unit: "ms",
            condition: "under load",
          },
        }),
      ),
    ).toBe("untested");
  });

  it("is broken when the experiment ran and measured nothing", () => {
    // Silence is not zero. This is the distinction the whole project turns on.
    expect(
      verdictOf(
        finding({
          prediction: {
            metric: "p99_latency",
            comparator: "at_least",
            value: 100,
            upper: null,
            unit: "ms",
            condition: "under load",
          },
          measurement: { value: null, detail: "printed no number" },
        }),
      ),
    ).toBe("broken");
  });

  it("is a hit when the measurement satisfies the claim", () => {
    expect(
      verdictOf(
        finding({
          prediction: {
            metric: "queries_per_request",
            comparator: "at_least",
            value: 51,
            upper: null,
            unit: "queries",
            condition: "GET /orders",
          },
          measurement: { value: 51, detail: "" },
        }),
      ),
    ).toBe("hit");
  });

  it("is a miss when the measurement refutes the claim", () => {
    expect(
      verdictOf(
        finding({
          prediction: {
            metric: "queries_per_request",
            comparator: "at_least",
            value: 51,
            upper: null,
            unit: "queries",
            condition: "GET /orders",
          },
          measurement: { value: 2, detail: "" },
        }),
      ),
    ).toBe("miss");
  });

  it("reads a between claim against both ends", () => {
    const between = {
      metric: "final_balance",
      comparator: "between",
      value: 10,
      upper: 100,
      unit: "x",
      condition: "concurrent debits",
    };

    expect(verdictOf(finding({ prediction: between, measurement: { value: 40, detail: "" } }))).toBe("hit");
    expect(verdictOf(finding({ prediction: between, measurement: { value: 400, detail: "" } }))).toBe("miss");
  });
});

describe("the claim as a sentence", () => {
  it("carries the metric, the number, the unit and the condition", () => {
    const said = claimOf(
      finding({
        prediction: {
          metric: "queries_per_request",
          comparator: "at_least",
          value: 51,
          upper: null,
          unit: "queries",
          condition: "GET /orders for a customer with 50 orders",
        },
      }),
    );

    expect(said).toContain("queries_per_request");
    expect(said).toContain("51");
    expect(said).toContain("queries");
    expect(said).toContain("GET /orders for a customer with 50 orders");
  });

  it("says so plainly when there is no claim, rather than inventing one", () => {
    expect(claimOf(finding())).toBe("no falsifiable claim");
  });

  it("shows both ends of a range", () => {
    const said = claimOf(
      finding({
        prediction: {
          metric: "final_balance",
          comparator: "between",
          value: 10,
          upper: 100,
          unit: "x",
          condition: "concurrent debits",
        },
      }),
    );

    expect(said).toContain("10");
    expect(said).toContain("100");
  });
});

describe("everything the review found", () => {
  it("gathers the model findings and the free deterministic ones", () => {
    const all = everyFinding(
      report({
        findings: [finding({ symbol: "model" })],
        deployment: [finding({ symbol: "deploy" })],
        schema: [finding({ symbol: "schema" })],
        dependencies: [finding({ symbol: "dep" })],
      }),
    );

    expect(all.map((f) => f.symbol).sort()).toEqual(["dep", "deploy", "model", "schema"]);
  });

  it("survives a report whose optional sections are absent", () => {
    expect(everyFinding(report())).toEqual([]);
  });
});

describe("the headline a reader sees first", () => {
  it("counts by severity", () => {
    const said = headline(
      report({
        findings: [
          finding({ severity: "high" }),
          finding({ severity: "high" }),
          finding({ severity: "low" }),
        ],
      }),
    );

    expect(said.high).toBe(2);
    expect(said.medium).toBe(0);
    expect(said.low).toBe(1);
    expect(said.total).toBe(3);
  });

  it("counts what was measured separately from what was asserted", () => {
    const said = headline(
      report({
        findings: [
          finding({
            prediction: {
              metric: "m",
              comparator: "at_least",
              value: 1,
              upper: null,
              unit: "ms",
              condition: "c",
            },
            measurement: { value: 5, detail: "" },
          }),
          finding(),
        ],
      }),
    );

    expect(said.measured).toBe(1);
    expect(said.total).toBe(2);
  });

  it("reports zero honestly rather than reading as a failed run", () => {
    const said = headline(report());

    expect(said.total).toBe(0);
    expect(said.measured).toBe(0);
  });
});

describe("what the downloaded file is called", () => {
  it("is the folder name and what the document is", () => {
    expect(filenameFor({ name: "orders-service", root: "/src/orders-service" })).toBe(
      "orders-service_augury_review_report",
    );
  });

  it("uses the name the report is headed with, not the raw folder", () => {
    // A file called `repo_augury_review_report` in a downloads folder names
    // nothing, and two of them collide.
    expect(
      filenameFor({ name: "repo", root: "/eval/cases/B01-orders-service/repo" }),
    ).toBe("B01-orders-service_augury_review_report");
  });

  it("strips anything a filesystem would object to", () => {
    expect(filenameFor({ name: "my service (v2)", root: "/x/my service (v2)" })).toBe(
      "my-service-v2_augury_review_report",
    );
  });

  it("still produces a usable name when there is nothing to go on", () => {
    expect(filenameFor({ name: "", root: "" })).toBe("this-repository_augury_review_report");
  });
});

describe("what the report is called", () => {
  it("uses the repository name", () => {
    expect(titleFor({ name: "orders-service", root: "/src/orders-service" })).toBe(
      "orders-service",
    );
  });

  it("climbs past a generically named folder", () => {
    // People review `~/work/payments/backend` and `eval/cases/B01/repo`, and a
    // report headed "backend" names nothing. The folder above it does.
    expect(titleFor({ name: "repo", root: "/eval/cases/B01-orders-service/repo" })).toBe(
      "B01-orders-service",
    );
    expect(titleFor({ name: "backend", root: "/work/payments/backend" })).toBe("payments");
    expect(titleFor({ name: "src", root: "/work/ledger/src" })).toBe("ledger");
  });

  it("keeps a generic name when there is nothing above it", () => {
    expect(titleFor({ name: "app", root: "/app" })).toBe("app");
  });

  it("does not climb twice", () => {
    // Two generic segments is unusual enough that guessing further is worse
    // than showing what the user actually pointed at.
    expect(titleFor({ name: "src", root: "/work/backend/src" })).toBe("backend");
  });

  it("falls back when there is no path at all", () => {
    expect(titleFor({ name: "", root: "" })).toBe("this repository");
  });
});
