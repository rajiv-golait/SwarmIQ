import { useEffect, useRef, useState } from 'react';
import { RunState } from '../../lib/types';
import { EmptyState } from './EmptyState';

interface ActivityViewProps {
  runState: RunState;
}

export function ActivityView({ runState }: ActivityViewProps) {
  const { log, result, error } = runState;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [log, autoScroll]);

  const handleScroll = () => {
    if (scrollRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
      setAutoScroll(isAtBottom);
    }
  };

  if (log.length === 0 && !error) {
    return <EmptyState message="No activity yet." />;
  }

  const formatTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="h-[600px] overflow-y-auto bg-[#0e121b] border border-[#1c2432] rounded-lg"
    >
      <div className="p-4 space-y-2">
        {/* Errors at the top */}
        {result?.errors && result.errors.length > 0 && (
          <div className="mb-4 space-y-2">
            {result.errors.map((err, index) => (
              <div
                key={`error-${index}`}
                className="flex gap-4 text-sm p-2 bg-[#ef4444]/10 rounded"
              >
                <span className="text-[#ef4444] font-mono whitespace-nowrap">
                  ERROR
                </span>
                <span className="text-[#ef4444] font-mono flex-1">
                  {err}
                </span>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="mb-4 flex gap-4 text-sm p-2 bg-[#ef4444]/10 rounded">
            <span className="text-[#ef4444] font-mono whitespace-nowrap">
              ERROR
            </span>
            <span className="text-[#ef4444] font-mono flex-1">
              {error}
            </span>
          </div>
        )}

        {/* Log entries in reverse chronological order */}
        {[...log].reverse().map((entry, index) => (
          <div
            key={index}
            className={`flex gap-4 text-sm p-2 rounded ${
              index % 2 === 0 ? 'bg-[#0a0b0f]' : 'bg-transparent'
            }`}
          >
            <span className="text-[#98a2b4] font-mono whitespace-nowrap">
              {formatTime(entry.timestamp)}
            </span>
            <span className="text-[#e7ecf7] font-mono flex-1">
              {entry.entry}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
