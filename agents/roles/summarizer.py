import json
import logging
from datetime import datetime

from groq import Groq
from agents.state import SwarmState, Claim
from memory.lance_store import LanceStore
from search.searcher import WebSearcher
from utils.confidence import compute_confidence
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.progress import emit_progress
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class SummarizerNode:
    def __init__(self, store: LanceStore):
        self.store    = store
        self.searcher = WebSearcher()
        self.client   = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        query     = state["query"]
        questions = (
            state.get("unanswered_questions")
            or state.get("research_questions", [])
        )

        y = datetime.now().year
        news_queries = [
            f"{q['text']} news {y - 1} {y}"
            for q in questions[:2]
        ]
        emit_progress(
            f"[Summarizer] News search: {len(news_queries)} queries (web fetch, can take minutes)..."
        )
        results = self.searcher.multi_search(news_queries, max_per_query=4)

        all_claims: list[Claim] = []

        for result in results[:6]:
            if not result.content.strip():
                continue

            groq_limiter.wait_if_needed(400)
            try:
                resp = self.client.chat.completions.create(
                    model=FAST_MODEL,
                    max_tokens=250,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Extract 2-3 key factual claims. "
                                'Return ONLY valid json: {"claims": ["claim text"]}'
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"{result.url}\n\n{result.content[:1200]}",
                        },
                    ],
                )
                data  = json.loads(resp.choices[0].message.content or "{}")
                texts = data.get("claims", [])
            except Exception as e:
                logger.warning(f"[Summarizer] LLM failed for {result.url}: {e}")
                continue

            confidence = compute_confidence(
                source_url=result.url,
                published_date=result.published_date,
            )

            for text in texts:
                if not text or not text.strip():
                    continue
                # ── BUG FIX: claim only if we have a real chunk_id ──
                # Never assign "ungrounded" — just skip if no evidence
                cid = LanceStore.stable_id("sum", result.chunk_id, text[:50])
                all_claims.append({
                    "claim_id":           cid,
                    "statement":          text.strip(),
                    "agent_id":           "summarizer",
                    "evidence_chunk_ids": [result.chunk_id],
                    "confidence":         confidence,
                    "consensus_state":    "pending",
                    "vote_rationale":     "",
                })

        log = f"[Summarizer] {len(all_claims)} grounded claims"
        logger.info(log)
        return {"claims": all_claims, "phase_log": [log]}
