export type StageName =
  | 'Plan'
  | 'LitReview'
  | 'Summarizer'
  | 'GapDetect'
  | 'Merge'
  | 'Negotiate'
  | 'Synthesize'
  | 'Critic';

export interface LogEvent {
  entry: string;
  timestamp: string;
}

export interface NegotiationRound {
  round_number: number;
  claims_reviewed: string[];
  outcomes: Record<string, string>;
  unresolved: string[];
}

export interface ClaimsSummary {
  total: number;
  accepted: number;
  rejected: number;
  uncertain: number;
}

export interface CompleteEvent {
  query: string;
  run_id: string;
  report: string;
  sources: string[];
  word_count: number;
  coherence_score: number;
  claims_summary: ClaimsSummary;
  negotiation_rounds: number;
  negotiation_log: NegotiationRound[];
  phase_log: string[];
  errors: string[];
  visualization?: Record<string, unknown>;
}

export interface ErrorEvent {
  message: string;
}

export type PhaseStatus = 'pending' | 'active' | 'done' | 'error';

export interface PhaseState {
  status: PhaseStatus;
  message: string;
}

export type RunStatus = 'idle' | 'running' | 'done' | 'error';

export interface RunState {
  status: RunStatus;
  phases: Record<StageName, PhaseState>;
  log: LogEvent[];
  result: CompleteEvent | null;
  error: string | null;
}

/**
 * Detect if the critic was a stub by checking the phase_log.
 * Returns true if the critic actually ran (not a stub).
 */
export function isCriticReal(phaseLog: string[]): boolean {
  return !phaseLog.some((entry) => entry.includes('[Critic] Stub'));
}

/**
 * Format the coherence score for display, with stub/suspicious detection.
 */
export function formatScoreDisplay(
  score: number,
  phaseLog: string[],
  wordCount: number
): { text: string; color: string } {
  if (!isCriticReal(phaseLog)) {
    return { text: 'N/A (stub)', color: 'text-[#98a2b4]' };
  }
  if (score >= 1.0 - 1e-9 && wordCount > 200) {
    return { text: `${score.toFixed(2)} ⚠️`, color: 'text-[#f59e0b]' };
  }
  if (score >= 0.75) {
    return { text: score.toFixed(2), color: 'text-[#22c55e]' };
  }
  if (score >= 0.5) {
    return { text: score.toFixed(2), color: 'text-[#f59e0b]' };
  }
  return { text: score.toFixed(2), color: 'text-[#ef4444]' };
}
