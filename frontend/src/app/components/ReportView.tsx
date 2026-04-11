import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Download } from 'lucide-react';
import { CompleteEvent, formatScoreDisplay } from '../../lib/types';
import { EmptyState } from './EmptyState';

interface ReportViewProps {
  result: CompleteEvent | null;
}

export function ReportView({ result }: ReportViewProps) {
  if (!result) {
    return <EmptyState message="No report yet." />;
  }

  const downloadMarkdown = () => {
    const blob = new Blob([result.report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `swarmiq-${result.run_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const scoreDisplay = formatScoreDisplay(
    result.coherence_score,
    result.phase_log,
    result.word_count
  );

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-4 mb-6 pb-4 border-b border-[#1c2432]">
        <span className="text-sm text-[#98a2b4]">
          {result.word_count} words
        </span>
        <span className="text-sm text-[#98a2b4]">·</span>
        <span className={`text-sm font-medium ${scoreDisplay.color}`}>
          Score {scoreDisplay.text}
        </span>
        <span className="text-sm text-[#98a2b4]">·</span>
        <span className="text-sm text-[#98a2b4]">
          {result.sources.length} sources
        </span>
        <button
          onClick={downloadMarkdown}
          className="ml-auto flex items-center gap-2 text-sm text-[#3c7bff] hover:text-[#2d6aee] transition-colors"
        >
          <Download className="w-4 h-4" />
          Download .md
        </button>
      </div>

      {/* Markdown content */}
      <div className="prose prose-invert max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          className="text-[#e7ecf7]"
          components={{
            h1: ({ children }) => (
              <h1 className="text-3xl font-serif mb-4 text-[#e7ecf7]">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-2xl font-serif mt-8 mb-3 text-[#e7ecf7]">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-xl font-serif mt-6 mb-2 text-[#e7ecf7]">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="font-serif leading-relaxed mb-4 text-[#e7ecf7]">
                {children}
              </p>
            ),
            ul: ({ children }) => (
              <ul className="list-disc list-inside mb-4 space-y-2 text-[#e7ecf7]">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal list-inside mb-4 space-y-2 text-[#e7ecf7]">
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="font-serif leading-relaxed text-[#e7ecf7]">
                {children}
              </li>
            ),
            a: ({ children, href }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#3c7bff] hover:underline"
              >
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="bg-[#1c2432] px-1 py-0.5 rounded text-sm font-mono text-[#e7ecf7]">
                {children}
              </code>
            ),
            pre: ({ children }) => (
              <pre className="bg-[#1c2432] p-4 rounded-lg overflow-x-auto mb-4">
                {children}
              </pre>
            ),
          }}
        >
          {result.report}
        </ReactMarkdown>
      </div>
    </div>
  );
}
