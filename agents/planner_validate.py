"""Post-process planner search queries: fix common typos and anchor off-topic strings."""
from __future__ import annotations

import logging
import re
from agents.state import ResearchQuestion

logger = logging.getLogger(__name__)

# Observed in production: LLM emits "cluade" for "Claude"
_TYPO_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bcluade\b", re.IGNORECASE), "Claude"),
]


def validate_and_fix_queries(
    questions: list[ResearchQuestion],
    original_query: str,
) -> list[ResearchQuestion]:
    """Normalize queries: typo fixes, length cap, anchor if no token overlap with topic."""
    original_tokens = {
        w.lower()
        for w in re.findall(r"\b\w+\b", original_query)
        if len(w) > 3
    }

    for question in questions:
        fixed: list[str] = []
        for raw in question.get("search_queries", []) or []:
            q = (raw or "").strip()
            if not q:
                continue
            for pat, rep in _TYPO_PATTERNS:
                q = pat.sub(rep, q)
            if len(q) > 100:
                q = q[:100].rsplit(" ", 1)[0] or q[:100]

            q_tokens = {w.lower() for w in re.findall(r"\b\w+\b", q) if len(w) > 3}
            if original_tokens and not q_tokens.intersection(original_tokens):
                q = f"{q} {original_query}".strip()
                logger.warning(
                    "[Plan] Query had no long-token overlap with original — anchored: %s",
                    q[:70],
                )
            fixed.append(q)

        if not fixed:
            fixed = [
                f"{original_query} overview",
                f"{original_query} 2025 2026",
            ]
        question["search_queries"] = fixed

    return questions
