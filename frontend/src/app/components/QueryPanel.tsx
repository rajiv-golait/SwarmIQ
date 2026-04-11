import { useState } from 'react';
import { Play, X } from 'lucide-react';

interface QueryPanelProps {
  onRun: (query: string) => void;
  onCancel: () => void;
  isRunning: boolean;
  isConnected: boolean;
}

export function QueryPanel({
  onRun,
  onCancel,
  isRunning,
  isConnected,
}: QueryPanelProps) {
  const [query, setQuery] = useState('');

  const handleSubmit = () => {
    if (query.trim()) {
      onRun(query.trim());
    }
  };

  return (
    <div>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Enter your research question..."
        className="w-full h-32 bg-[#0e121b] border border-[#1c2432] rounded-lg p-4 text-[#e7ecf7] placeholder:text-[#98a2b4] resize-none focus:outline-none focus:ring-2 focus:ring-[#3c7bff]"
        disabled={isRunning}
      />

      <div className="flex gap-3 mt-4">
        <button
          onClick={handleSubmit}
          disabled={isRunning || !isConnected || !query.trim()}
          className="flex-1 flex items-center justify-center gap-2 bg-[#3c7bff] text-white py-3 px-6 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[#2d6aee] transition-colors"
        >
          <Play className="w-5 h-5" />
          Run Research
        </button>

        {isRunning && (
          <button
            onClick={onCancel}
            className="flex items-center justify-center gap-2 bg-[#ef4444] text-white py-3 px-6 rounded-lg font-medium hover:bg-[#dc2626] transition-colors"
          >
            <X className="w-5 h-5" />
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
