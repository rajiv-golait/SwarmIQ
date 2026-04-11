import { ExternalLink } from 'lucide-react';
import { CompleteEvent } from '../../lib/types';
import { EmptyState } from './EmptyState';

interface SourcesViewProps {
  result: CompleteEvent | null;
}

export function SourcesView({ result }: SourcesViewProps) {
  if (!result || result.sources.length === 0) {
    return <EmptyState message="No sources yet." />;
  }

  const extractDomain = (url: string) => {
    try {
      return new URL(url).hostname.replace('www.', '');
    } catch {
      return url;
    }
  };

  return (
    <div className="space-y-4">
      {result.sources.map((source, index) => (
        <div
          key={index}
          className="bg-[#0e121b] border border-[#1c2432] rounded-lg p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[#e7ecf7] font-medium mb-1">
                {extractDomain(source)}
              </div>
              <div className="text-sm text-[#98a2b4] break-all">
                {source}
              </div>
            </div>
            <a
              href={source}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-[#3c7bff] hover:text-[#2d6aee] transition-colors whitespace-nowrap"
            >
              Open
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        </div>
      ))}
    </div>
  );
}
