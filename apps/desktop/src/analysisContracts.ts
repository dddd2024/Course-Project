export type DecisionStatus = "ACCEPTED" | "REJECTED" | "UNCERTAIN";

export interface FindingReview {
  decision: DecisionStatus;
  correction: string;
}

export interface ByteLocation {
  inputId: string;
  offset: number;
  length: number;
}

export interface FindingScores {
  model?: number;
  evidence?: number;
  verification?: number;
}

export interface AnalysisFinding {
  findingId: string;
  claim: string;
  status: DecisionStatus;
  semanticType?: string;
  evidenceIds: string[];
  location?: ByteLocation;
  scores?: FindingScores;
}

export interface EvidenceRecord {
  evidenceId: string;
  sourceComponent: string;
  method: string;
  featureFamily: string;
  score?: number;
  observation?: Record<string, unknown>;
  parentEvidenceIds?: string[];
  independenceGroup?: string | null;
  sampleIds?: string[];
}

export type ArtifactType =
  | "evidence"
  | "packets"
  | "messages"
  | "alignment"
  | "statistics"
  | "behavior"
  | "restored"
  | "schema"
  | "report";

export interface ArtifactRef {
  artifactId: string;
  type: ArtifactType;
  format: "json" | "jsonl" | "parquet" | "csv" | "text" | "binary" | "ksy";
  ref: string;
  count?: number;
  metadata?: Record<string, unknown>;
}

export interface AnalysisResult {
  protocolVersion: 1;
  taskId: string;
  status: "COMPLETED" | "FAILED" | "CANCELLED" | "PARTIAL";
  inputId?: string;
  resultRef?: string;
  findings: AnalysisFinding[];
  evidence?: EvidenceRecord[];
  artifacts?: ArtifactRef[];
  metrics?: Record<string, unknown>;
  limitations?: string[];
}

export type AnalysisViewName =
  | "findings"
  | "evidence"
  | "artifacts"
  | "packets"
  | "alignment"
  | "statistics"
  | "behavior"
  | "restoration";

export function scoreLabel(value: number | undefined) {
  return value === undefined ? "—" : value.toFixed(2);
}

