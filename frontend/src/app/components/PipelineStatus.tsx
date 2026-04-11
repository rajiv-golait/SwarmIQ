import { PhaseCard } from './PhaseCard';
import { RunState, formatScoreDisplay } from '../../lib/types';

interface PipelineStatusProps {
  runState: RunState;
}

export function PipelineStatus({ runState }: PipelineStatusProps) {
  const { phases, result, status } = runState;

  return (
    <div className="mt-6">
      <h3 className="text-[#e7ecf7] font-medium mb-4">Pipeline Status</h3>

      <div className="space-y-3">
        {/* Plan */}
        <PhaseCard
          name="Plan"
          status={phases.Plan.status}
          message={phases.Plan.message}
        />

        {/* Parallel stages: LitReview and Summarizer */}
        <div className="grid grid-cols-2 gap-3">
          <PhaseCard
            name="Literature Review"
            status={phases.LitReview.status}
            message={phases.LitReview.message}
          />
          <PhaseCard
            name="Summarize"
            status={phases.Summarizer.status}
            message={phases.Summarizer.message}
          />
        </div>

        {/* Gap Detection */}
        <PhaseCard
          name="Detect Gaps"
          status={phases.GapDetect.status}
          message={phases.GapDetect.message}
        />

        {/* Merge & Validate */}
        <PhaseCard
          name="Merge & Validate"
          status={phases.Merge.status}
          message={phases.Merge.message}
        />

        {/* Negotiate */}
        <PhaseCard
          name="Negotiate"
          status={phases.Negotiate.status}
          message={phases.Negotiate.message}
        />

        {/* Synthesize */}
        <PhaseCard
          name="Synthesize"
          status={phases.Synthesize.status}
          message={phases.Synthesize.message}
        />

        {/* Critique */}
        <PhaseCard
          name="Critique"
          status={phases.Critic.status}
          message={phases.Critic.message}
        />
      </div>

      {/* Summary when complete */}
      {status === 'done' && result && (() => {
        const scoreDisplay = formatScoreDisplay(
          result.coherence_score,
          result.phase_log,
          result.word_count
        );
        return (
          <div className="mt-4 p-4 bg-[#0e121b] border border-[#1c2432] rounded-lg text-sm text-[#98a2b4]">
            Completed · {result.word_count} words · {result.sources.length} sources
            · score <span className={scoreDisplay.color}>{scoreDisplay.text}</span>
          </div>
        );
      })()}
    </div>
  );
}
