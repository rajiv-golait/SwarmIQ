"""PlannerNode — decomposes research queries and validates search queries.

Fix from run fd92dd06a5ae:
  - Bug 4: 5 of 7 search queries contained "cluade" (typo of "claude").
    Added _validate_and_fix_queries() post-processing after JSON parse.
"""
import json
import re
import logging
from datetime import datetime

from groq import Groq
from agents.state import SwarmState, ResearchQuestion
from memory.lance_store import LanceStore
from utils.config import LLM_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)

# Common planner typos — fix before token-overlap checks (Bug 4, run fd92dd06a5ae)
_CLUADE_TYPO = re.compile(r"\bcluade\b", re.IGNORECASE)


def _failed_generation_from_error(exc: BaseException) -> str:
    """Groq json_object 400 responses may include error.error.failed_generation."""
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = None
    if not isinstance(body, dict):
        body = None
    if body is None:
        resp = getattr(exc, "response", None)
        if resp is not None:
            try:
                body = resp.json()
            except Exception:
                body = None
    if not isinstance(body, dict):
        return ""
    err = body.get("error")
    if not isinstance(err, dict):
        return ""
    fg = err.get("failed_generation")
    return fg.strip() if isinstance(fg, str) else ""


def _validate_and_fix_queries(
    questions: list[ResearchQuestion],
    original_query: str,
) -> list[ResearchQuestion]:
    """Ensure every generated search query is usable.

    Checks:
    1. Non-empty
    2. Not longer than 100 chars (LLMs sometimes emit sentences)
    3. Contains at least one token from the original query (catches typos)

    If a query fails check 3, it is replaced with a corrected fallback
    that appends the original query tokens.
    """
    # Extract significant tokens from the original query (len > 3)
    original_tokens = {
        w.lower() for w in re.findall(r'\b\w+\b', original_query)
        if len(w) > 3
    }

    for question in questions:
        fixed: list[str] = []
        for q in question.get("search_queries", []):
            q = q.strip()
            if not q:
                continue
            q = _CLUADE_TYPO.sub("Claude", q)
            if len(q) > 100:
                q = q[:100]
            # Check token overlap with original query
            q_tokens = {w.lower() for w in re.findall(r'\b\w+\b', q)}
            if original_tokens and not q_tokens.intersection(original_tokens):
                # Typo or hallucinated query — append original query as anchor
                original_q = q
                q = f"{q} {original_query}"
                logger.warning(
                    f"[Plan] Query '{original_q[:60]}' had no token overlap "
                    f"with original query — appended original as anchor"
                )
            fixed.append(q)

        # If all queries were dropped, use safe fallbacks
        if not fixed:
            fixed = [
                f"{original_query} overview",
                f"{original_query} 2025 2026",
            ]
        question["search_queries"] = fixed

    return questions


class PlannerNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    @staticmethod
    def _parse_llm_json(raw: str) -> list[dict]:
        """Parse planner JSON; repair common Groq/Llama json_object mistakes."""
        if not raw or not str(raw).strip():
            return []

        s = str(raw).strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL | re.IGNORECASE)
        if m:
            s = m.group(1).strip()

        brace = s.find("{")
        if brace >= 0:
            s = s[brace:]

        def _loads_questions(text: str) -> list[dict] | None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None
            if not isinstance(data, dict):
                return None
            qs = data.get("questions", [])
            if not isinstance(qs, list):
                return None
            return [x for x in qs if isinstance(x, dict)]

        # Progressive repairs (do not globally swap quotes — breaks "it's" in text fields).
        candidates: list[str] = [s]
        t = re.sub(r'"queries:\s*\[', '"queries": [', s)
        t = re.sub(r'"queries=\s*\[', '"queries": [', t)
        # Model wrapped the whole array in an extra string close: ... ]"\n or ]"},
        t = re.sub(r"\]\s*\"\s*\n", "]\n", t)
        t = re.sub(r"\]\s*\"\s*,", "],", t)
        t = re.sub(r"\]\s*\"\s*}", "]}", t)
        t = re.sub(r",\s*([}\]])", r"\1", t)
        if t != s:
            candidates.append(t)
        t2 = re.sub(r"\\'([^'\\]*)\\'", r'"\1"', t)
        if t2 != t:
            candidates.append(t2)
        # Model emitted literal \n tokens inside the array instead of commas/newlines.
        t3 = re.sub(r"\\n\s*", " ", t2)
        if t3 != t2:
            candidates.append(t3)

        for cand in candidates:
            got = _loads_questions(cand)
            if got:
                return got

        logger.error(f"[Plan] JSON repair failed; head:\n{s[:480]}")
        return []

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
            return self._targeted_plan(unanswered, iteration, query)

        # First iteration: full decomposition (70B for better query quality vs stale 8B cutoff)
        now          = datetime.now()
        current_date = now.strftime("%B %d, %Y")
        current_year = now.year
        groq_limiter.wait_if_needed(800)
        questions_data: list = []
        try:
            resp = self.client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=600,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Today's date is {current_date}. The current year is {current_year}. "
                            "Your training data may be outdated — assume major developments since "
                            "your knowledge cutoff. Generate web search queries a human would type "
                            f"today; prefer {current_year} and the last 12 months.\n\n"
                            "You decompose the research topic into 4-6 specific sub-questions. "
                            "Return ONLY valid JSON. Use this EXACT structure, no variations:\n\n"
                            '{"questions": [\n'
                            '  {"id": "q1", "text": "specific question here", '
                            '"queries": ["search term one", "search term two"]},\n'
                            '  {"id": "q2", "text": "another question", '
                            '"queries": ["search term three", "search term four"]}\n'
                            "]}\n\n"
                            "Rules:\n"
                            "- The key must be spelled exactly \"queries\" with a JSON array of "
                            "strings as its value — never a single string, never `queries:[` or "
                            "`queries=` inside quotes.\n"
                            "- Each question needs 2-3 short search-engine queries, not essay titles.\n"
                            "- Use double quotes for all JSON strings.\n"
                            "- Do not add any text outside the JSON object."
                        ),
                    },
                    {"role": "user", "content": f"Research topic: {query}"},
                ],
            )
            raw            = resp.choices[0].message.content or "{}"
            questions_data = self._parse_llm_json(raw)
        except Exception as e:
            fg = _failed_generation_from_error(e)
            if fg:
                questions_data = self._parse_llm_json(fg)
            if not questions_data:
                logger.warning(f"[Plan] LLM failed: {e} — using fallback")
                questions_data = self._fallback(query)

        if not questions_data:
            questions_data = self._fallback(query)

        questions: list[ResearchQuestion] = []
        for i, q in enumerate(questions_data):
            if not isinstance(q, dict):
                continue
            raw_q = q.get("queries", [query])
            if isinstance(raw_q, list):
                sq = [str(x).strip() for x in raw_q if str(x).strip()]
            else:
                sq = [query]
            if not sq:
                sq = [query]
            questions.append({
                "question_id":    q.get("id", f"q{i}"),
                "text":           q.get("text", query),
                "search_queries": sq,
                "answered":       False,
            })

        # ── Validate and fix search queries (catches typos like "cluade") ──
        questions = _validate_and_fix_queries(questions, query)

        log = f"[Plan] {len(questions)} questions generated for: {query[:60]}"
        logger.info(log)

        return {
            "research_questions":   questions,
            "unanswered_questions": questions,
            "research_iteration":   1,
            "phase_log":            [log],
        }

    def _targeted_plan(
        self, unanswered: list[ResearchQuestion], iteration: int, query: str,
    ) -> dict:
        """Generate targeted search queries for unanswered questions.

        Rotate wording by iteration so search cache keys and DDG results differ
        from the first pass (see search/cache.py).
        """
        current_year = datetime.now().year
        for q in unanswered:
            qt = (q.get("text") or query).strip()
            if iteration <= 1:
                q["search_queries"] = [
                    f"{qt} {current_year}",
                    f"{qt} recent",
                ]
            else:
                q["search_queries"] = [
                    f"{qt} news",
                    f"how {qt}",
                ]
        # Validate targeted queries too
        unanswered = _validate_and_fix_queries(unanswered, query)
        log = f"[Plan] Iteration {iteration+1}: targeting {len(unanswered)} unanswered questions"
        return {
            "unanswered_questions": unanswered,
            "research_iteration":   iteration + 1,
            "phase_log":            [log],
        }

    def _fallback(self, query: str) -> list[dict]:
        y = datetime.now().year
        return [
            {"id": "q1", "text": f"Background: {query}",
             "queries": [f"{query} overview {y}", f"{query} explained"]},
            {"id": "q2", "text": f"Current status: {query}",
             "queries": [f"{query} latest news {y}", f"{query} {y}"]},
            {"id": "q3", "text": f"Expert perspectives on: {query}",
             "queries": [f"{query} expert opinion", f"{query} analysis"]},
        ]
