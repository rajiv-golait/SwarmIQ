import { useState } from 'react';
import { RunState } from '../../lib/types';
import { ReportView } from './ReportView';
import { SourcesView } from './SourcesView';
import { ClaimsView } from './ClaimsView';
import { ActivityView } from './ActivityView';
import { EmptyState } from './EmptyState';

interface ResultTabsProps {
  runState: RunState;
}

type TabName = 'report' | 'sources' | 'claims' | 'activity';

export function ResultTabs({ runState }: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabName>('report');

  const tabs: { id: TabName; label: string }[] = [
    { id: 'report', label: 'Report' },
    { id: 'sources', label: 'Sources' },
    { id: 'claims', label: 'Claims' },
    { id: 'activity', label: 'Activity' },
  ];

  const hasData = runState.result || runState.log.length > 0;

  return (
    <div>
      {/* Tab headers */}
      <div className="flex gap-1 border-b border-[#1c2432] mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-6 py-3 font-medium transition-colors relative ${
              activeTab === tab.id
                ? 'text-[#e7ecf7]'
                : 'text-[#98a2b4] hover:text-[#e7ecf7]'
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#3c7bff]" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {!hasData ? (
        <EmptyState message="Enter a query and click Run Research to begin." />
      ) : (
        <>
          {activeTab === 'report' && <ReportView result={runState.result} />}
          {activeTab === 'sources' && <SourcesView result={runState.result} />}
          {activeTab === 'claims' && <ClaimsView result={runState.result} />}
          {activeTab === 'activity' && <ActivityView runState={runState} />}
        </>
      )}
    </div>
  );
}
