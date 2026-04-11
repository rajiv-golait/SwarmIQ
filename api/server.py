"""FastAPI server with SSE streaming for SwarmIQ pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents.graph import run_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="SwarmIQ API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=2)


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/run")
async def run(request: RunRequest):
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must be non-empty")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _event_callback(entry: str):
        data = json.dumps({
            "entry": entry,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        loop.call_soon_threadsafe(queue.put_nowait, ("log", data))

    def _run_in_thread():
        try:
            result = run_pipeline(query, event_callback=_event_callback)
            loop.call_soon_threadsafe(
                queue.put_nowait, ("complete", json.dumps(result))
            )
        except Exception as e:
            logger.exception("run_pipeline failed")
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "error",
                    json.dumps({"message": f"{type(e).__name__}: {e}"}),
                ),
            )

    async def _stream() -> AsyncGenerator[dict, None]:
        _executor.submit(_run_in_thread)
        while True:
            event_type, data = await queue.get()
            yield {"event": event_type, "data": data}
            if event_type in ("complete", "error"):
                break

    return EventSourceResponse(_stream())
