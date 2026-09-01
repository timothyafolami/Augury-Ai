import { useEffect, useMemo, useRef } from "react";

import {
  claimOf,
  everyFinding,
  filenameFor,
  headline,
  ranked,
  titleFor,
  verdictOf,
} from "../lib/dossier";
import { mountForPrint, release, watchPrinting } from "../lib/printing";
import type { Finding, Report } from "../lib/types";

/** The review as a document somebody signs their name to.
 *
 * Rendered as a light sheet inside a dark application on purpose: this is the
 * artefact that leaves the building, and it should look on screen exactly like
 * it looks on paper. The print stylesheet removes the application around it
 * and changes nothing about the sheet itself, so there is no second layout to
 * keep in agreement with this one.
 *
 * The download is the browser's own PDF writer. It costs no dependency, keeps
 * the text selectable and searchable rather than raster, and means the project
 * still installs from a clean clone with nothing but Python and Node.
 */
export function Dossier({ report }: { report: Report }) {
  const found = useMemo(() => ranked(everyFinding(report)), [report]);
  const counts = useMemo(() => headline(report), [report]);
  const printed = useMemo(() => new Date(), []);
  const sheet = useRef<HTMLElement>(null);
  const title = useMemo(
    () => titleFor({ name: report.name, root: report.root ?? "" }),
    [report],
  );

  // The browser's own print command has to produce the same document the
  // button does, or there are two artefacts and one of them is broken.
  useEffect(() => watchPrinting(() => sheet.current), []);

  /** Hand the document over.
   *
   * The document title becomes the suggested filename in every browser's save
   * dialog, so it is set for the duration of the print and put back after. A
   * file called "Augury" that overwrites last month's is not a report.
   */
  const save = () => {
    if (!sheet.current) return;
    const was = window.document.title;
    window.document.title = filenameFor(report, printed);

    // Lifted out of the review column before printing. That column scrolls,
    // and a scrolling ancestor clips its contents in paged media exactly as it
    // does on screen: printed in place, a seven-thousand-pixel document came
    // out as page one and nothing else.
    const undo = mountForPrint(sheet.current);
    window.print();
    undo();
    release();
    window.document.title = was;
  };

  const day = printed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="dossier-wrap">
      <div className="no-print mb-4 flex items-center justify-between gap-4 border border-edge bg-ink px-4 py-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-augur-400">
            the report
          </p>
          <p className="mt-1 text-[13px] text-mist">
            {counts.total} finding{counts.total === 1 ? "" : "s"} on {title}, ranked by
            severity. Print or save it as PDF.
          </p>
        </div>
        <button
          onClick={save}
          className="shrink-0 whitespace-nowrap border border-augur-500 bg-augur-600/20 px-4 py-2 font-mono text-[12px] text-augur-200 transition hover:bg-augur-600/40"
        >
          download PDF
        </button>
      </div>

      <article ref={sheet} className="sheet">
        <header className="sheet-head">
          <div className="sheet-brand">
            <span className="sheet-mark">AUGURY</span>
            <span className="sheet-kind">Engineering review</span>
          </div>
          <h1 className="sheet-title">{title}</h1>
          <dl className="sheet-meta">
            <Meta label="reviewed" value={day} />
            <Meta label="model" value={report.modelId || "—"} />
            <Meta label="duration" value={`${report.seconds.toFixed(1)}s`} />
            <Meta label="spend" value={report.usd > 0 ? `$${report.usd.toFixed(4)}` : "$0.00"} />
          </dl>
        </header>

        <section className="sheet-glance">
          <Tally label="high" value={counts.high} tone="high" />
          <Tally label="medium" value={counts.medium} tone="medium" />
          <Tally label="low" value={counts.low} tone="low" />
          <Tally label="settled by experiment" value={counts.measured} tone="measured" />
        </section>

        {report.synthesis && report.synthesis.length > 0 && (
          <section className="sheet-section">
            <h2>What this review concluded</h2>
            {report.synthesis.map((item, i) => (
              <div key={i} className="sheet-observation">
                <h3>{item.mechanism}</h3>
                <p>{item.consequence}</p>
                {item.citations.length > 0 && (
                  <p className="sheet-evidence">
                    {item.citations
                      .map((c) => (c.line > 0 ? `${c.path}:${c.line}` : c.path))
                      .filter(Boolean)
                      .join("  ·  ")}
                  </p>
                )}
              </div>
            ))}
          </section>
        )}

        <section className="sheet-section sheet-break">
          <h2>
            Findings
            <span className="sheet-count">{found.length}</span>
          </h2>
          {found.length === 0 && (
            <p className="sheet-empty">
              Nothing was found at this budget. That is a result, not a failure: the coverage
              section below says what was read and what was not.
            </p>
          )}
          {found.map((finding, i) => (
            <Entry key={`${finding.path}:${finding.line}:${i}`} finding={finding} index={i + 1} />
          ))}
        </section>

        {report.forecast && report.forecast.length > 0 && (
          <section className="sheet-section sheet-break">
            <h2>
              Where this breaks next
              <span className="sheet-count">{report.forecast.length}</span>
            </h2>
            <p className="sheet-lede">
              Pressures read off the findings above rather than predicted in the abstract. Each
              names the mechanism and the evidence it was read from.
            </p>
            {report.forecast.map((pressure, i) => (
              <div key={i} className="sheet-pressure">
                <h3>
                  {pressure.mechanism}
                  <span className="sheet-band"> {pressure.band}</span>
                </h3>
                <p>{pressure.derivation}</p>
                <p className="sheet-derivation">
                  read from {pressure.independent_findings} independent finding
                  {pressure.independent_findings === 1 ? "" : "s"}
                  {pressure.evidence.length > 0 &&
                    `  ·  ${pressure.evidence
                      .map((e) => (e.line > 0 ? `${e.path}:${e.line}` : e.path))
                      .join("  ·  ")}`}
                </p>
              </div>
            ))}
          </section>
        )}

        <section className="sheet-section sheet-break">
          <h2>Coverage, and what this review did not do</h2>
          <p className="sheet-lede">
            A review that does not say what it skipped cannot be audited. This section is here so
            the absence of a finding can be read correctly.
          </p>
          <dl className="sheet-facts">
            <Fact
              label="modules read"
              value={report.coverage ? String(report.coverage.analysed.length) : "—"}
            />
            <Fact
              label="modules skipped"
              value={
                report.coverage ? String(Object.keys(report.coverage.skipped).length) : "—"
              }
            />
            <Fact label="duplicates merged" value={String(report.dropped?.length ?? 0)} />
            <Fact
              label="stopped because"
              value={report.coverage?.stopped_because || "the budget was not reached"}
              wide
            />
          </dl>
          {report.dropped && report.dropped.length > 0 && (
            <details className="sheet-dropped" open>
              <summary>Findings merged into another, with the reason</summary>
              <ul>
                {report.dropped.map((d, i) => (
                  <li key={i}>
                    <code>{d.path}</code> {d.symbol} — {d.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <footer className="sheet-foot">
          <p>
            Produced by Augury. Every claim above carries the evidence it was read from, and every
            measured claim carries the experiment that tested it. Findings are evidence for a
            qualified engineer, not a verdict: nothing here should be applied to a running system
            without one.
          </p>
          <p className="sheet-stamp">
            {title} · {day} · {report.modelId || "model not recorded"}
          </p>
        </footer>
      </article>
    </div>
  );
}

function Entry({ finding, index }: { finding: Finding; index: number }) {
  const verdict = verdictOf(finding);
  const claim = claimOf(finding);

  return (
    <div className="sheet-entry">
      <div className="sheet-entry-head">
        <span className={`sheet-sev sheet-sev-${finding.severity}`}>{finding.severity}</span>
        <span className="sheet-index">{String(index).padStart(2, "0")}</span>
        <span className="sheet-where">
          {finding.path}
          {finding.line > 0 && <span className="sheet-line">:{finding.line}</span>}
        </span>
        {finding.layer && <span className="sheet-layer">{finding.layer}</span>}
      </div>

      {finding.symbol && <h3 className="sheet-symbol">{finding.symbol}</h3>}
      <p className="sheet-mechanism">{finding.mechanism}</p>

      <div className="sheet-claim">
        <span className="sheet-claim-label">claim</span>
        <span className="sheet-claim-body">{claim}</span>
        <span className={`sheet-verdict sheet-verdict-${verdict}`}>{verdict}</span>
      </div>

      {finding.measurement?.detail && (
        <p className="sheet-measured">
          measured {finding.measurement.value ?? "nothing"} — {finding.measurement.detail}
        </p>
      )}

      {finding.remediation && (
        <div className="sheet-fix">
          <span className="sheet-fix-label">what to do</span>
          <p>{finding.remediation}</p>
        </div>
      )}
    </div>
  );
}

const Meta = ({ label, value }: { label: string; value: string }) => (
  <div>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
);

const Tally = ({ label, value, tone }: { label: string; value: number; tone: string }) => (
  <div className={`sheet-tally sheet-tally-${tone}`}>
    <span className="sheet-tally-value">{value}</span>
    <span className="sheet-tally-label">{label}</span>
  </div>
);

const Fact = ({ label, value, wide }: { label: string; value: string; wide?: boolean }) => (
  <div className={wide ? "sheet-fact-wide" : undefined}>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
);
