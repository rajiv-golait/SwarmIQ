import { StageName } from './types';

const STAGE_MAP: Record<string, StageName> = {
  Plan: 'Plan',
  LitReview: 'LitReview',
  Summarizer: 'Summarizer',
  GapDetect: 'GapDetect',
  Merge: 'Merge',
  Negotiate: 'Negotiate',
  Synthesize: 'Synthesize',
  Critic: 'Critic',
};

export function parsePhase(entry: string): {
  stage: StageName | null;
  message: string;
} {
  const match = entry.match(/^\[([^\]]+)\]\s*(.*)$/);

  if (!match) {
    return { stage: null, message: entry };
  }

  const [, prefix, message] = match;
  const stage = STAGE_MAP[prefix] || null;

  return { stage, message: message || entry };
}
