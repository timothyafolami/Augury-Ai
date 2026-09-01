import type { Finding, Report } from "./types";

/** What the printed report says, separated from how it looks.
 *
 * A report is the artefact somebody acts on. If it ranks a low-severity note
 * above a high one, or calls an untested claim a hit, a person makes the wrong
 * call on Monday morning. None of that is presentation, so none of it lives in
 * a component.
 */

export type Verdict = "hit" | "miss" | "broken" | "untested";

const WEIGHT: Record<Finding["severity"], number> = { high: 0, medium: 1, low: 2 };

/** Most severe first; within a severity, what was measured before what was
 *  merely asserted; then by file, so a reader works through one file at a time.
 *
 *  Copies rather than sorting in place: the caller's array is usually state,
 *  and sorting state in place is how a list re-renders in a different order
 *  than the one it was given.
 */
export function ranked(findings: readonly Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const severity = WEIGHT[a.severity] - WEIGHT[b.severity];
    if (severity !== 0) return severity;

    const settled = Number(isSettled(b)) - Number(isSettled(a));
    if (settled !== 0) return settled;

    if (a.path !== b.path) return a.path < b.path ? -1 : 1;
    return a.line - b.line;
  });
}

const isSettled = (finding: Finding): boolean =>
  finding.prediction !== null && finding.measurement?.value != null;

/** What an experiment made of the claim, if one ran.
 *
 * `broken` is a verdict rather than a failure to report, and it is the
 * distinction this whole project turns on: an experiment that printed no
 * number measured nothing, and grading it against the prediction would invent
 * a result.
 */
export function verdictOf(finding: Finding): Verdict {
  const { prediction, measurement } = finding;
  if (prediction === null) return "untested";
  if (measurement === null) return "untested";
  if (measurement.value === null) return "broken";

  const measured = measurement.value;
  switch (prediction.comparator) {
    case "at_least":
      return measured >= prediction.value ? "hit" : "miss";
    case "at_most":
      return measured <= prediction.value ? "hit" : "miss";
    case "between": {
      const ceiling = prediction.upper ?? Number.POSITIVE_INFINITY;
      return measured >= prediction.value && measured <= ceiling ? "hit" : "miss";
    }
    default:
      return "untested";
  }
}

const SAYS: Record<string, string> = {
  at_least: "at least",
  at_most: "at most",
  between: "between",
};

/** The claim as a sentence a person can argue with.
 *
 * The point of the product is that a reviewer can disagree with the
 * measurement rather than with the model, and that requires the claim to be
 * legible without reading the JSON.
 */
export function claimOf(finding: Finding): string {
  const said = finding.prediction;
  if (said === null) return "no falsifiable claim";

  const comparator = SAYS[said.comparator] ?? said.comparator;
  const amount =
    said.comparator === "between" && said.upper !== null
      ? `${said.value} and ${said.upper}`
      : `${said.value}`;

  return `${said.metric} ${comparator} ${amount} ${said.unit} — ${said.condition}`.trim();
}

/** Everything the review found, model-driven and deterministic together.
 *
 * The deployment, schema and dependency passes cost nothing and are the ones
 * most likely to be actionable before lunch, so a report that omitted them
 * would be hiding its cheapest value.
 */
export function everyFinding(report: Report): Finding[] {
  return [
    ...(report.deployment ?? []),
    ...(report.findings ?? []),
    ...(report.schema ?? []),
    ...(report.dependencies ?? []),
  ];
}

export interface Headline {
  high: number;
  medium: number;
  low: number;
  total: number;
  measured: number;
}

/** The counts a reader sees before anything else. */
export function headline(report: Report): Headline {
  const all = everyFinding(report);
  return {
    high: all.filter((f) => f.severity === "high").length,
    medium: all.filter((f) => f.severity === "medium").length,
    low: all.filter((f) => f.severity === "low").length,
    total: all.length,
    measured: all.filter(isSettled).length,
  };
}

/** Folder names that describe a role rather than a service.
 *
 * A report headed "backend" or "repo" names nothing the reader can act on.
 * People point this at `~/work/payments/backend` and at
 * `eval/cases/B01-orders-service/repo`, and in both the useful name is one
 * level up.
 */
const GENERIC = new Set(["repo", "src", "app", "backend", "server", "service", "api", "code"]);

/** What to head the report with. */
export function titleFor({ name, root }: { name: string; root: string }): string {
  const parts = root.split("/").filter(Boolean);
  const own = name || parts[parts.length - 1] || "";

  if (!own) return "this repository";
  if (!GENERIC.has(own.toLowerCase())) return own;

  // One level, and only one. Two generic segments is unusual enough that
  // guessing further is worse than showing what the user pointed at.
  const above = parts[parts.length - 2];
  return above || own;
}

/** What the downloaded file is called.
 *
 * The name the report is headed with, not the raw folder: a file called
 * `repo_augury_review_report` sitting in a downloads folder names nothing,
 * and the second one collides with the first.
 */
export function filenameFor(where: { name: string; root: string }): string {
  const safe = titleFor(where)
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${safe || "review"}_augury_review_report`;
}
