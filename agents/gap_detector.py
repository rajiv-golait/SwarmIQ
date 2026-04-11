"""GapDetectorNode — evaluates whether research questions have been adequately answered.

Replaces the stub that returned unanswered_questions=[] unconditionally.
When unanswered questions are returned, the _should_research_more conditional
edge in graph.py loops back to the planner for targeted re-search.
"""
import json
import logging
from groq import Groq
from agents.state import SwarmState, ResearchQuestion
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class GapDetectorNode:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        questions = state.get("research_questions", [])
        evidence  = state.get("evidence_chunks", [])
        claims    = state.get("claims", [])

        if not questions:
            return {
                "unanswered_questions": [],
                "phase_log": ["[GapDetect] No questions to evaluate"],
            }

        # Build a compact summary of available evidence per question
        evidence_by_q: dict[str, list[str]] = {}
        for chunk in evidence:
            qid = chunk.get("question_id", "unknown")
            snippet = (chunk.get("content") or "")[:200]
            evidence_by_q.setdefault(qid, []).append(snippet)

        questions_text = ""
        for q in questions:
            qid     = q["question_id"]
            n_ev    = len(evidence_by_q.get(qid, []))
            n_claims_for_q = sum(
                1 for c in claims
                if any(eid in [ch.get("chunk_id", "") for ch in evidence
                               if ch.get("question_id") == qid]
                       for eid in c.get("evidence_chunk_ids", []))
            )
            questions_text += (
                f"- {qid}: \"{q['text']}\" | "
                f"{n_ev} evidence chunks, ~{n_claims_for_q} claims\n"
            )

        groq_limiter.wait_if_needed(estimated_tokens=400)
        try:
            resp = self.client.chat.completions.create(
                model=FAST_MODEL,
                max_tokens=300,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You evaluate whether research questions have been adequately answered. "
                            "A question is adequately answered if it has ≥3 evidence chunks and ≥2 claims. "
                            "A question with 0 evidence or 0 claims is definitely unanswered. "
                            'Return ONLY valid JSON: {"unanswered": ["q1", "q3"]} — '
                            "list the question IDs that need more research. "
                            "Return {\"unanswered\": []} if all questions are adequately covered."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Research questions and their coverage:\n{questions_text}",
                    },
                ],
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            unanswered_ids = set(data.get("unanswered", []))
        except Exception as e:
            logger.warning(f"[GapDetect] LLM evaluation failed: {e} — assuming all answered")
            unanswered_ids = set()

        # Build the unanswered_questions list from the question IDs the LLM flagged
        unanswered: list[ResearchQuestion] = [
            q for q in questions
            if q["question_id"] in unanswered_ids
        ]

        if unanswered:
            log = (
                f"[GapDetect] {len(unanswered)} of {len(questions)} questions "
                f"need more research: {[q['question_id'] for q in unanswered]}"
            )
        else:
            log = f"[GapDetect] All {len(questions)} questions adequately covered"

        logger.info(log)
        return {
            "unanswered_questions": unanswered,
            "phase_log": [log],
        }
