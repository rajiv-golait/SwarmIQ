import logging
from agents.state import SwarmState, EvidenceChunk, Claim
from memory.lance_store import LanceStore
from memory.models import rerank
from search.searcher import WebSearcher
from utils.confidence import compute_confidence
from utils.progress import emit_progress

logger = logging.getLogger(__name__)


class LiteratureReviewNode:
    def __init__(self, store: LanceStore):
        self.store    = store
        self.searcher = WebSearcher()

    def run(self, state: SwarmState) -> dict:
        run_id    = state["run_id"]
        questions = (
            state.get("unanswered_questions")
            or state.get("research_questions", [])
        )

        if not questions:
            return {"phase_log": ["[LitReview] No questions"]}

        all_chunks: list[EvidenceChunk] = []
        all_claims: list[Claim]         = []
        logs: list[str]                 = []

        for question in questions[:3]:
            q_id      = question["question_id"]
            q_queries = question.get("search_queries", [question["text"]])

            emit_progress(
                f"[LitReview] Q {q_id}: {len(q_queries)} search queries "
                f"(this step is slow: many web fetches)..."
            )
            results = self.searcher.multi_search(q_queries, max_per_query=4)
            emit_progress(
                f"[LitReview] Q {q_id}: retrieved {len(results)} pages, building claims..."
            )

            for result in results:
                confidence = compute_confidence(
                    source_url=result.url,
                    published_date=result.published_date,
                )
                chunk: EvidenceChunk = {
                    "chunk_id":       result.chunk_id,
                    "content":        result.content,
                    "source_url":     result.url,
                    "source_domain":  result.url.split("/")[2]
                                      if "//" in result.url else "",
                    "published_date": result.published_date,
                    "agent_id":       "literature_reviewer",
                    "confidence":     confidence,
                    "question_id":    q_id,
                }
                all_chunks.append(chunk)

                for sentence in self._extract_sentences(result.content):
                    cid = LanceStore.stable_id("lit", result.chunk_id, sentence[:50])
                    all_claims.append({
                        "claim_id":           cid,
                        "statement":          sentence,
                        "agent_id":           "literature_reviewer",
                        "evidence_chunk_ids": [result.chunk_id],
                        "confidence":         confidence,
                        "consensus_state":    "pending",
                        "vote_rationale":     "",
                    })

            logs.append(
                f"[LitReview] Q{q_id}: {len(results)} sources, "
                f"{len(all_claims)} claims"
            )

        if all_chunks:
            self.store.add_documents(
                documents=[c["content"] for c in all_chunks],
                metadatas=[{
                    **c,
                    "run_id": run_id,
                    "phase":  "execution",
                } for c in all_chunks],
                ids=[c["chunk_id"] for c in all_chunks],
            )

        return {
            "evidence_chunks": all_chunks,
            "claims":          all_claims,
            "phase_log":       logs,
        }

    def _extract_sentences(self, content: str) -> list[str]:
        sents = content.replace("!", ".").replace("?", ".").split(".")
        return [s.strip() for s in sents if 40 < len(s.strip()) < 250][:4]
