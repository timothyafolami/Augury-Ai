/** The event vocabulary the server actually emits.
 *
 * Deliberately close to the shape of the pipeline rather than to the shape of
 * the screen: every one of these is a step the reviewer takes anyway and
 * writes to its trajectory. When the pipeline stops emitting, the interface
 * stops moving, which is the honest behaviour.
 */

export type StageKey = "survey" | "map" | "schema" | "specialists" | "report";
export type StageState = "waiting" | "running" | "done";

export interface Stage {
  key: StageKey;
  title: string;
  detail: string;
  usesModel: boolean;
}

export interface Service {
  name: string;
  sourceRoot: string;
  command: string;
  ports: string[];
  isEntrypoint: boolean;
}

export interface Backing {
  name: string;
  kind: string;
  image: string;
}

export interface Module {
  path: string;
  loc: number;
  depth: number | null;
  fanIn: number;
  signals: string[];
}

export interface Discovery {
  root: string;
  name: string;
  services: Service[];
  backing: Backing[];
  modules: Module[];
  languages: Record<string, number>;
  unreachable: string[];
}

export interface Prediction {
  metric: string;
  comparator: string;
  value: number;
  upper: number | null;
  unit: string;
  condition: string;
}

export interface Finding {
  path: string;
  line: number;
  layer: string;
  symbol: string;
  severity: "high" | "medium" | "low";
  mechanism: string;
  remediation: string;
  rule: string;
  prediction: Prediction | null;
  measurement: { value: number | null; detail: string } | null;
}

export interface Report {
  name: string;
  usd: number;
  seconds: number;
  modelId: string;
  coverage: { analysed: string[]; skipped: Record<string, string>; stopped_because: string } | null;
  findings: Finding[];
  dropped: { symbol: string; path: string; reason: string }[];
  schema: Finding[];
  dependencies: Finding[];
  engineering?: EngineeringCoverage;
  deployment?: Finding[];
  synthesis?: Observation[];
  architecture?: Architecture;
  reading?: Record<string, string[]>;
  forecast?: Pressure[];
}

/** One line of the raw feed, so a sceptical viewer can check the pretty view. */
export interface Step {
  /** The typed vocabulary: "review.started", "research.finished" and so on. */
  event?: string;
  seq?: number;
  offsetMs?: number;
  data?: Record<string, unknown>;
  kind?: string;
  agent?: string;
  action?: string;
  stage?: StageKey;
  state?: StageState;
  path?: string;
  findings?: number;
  read?: number;
  total?: number;
  usd?: number;
  depth?: number | null;
  detail?: Record<string, unknown> | string;
  provider?: string;
  model?: string;
  report?: Report;
  model_call?: boolean;
  at?: number;
}

/** One specialist's share of the concern it owns.
 *
 * `basis` is load-bearing. "routed" means the caller supplied which
 * specialists were actually asked about which module. "signalled" is an upper
 * bound: a module the scheduler read counts as read for every layer its
 * signals route to, and triage narrows those further than this can see. A bar
 * drawn without saying which it is looks exactly like a measurement.
 */
export interface LayerCoverage {
  layer: string;
  title: string;
  occurrences: string[];
  reviewed: string[];
  share: number | null;
  findings: number;
  basis: "routed" | "signalled";
}

export interface EngineeringCoverage {
  layers: LayerCoverage[];
  modules: number;
  unattributed_findings: number;
}

export interface Evidence {
  path: string;
  line: number;
  symbol: string;
  layer: string;
  trigger: string;
}

/** A mechanism the review reached from several directions.
 *
 * There is no probability here on purpose. `independent_findings` counts
 * places, `band` is a position in a sequence rather than a magnitude, and
 * `derivation` is the sentence that has to travel with the bar.
 */
export interface Pressure {
  mechanism: string;
  evidence: Evidence[];
  rule: string;
  independent_findings: number;
  band: "isolated" | "repeated" | "systemic";
  derivation: string;
}

/** The service drawn from what was read.
 *
 * `basis` travels with it because a diagram reads as authoritative unless
 * something arriving alongside says where it came from.
 */
export interface ArchNode {
  id: string;
  label: string;
  kind: "service" | "code" | "store";
  detail: string;
  ceiling: string;
  modules: number;
  findings: number;
  depth: number | null;
}

export interface ArchEdge {
  source: string;
  target: string;
  why: string;
}

export interface Architecture {
  nodes: ArchNode[];
  edges: ArchEdge[];
  basis: string;
}

/** One citation inside a senior observation. */
export interface Citation {
  path: string;
  line: number;
  symbol: string;
  layer: string;
}

/** Something no single specialist could have said.
 *
 * Two citations are a connection only when two different specialists reported
 * them, which the model enforces rather than the renderer.
 */
export interface Observation {
  mechanism: string;
  consequence: string;
  citations: Citation[];
}
