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
}

/** One line of the raw feed, so a sceptical viewer can check the pretty view. */
export interface Step {
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
