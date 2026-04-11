import { useEffect, useReducer, useRef, useState } from 'react';
import { ConnectionPill } from './components/ConnectionPill';
import { QueryPanel } from './components/QueryPanel';
import { PipelineStatus } from './components/PipelineStatus';
import { ResultTabs } from './components/ResultTabs';
import { runReducer, initialState } from '../state/runReducer';
import { checkHealth, runResearch } from '../lib/api';

export default function App() {
  const [runState, dispatch] = useReducer(runReducer, initialState);
  const [isConnected, setIsConnected] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    checkHealth().then(setIsConnected);
  }, []);

  const handleRun = (query: string) => {
    dispatch({ type: 'RUN_STARTED' });

    const cancel = runResearch(query, {
      onLog: (log) => {
        dispatch({ type: 'LOG_RECEIVED', payload: log });
      },
      onComplete: (result) => {
        dispatch({ type: 'COMPLETE_RECEIVED', payload: result });
        cancelRef.current = null;
      },
      onError: (error) => {
        dispatch({ type: 'ERROR_RECEIVED', payload: error.message });
        cancelRef.current = null;
      },
    });

    cancelRef.current = cancel;
  };

  const handleCancel = () => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    dispatch({ type: 'RUN_CANCELED' });
  };

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-[#e7ecf7]">
      <div className="flex h-screen">
        {/* Left column - Query and Pipeline */}
        <div className="w-[32%] min-w-[340px] border-r border-[#1c2432] p-6 overflow-y-auto">
          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-1">SwarmIQ</h1>
            <p className="text-sm text-[#98a2b4]">
              Multi-agent research assistant
            </p>
          </div>

          <ConnectionPill isConnected={isConnected} />

          <QueryPanel
            onRun={handleRun}
            onCancel={handleCancel}
            isRunning={runState.status === 'running'}
            isConnected={isConnected}
          />

          <PipelineStatus runState={runState} />
        </div>

        {/* Right column - Results */}
        <div className="flex-1 p-6 overflow-y-auto">
          <ResultTabs runState={runState} />
        </div>
      </div>
    </div>
  );
}
