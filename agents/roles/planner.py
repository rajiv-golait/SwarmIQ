import json
import logging
from groq import Groq
from agents.state import SwarmState, ResearchQuestion
from memory.lance_store import LanceStore
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class PlannerNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        query      = state["query"]
        iteration  = state.get("research_iteration", 0)

        # On re-search iterations, focus on unanswered questions
        if iteration > 0:
            unanswered = state.get("unanswered_questions", [])
            if not unanswered:
                return {
                    "research_iteration": iteration + 1,
                    "phase_log": ["[Plan] No unanswered questions — skipping re-plan"],
                }
            # Generate targeted queries for unanswered questions only
            return self._targeted_plan(unanswered, iteration)

        # First iteration: full decomposition
        groq_limiter.wait_if_needed(800)
        try:
            resp = self.client.chat.completions.create(
                model=FAST_MODEL,
                max_tokens=600,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Decompose the research topic into 4-6 specific questions. "
                            'Return ONLY valid JSON: {"questions": ['
                            '{"id": "q1", "text": "...", "queries": ["ddg query 1", "ddg query 2"]}'
                            "]} — queries must be actual search engine queries, not topics."
                        ),
                    },
                    {"role": "user", "content": f"Research topic: {query}"},
                ],
            )
            data           = json.loads(resp.choices[0].message.content or "{}")
            questions_data = data.get("questions", [])
        except Exception as e:
            logger.warning(f"[Plan] LLM failed: {e} — using fallback")
            questions_data = self._fallback(query)

        questions: list[ResearchQuestion] = [
            {
                "question_id":    q.get("id", f"q{i}"),
                "text":           q.get("text", query),
                "search_queries": q.get("queries", [query]),
                "answered":       False,
            }
            for i, q in enumerate(questions_data)
        ]

        log = f"[Plan] {len(questions)} questions generated for: {query[:60]}"
        logger.info(log)

        return {
            "research_questions":   questions,
            "unanswered_questions": questions,
            "research_iteration":   1,
            "phase_log":            [log],
        }

    def _targeted_plan(
        self, unanswered: list[ResearchQuestion], iteration: int
    ) -> dict:
        """Generate targeted search queries for unanswered questions."""
        for q in unanswered:
            if not q.get("search_queries"):
                q["search_queries"] = [
                    f"{q['text']} 2024",
                    f"{q['text']} research evidence",
                ]
        log = f"[Plan] Iteration {iteration+1}: targeting {len(unanswered)} unanswered questions"
        return {
            "unanswered_questions": unanswered,
            "research_iteration":   iteration + 1,
            "phase_log":            [log],
        }

    def _fallback(self, query: str) -> list[dict]:
        return [
            {"id": "q1", "text": f"Background: {query}",
             "queries": [f"{query} overview 2024", f"{query} explained"]},
            {"id": "q2", "text": f"Current status: {query}",
             "queries": [f"{query} latest news", f"{query} 2025"]},
            {"id": "q3", "text": f"Expert perspectives on: {query}",
             "queries": [f"{query} expert opinion", f"{query} analysis"]},
        ]
