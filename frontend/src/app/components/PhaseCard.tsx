import { CheckCircle2, Circle, XCircle } from 'lucide-react';
import { PhaseStatus } from '../../lib/types';

interface PhaseCardProps {
  name: string;
  status: PhaseStatus;
  message: string;
}

export function PhaseCard({ name, status, message }: PhaseCardProps) {
  const getIcon = () => {
    switch (status) {
      case 'pending':
        return <Circle className="w-5 h-5 text-[#98a2b4]" />;
      case 'active':
        return (
          <div className="w-5 h-5 rounded-full bg-[#3c7bff] animate-pulse" />
        );
      case 'done':
        return <CheckCircle2 className="w-5 h-5 text-[#22c55e]" />;
      case 'error':
        return <XCircle className="w-5 h-5 text-[#ef4444]" />;
    }
  };

  return (
    <div className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4">
      <div className="flex items-start gap-3">
        {getIcon()}
        <div className="flex-1 min-w-0">
          <div className="text-[#e7ecf7] font-medium mb-1">{name}</div>
          {message && (
            <div className="text-sm text-[#98a2b4] truncate">{message}</div>
          )}
        </div>
      </div>
    </div>
  );
}
