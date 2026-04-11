import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { CompleteEvent } from '../../lib/types';
import { EmptyState } from './EmptyState';

interface ClaimsViewProps {
  result: CompleteEvent | null;
}

export function ClaimsView({ result }: ClaimsViewProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!result) {
    return <EmptyState message="No claims yet." />;
  }

  const { claims_summary, negotiation_rounds, negotiation_log } = result;
  const total = claims_summary.total;

  const acceptedPercent = total > 0 ? (claims_summary.accepted / total) * 100 : 0;
  const rejectedPercent = total > 0 ? (claims_summary.rejected / total) * 100 : 0;
  const uncertainPercent = total > 0 ? (claims_summary.uncertain / total) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4">
          <div className="text-2xl font-bold text-[#e7ecf7] mb-1">
            {claims_summary.total}
          </div>
          <div className="text-sm text-[#98a2b4]">Total</div>
        </div>
        <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4">
          <div className="text-2xl font-bold text-[#22c55e] mb-1">
            {claims_summary.accepted}
          </div>
          <div className="text-sm text-[#98a2b4]">Accepted</div>
        </div>
        <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4">
          <div className="text-2xl font-bold text-[#ef4444] mb-1">
            {claims_summary.rejected}
          </div>
          <div className="text-sm text-[#98a2b4]">Rejected</div>
        </div>
        <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4">
          <div className="text-2xl font-bold text-[#f59e0b] mb-1">
            {claims_summary.uncertain}
          </div>
          <div className="text-sm text-[#98a2b4]">Uncertain</div>
        </div>
      </div>

      {/* Stacked bar */}
      <div>
        <div className="flex h-6 rounded-lg overflow-hidden">
          {acceptedPercent > 0 && (
            <div
              className="bg-[#22c55e]"
              style={{ width: `${acceptedPercent}%` }}
            />
          )}
          {rejectedPercent > 0 && (
            <div
              className="bg-[#ef4444]"
              style={{ width: `${rejectedPercent}%` }}
            />
          )}
          {uncertainPercent > 0 && (
            <div
              className="bg-[#f59e0b]"
              style={{ width: `${uncertainPercent}%` }}
            />
          )}
        </div>
        <div className="mt-3 text-sm text-[#98a2b4] text-center">
          Resolved across {negotiation_rounds} negotiation round{negotiation_rounds !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Negotiation detail */}
      {negotiation_log.length > 0 && (
        <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full flex items-center justify-between p-4 text-left hover:bg-[#1c2432]/30 transition-colors"
          >
            <span className="text-[#e7ecf7] font-medium">
              Negotiation detail
            </span>
            {isExpanded ? (
              <ChevronDown className="w-5 h-5 text-[#98a2b4]" />
            ) : (
              <ChevronRight className="w-5 h-5 text-[#98a2b4]" />
            )}
          </button>

          {isExpanded && (
            <div className="px-4 pb-4 space-y-3">
              {negotiation_log.map((round) => (
                <div
                  key={round.round_number}
                  className="text-sm text-[#98a2b4] py-2 border-t border-[#1c2432]"
                >
                  Round {round.round_number} — {Object.keys(round.outcomes).length} claims reviewed,{' '}
                  {round.unresolved.length} unresolved
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
