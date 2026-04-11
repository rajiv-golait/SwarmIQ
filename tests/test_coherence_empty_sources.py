"""CoherenceScorer caps score when pipeline passes no sources (ungrounded report)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.coherence_scorer import CoherenceScorer


def test_empty_sources_caps_score_and_fails():
    scorer = CoherenceScorer(threshold=0.75)
    # Long-enough structured report that would score high if sources were present
    report = """
## Executive Summary
Lorem ipsum dolor sit amet, consectetur adipiscing elit. This summary states the topic clearly.

## Key Findings
Alpha beta gamma delta. Finding one supports the main thesis with evidence [1]. Finding two adds nuance [2].

## Conflicting Perspectives
One view emphasizes speed. Another view emphasizes safety and thorough review before action.

## Analysis
More text here with citations [1] [2] [3]. We weigh trade-offs and connect claims to the query.

## Limitations
Some limits apply to scope, data freshness, and what external sources could be verified.

## Conclusion
In conclusion, the evidence supports a cautious recommendation pending further validation.

## References
https://example.com/a https://example.com/b
"""
    r = scorer.score("test query", report, sources=[])
    assert r["score"] <= 0.5
    assert r["passed"] is False
    assert any("not grounded" in i.lower() for i in r["issues"])


def test_with_sources_can_pass():
    scorer = CoherenceScorer(threshold=0.75)
    report = """
## Executive Summary
A.

## Key Findings
B.

## Conflicting Perspectives
C.

## Analysis
D [1] [2] [3].

## Limitations
E.

## Conclusion
F.

## References
https://a.com https://b.com
"""
    r = scorer.score("q", report, sources=["https://a.com"])
    assert r["passed"] in (True, False)
    assert not any("not grounded" in i.lower() for i in r["issues"])
