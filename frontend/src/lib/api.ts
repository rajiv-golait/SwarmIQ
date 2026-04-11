import { LogEvent, CompleteEvent, ErrorEvent } from './types';

/**
 * Base URL for SwarmIQ API.
 * - Dev (default): empty → same-origin `/api/...` via Vite proxy (see vite.config.ts).
 * - Production: set `VITE_API_BASE_URL=https://your-api.example.com` at build time.
 */
const rawBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE_URL =
  typeof rawBase === 'string' && rawBase.trim() !== ''
    ? rawBase.replace(/\/$/, '')
    : '';

export interface RunCallbacks {
  onLog: (log: LogEvent) => void;
  onComplete: (result: CompleteEvent) => void;
  onError: (error: ErrorEvent) => void;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    if (!response.ok) return false;
    const data = await response.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}

export function runResearch(
  query: string,
  callbacks: RunCallbacks
): () => void {
  const controller = new AbortController();
  let isCanceled = false;

  (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (!response.ok) {
        callbacks.onError({ message: `HTTP ${response.status}` });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError({ message: 'No response body' });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (!isCanceled) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim() || line.startsWith(':')) continue;

          if (line.startsWith('event: ')) {
            currentEvent = line.substring(7).trim();
          } else if (line.startsWith('data: ')) {
            const data = line.substring(6);
            try {
              const parsed = JSON.parse(data);

              if (currentEvent === 'log') {
                callbacks.onLog(parsed as LogEvent);
              } else if (currentEvent === 'complete') {
                callbacks.onComplete(parsed as CompleteEvent);
              } else if (currentEvent === 'error') {
                callbacks.onError(parsed as ErrorEvent);
              }

              currentEvent = '';
            } catch (error) {
              console.error('Failed to parse SSE data:', error);
            }
          }
        }
      }
    } catch (error) {
      if (!isCanceled) {
        callbacks.onError({
          message: error instanceof Error ? error.message : 'Connection error',
        });
      }
    }
  })();

  return () => {
    isCanceled = true;
    controller.abort();
  };
}
