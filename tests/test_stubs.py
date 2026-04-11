"""Regression test: Critic and GapDetector must NOT be stubs.

Prevents the P0 bug from ever recurring — the critic and gap detector
shipped as stubs in the first production run, producing fraudulent
coherence scores and disabling the research iteration loop.
"""
import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.critic import CriticNode
from agents.gap_detector import GapDetectorNode


def test_critic_is_not_stub():
    """CriticNode.run must NOT contain hardcoded coherence_score=1.0
    or critique_revision=99 (the stub sentinel values)."""
    source = inspect.getsource(CriticNode.run)

    # Check for the exact stub patterns
    assert "coherence_score\": 1.0" not in source.replace(" ", ""), (
        "CriticNode.run contains hardcoded coherence_score=1.0 — this is a stub!"
    )
    assert "critique_revision\": 99" not in source.replace(" ", ""), (
        "CriticNode.run contains hardcoded critique_revision=99 — this is a stub!"
    )


def test_critic_uses_coherence_scorer():
    """CriticNode must reference CoherenceScorer, not bypass it."""
    source = inspect.getsource(CriticNode)
    assert "CoherenceScorer" in source, (
        "CriticNode does not use CoherenceScorer — likely a stub"
    )


def test_gap_detector_is_not_stub():
    """GapDetectorNode.run must NOT always return empty unanswered_questions."""
    source = inspect.getsource(GapDetectorNode.run)

    # The stub had: return {"unanswered_questions": [], ...}
    # A real implementation should reference state["research_questions"]
    assert "research_questions" in source, (
        "GapDetectorNode.run does not read research_questions — likely a stub"
    )
    assert "evidence_chunks" in source, (
        "GapDetectorNode.run does not read evidence_chunks — likely a stub"
    )


def test_gap_detector_uses_llm():
    """GapDetectorNode must use an LLM for evaluation, not hardcode results."""
    source = inspect.getsource(GapDetectorNode)
    assert "Groq" in source or "client" in source, (
        "GapDetectorNode does not reference any LLM client — likely a stub"
    )


def test_critic_returns_is_stub_false():
    """The CoherenceScorer must include is_stub: False in its return dict."""
    from evaluation.coherence_scorer import CoherenceScorer

    scorer = CoherenceScorer()
    result = scorer.score(
        "test query",
        "## Executive Summary\nThis is a test report with [1] citations. " * 50
        + "\n## Key Findings\nMore content [2].\n## Conclusion\nDone.\n"
        "## References\nhttps://example.com/1\nhttps://example.com/2",
        ["https://example.com/1", "https://example.com/2"],
    )
    assert "is_stub" in result, "CoherenceScorer must return is_stub field"
    assert result["is_stub"] is False, "CoherenceScorer.is_stub must be False"
