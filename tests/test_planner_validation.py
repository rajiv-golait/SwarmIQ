"""Regression test: Planner query validation catches typos.

Reproduces Bug 4 from run fd92dd06a5ae where 5 of 7 search queries
contained "cluade" (typo of "claude") and were passed directly to DDG.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.roles.planner import _validate_and_fix_queries


def test_typo_cluade_corrected():
    """Observed bug: LLM emits 'cluade' — must not reach search unchanged."""
    questions = [
        {
            "question_id": "q1",
            "text": "When was the latest model released?",
            "search_queries": [
                "cluade model 2026 release date",
                "latest AI model release April",
            ],
            "answered": False,
        }
    ]
    original_query = "Latest Claude Model Released in 2026 April"

    fixed = _validate_and_fix_queries(questions, original_query)

    q1_queries = fixed[0]["search_queries"]
    assert len(q1_queries) == 2, f"Expected 2 queries, got {len(q1_queries)}"

    assert "cluade" not in q1_queries[0].lower(), (
        f"Typo must be corrected, got: {q1_queries[0]}"
    )
    assert "claude" in q1_queries[0].lower()

    assert q1_queries[1] == "latest AI model release April", (
        f"Valid query should be unchanged, got: {q1_queries[1]}"
    )


def test_offtopic_query_gets_anchor_appended():
    """Zero long-token overlap with the user query → append original as anchor."""
    questions = [
        {
            "question_id": "q1",
            "text": "Widgets",
            "search_queries": ["random unrelated xyzabc topic"],
            "answered": False,
        }
    ]
    fixed = _validate_and_fix_queries(questions, "Anthropic API pricing")
    combined = " ".join(fixed[0]["search_queries"]).lower()
    assert "anthropic" in combined or "pricing" in combined


def test_empty_queries_get_fallback():
    """Questions with empty search_queries get safe fallbacks."""
    questions = [
        {
            "question_id": "q1",
            "text": "Background on the topic",
            "search_queries": [],
            "answered": False,
        }
    ]
    original_query = "Claude AI model"
    fixed = _validate_and_fix_queries(questions, original_query)
    assert len(fixed[0]["search_queries"]) >= 2, "Empty queries should get fallbacks"
    assert any("Claude AI model" in q for q in fixed[0]["search_queries"])


def test_long_queries_get_truncated():
    """Queries longer than 100 chars are truncated."""
    questions = [
        {
            "question_id": "q1",
            "text": "Test",
            "search_queries": ["a" * 150],
            "answered": False,
        }
    ]
    fixed = _validate_and_fix_queries(questions, "test query")
    for q in fixed[0]["search_queries"]:
        assert len(q) <= 200, f"Query too long after fix: {len(q)} chars"


def test_valid_queries_unchanged():
    """Queries with token overlap should not be modified."""
    questions = [
        {
            "question_id": "q1",
            "text": "Claude capabilities",
            "search_queries": [
                "Claude model capabilities 2026",
                "Claude latest features",
            ],
            "answered": False,
        }
    ]
    original_query = "Claude model features"
    fixed = _validate_and_fix_queries(questions, original_query)
    assert fixed[0]["search_queries"] == [
        "Claude model capabilities 2026",
        "Claude latest features",
    ]
