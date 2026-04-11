Good call. Gradio gets you to "it works" but it caps the ceiling on how the project looks and feels, and for a portfolio piece that ceiling matters. Here's how I'd restructure the day to make this work without blowing the 8-hour budget.
The shift in plan
Drop Gradio entirely from Kiro's task list. Replace T8 with a FastAPI wrapper task — about 30 minutes of work for Kiro, it just exposes run_pipeline() over HTTP/SSE. Then Lovable builds a real React frontend in parallel against that exact contract. Because the contract is small and frozen, the two builds don't block each other.
You should think of this as adding one new file to the backend plan (api/server.py) and removing one (ui/gradio_app.py). Everything else in the original plan stays identical — same run_pipeline(), same SwarmState, same return dict shape.
Revised time budget
Backend (Kiro):                   Frontend (Lovable):
H0:00–4:30  T1–T5 unchanged       (you're not touching Lovable yet)
H4:30–5:30  T6 first run          ↓
H5:30–6:30  T7 regression runs    ↓
H6:30–7:00  T8 NEW: FastAPI       H6:30–7:30 Lovable build + iterate
            wrapper (30 min)      
H7:00–7:30  T9 wire frontend to   H7:30–8:00 final polish, both halves
            backend, smoke test   
H7:30–8:00  Buffer + commit
The key insight: Lovable can build the entire UI against a frozen JSON contract without the backend running at all. You point it at localhost:8000 and as soon as Kiro finishes T8, the connection just works. No iteration needed if the contract is exact.
Step 1 — Tell Kiro about the new T8
Send this to Kiro mid-build (after T6 ideally, before it starts T8):

Plan amendment: replace T8 entirely.
We're dropping Gradio. Instead, add a thin FastAPI wrapper that exposes run_pipeline() over HTTP. New T8:
T8: FastAPI wrapper (30 min budget, hard cap)
8.1 Add fastapi, uvicorn[standard], sse-starlette to requirements.txt
8.2 Create api/__init__.py and api/server.py with:

POST /api/run — accepts {"query": "string"}, returns SSE stream. Wrap run_pipeline() in a thread, push events to an asyncio.Queue via the event_callback parameter that already exists in the plan's run_pipeline() signature. Emit two SSE event types:

event: log with data: {"entry": "string", "timestamp": "ISO8601"} for each phase_log entry as it streams
event: complete with data: <full run_pipeline return dict> when done
event: error with data: {"message": "string"} on exception


GET /api/health — returns {"status": "ok"}
CORS middleware allowing http://localhost:5173 and http://localhost:8080 (Vite + Lovable preview ports)

8.3 Update app.py to launch uvicorn instead of Gradio: uvicorn.run("api.server:app", host="0.0.0.0", port=8000)
8.4 Update main.py CLI to call run_pipeline() directly (unchanged from plan, just confirm the legacy Supervisor reference is gone)
8.5 Smoke test: curl -N -X POST http://localhost:8000/api/run -H "Content-Type: application/json" -d '{"query":"What is LangGraph?"}' — should stream log events then a complete event
Do NOT add /api/runs list, /api/runs/:id, or export endpoints. Single endpoint, single purpose. The plan's run_pipeline() return dict is the frozen contract — do not rename or restructure any field.

That's the only change to Kiro's plan. Everything else stays.
Step 2 — Lovable prompt (rewritten against the actual contract)
Paste this into Lovable:

Build the frontend for SwarmIQ, a multi-agent research assistant. The Python backend exposes one streaming endpoint that runs a research pipeline and returns a cited markdown report. Your job is the frontend only — do not add a Node server, do not add a database, do not add authentication, do not invent endpoints.
Critical rules

No dummy data anywhere. No placeholder reports, no fake sources, no lorem ipsum, no example queries hardcoded into state, no mock claims, no sample past runs. Empty states must say "No run yet" or similar — they must not be pre-filled with sample content. The only acceptable hardcoded text is UI chrome (button labels, headings, placeholder text inside empty input fields).
No mock API layer that returns fake data. Build a real API client (src/lib/api.ts) that hits the actual endpoint below. If the backend isn't running, the UI shows real connection errors — it does not fall back to fake data.
No routing library. Single screen, no React Router.
Match the API contract exactly. The field names below are frozen by the backend. Do not rename, restructure, or add fields the backend doesn't send.

API contract (this is the entire backend surface)
Base URL configurable via VITE_API_BASE_URL, default http://localhost:8000.
POST /api/run — Server-Sent Events stream
Request:
json{ "query": "string" }
Response is text/event-stream. Three event types:
event: log
data: {"entry": "string", "timestamp": "ISO8601"}

event: complete
data: {
  "query": "string",
  "run_id": "string",
  "report": "markdown string",
  "sources": ["url1", "url2", ...],
  "word_count": 0,
  "coherence_score": 0.0,
  "claims_summary": {
    "total": 0,
    "accepted": 0,
    "rejected": 0,
    "uncertain": 0
  },
  "negotiation_rounds": 0,
  "negotiation_log": [
    {
      "round_number": 1,
      "claims_reviewed": ["claim_id"],
      "outcomes": {"claim_id": "accepted"},
      "unresolved": []
    }
  ],
  "phase_log": ["string", ...],
  "errors": ["string", ...]
}

event: error
data: {"message": "string"}
The phase_log entries are strings that look like "[Plan] 4 questions generated for: query", "[LitReview] Q1: 5 sources, 12 claims", "[Negotiate] 8 accepted, 2 rejected, 1 uncertain (2 rounds)", "[Synthesize] 743 words, 9 sources". Parse the bracketed prefix to identify which pipeline stage emitted each entry — you'll use this for the live progress visualization.
GET /api/health
Returns {"status": "ok"}. Use this on mount to show a connection indicator.
That is the entire backend. No /api/runs list endpoint. No history. No export endpoint — the report is markdown so the user can copy it from the UI or you can offer a client-side "Download as .md" button that creates a Blob from the report string.
Layout
Single screen, two columns. No top nav, no sidebar nav, no footer.
Left column (≈32% width, min 340px):

Title "SwarmIQ" with one-line subtitle "Multi-agent research assistant"
Tiny connection status pill (green dot "Connected" / red dot "Backend offline") that polls /api/health once on mount
Large autosize textarea for the query (5–6 rows)
Primary "Run Research" button (disabled while a run is in flight or backend is offline)
"Cancel" button visible only during a run, aborts the EventSource
Pipeline status panel below the buttons — see next section

Right column (≈68% width):

Tabs: Report | Sources | Claims | Activity
Default empty state: centered "Enter a query and click Run Research to begin." No sample content.

Pipeline visualization (the centerpiece)
This is what makes the UI feel alive. As log events stream in, parse the bracketed prefix and update a vertical flow diagram with these stages:

Plan ([Plan])
Literature Review ([LitReview]) and Summarize ([Summarizer]) — these run in parallel in the backend, draw them side by side at the same vertical level
Detect Gaps ([GapDetect])
Negotiate ([Negotiate])
Synthesize ([Synthesize])
Critique ([Critic])

Each stage is a small card with: a status icon (pending gray dot, active animated pulse, done green check, error red X), the stage name, and the most recent log message for that stage as a one-line subtitle. Subtle connecting lines between stages. The two parallel cards rejoin visually at Detect Gaps.
A stage is "active" the moment its first log event arrives, and "done" when a later stage's log event arrives or when complete fires. If error fires, mark the currently active stage red.
When complete arrives, all stages show green checks and the panel shows a compact summary line: "Completed · {word_count} words · {sources.length} sources · score {coherence_score.toFixed(2)}".
Tabs (right column)
Report tab

Markdown rendered with react-markdown + remark-gfm and proper typography (serif body font, generous line height)
Inline [1] [2] markers rendered as superscript links that scroll-anchor to entries in the report's References section
Top bar of the tab: word count · coherence score badge (green ≥0.75, amber 0.5–0.75, red <0.5) · source count · "Download .md" button (client-side Blob, no backend call)
Empty: "No report yet."

Sources tab

List from sources[]. Each row: extract domain client-side as the header, full URL below, "Open" link (new tab)
Empty: "No sources yet."

Claims tab

Four stat cards from claims_summary: Total / Accepted / Rejected / Uncertain
Below: a horizontal stacked bar showing the accepted/rejected/uncertain proportions (colored segments, no chart library — pure CSS flexbox with widths from the percentages)
Below that: "Resolved across {negotiation_rounds} negotiation round(s)"
Then a collapsible section "Negotiation detail" rendering each entry from negotiation_log[] as: "Round {round_number} — {Object.keys(outcomes).length} claims reviewed, {unresolved.length} unresolved"
Empty: "No claims yet."

Activity tab

Reverse-chronological list of every log entry received during the run, plus any errors[] from the complete event at the top in red
Monospace font, subtle alternating row backgrounds, timestamps on the left
Auto-scrolls to bottom while a run is in flight; pauses auto-scroll if the user scrolls up
Empty: "No activity yet."

Visual design

Dark theme only. Background #0a0b0f, panels #0e121b, borders #1c2432, text #e7ecf7, muted #98a2b4, accent blue #3c7bff, success #22c55e, warning #f59e0b, error #ef4444
Inter for UI, Georgia (or similar serif) for the rendered report body so it reads like a paper
16–20px panel padding, 12–18px rounded corners, subtle inset highlight on panel tops
lucide-react for icons
Tailwind for everything. No CSS-in-JS, no styled-components, no shadcn theme overrides

State management
Plain React useReducer. One reducer for run state:
tstype RunState = {
  status: 'idle' | 'running' | 'done' | 'error'
  phases: Record<StageName, {status: 'pending'|'active'|'done'|'error', message: string}>
  log: Array<{entry: string, timestamp: string}>
  result: CompleteEvent | null
  error: string | null
}
Actions: RUN_STARTED, LOG_RECEIVED (parses prefix, updates phase + appends to log), COMPLETE_RECEIVED, ERROR_RECEIVED, RUN_RESET, RUN_CANCELED. No Redux, no Zustand, no React Query.
File structure
src/
├── App.tsx
├── main.tsx
├── components/
│   ├── QueryPanel.tsx
│   ├── PipelineStatus.tsx
│   ├── PhaseCard.tsx
│   ├── ConnectionPill.tsx
│   ├── ResultTabs.tsx
│   ├── ReportView.tsx
│   ├── SourcesView.tsx
│   ├── ClaimsView.tsx
│   ├── ActivityView.tsx
│   └── EmptyState.tsx
├── lib/
│   ├── api.ts          ← real fetch + EventSource wrapper, no mocks
│   ├── parsePhase.ts   ← extracts stage from "[Plan] ..." prefix
│   └── types.ts        ← TS types matching the API contract above verbatim
├── state/
│   └── runReducer.ts
└── index.css
Things to explicitly NOT do

No "Try a sample query" button that fills fake input
No fake past runs list (the backend has no history endpoint, so there's no UI element for history at all)
No charts using fake data
No settings page, theme toggle, or login
No toast library — only show inline error states
No Framer Motion. CSS transitions only (opacity, small scale on phase activate)
No fields in the UI that aren't in the API contract above. If you find yourself wanting to display something the backend doesn't send, stop and remove it.

Acceptance test
I should be able to grep src/ for lorem, ipsum, sample, mock, dummy, fake, placeholder report, example query and find zero matches in any data field (matches in input placeholder props are fine). Then npm run dev, type a query, click Run, and see a real POST /api/run request fire in devtools — failing with a connection error if the backend is offline, or streaming events if it's up.
Build it.

That's the whole revised plan. One amendment to Kiro's tasks (the FastAPI swap), one Lovable prompt that matches the contract exactly. The two builds run in parallel from H6:30 onward and converge cleanly at H7:30 for the integration smoke test.Opus 4.6Extended