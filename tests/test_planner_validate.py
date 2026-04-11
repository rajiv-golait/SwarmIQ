"""Planner query validation (v4.0 — typo / anchoring)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.planner_validate import validate_and_fix_queries


def test_cluade_typo_corrected():
    questions = [
        {
            "question_id": "q1",
            "text": "Claude releases",
            "search_queries": ["cluade model 2026 features"],
            "answered": False,
        }
    ]
    out = validate_and_fix_queries(questions, "Latest Claude model April 2026")
    q = out[0]["search_queries"][0].lower()
    assert "cluade" not in q
    assert "claude" in q


def test_offtopic_query_gets_anchor():
    questions = [
        {
            "question_id": "q1",
            "text": "Widgets",
            "search_queries": ["random unrelated xyzabc topic"],
            "answered": False,
        }
    ]
    out = validate_and_fix_queries(questions, "Anthropic API pricing")
    combined = " ".join(out[0]["search_queries"]).lower()
    assert "anthropic" in combined or "pricing" in combined
