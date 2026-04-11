"""Regression test: Synthesizer citation inflation.

Reproduces Bug 7 from run fd92dd06a5ae where the report used [1]-[24]
inline citations but only 9 unique sources existed.
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.roles.synthesizer import SynthesizerNode


def test_clamp_citations_reduces_to_max():
    """Citations above the source count must be clamped down."""
    report = (
        "This is a test report. According to [1], the findings are clear. "
        "Further evidence from [5] and [12] confirms this. "
        "Additional data from [24] also supports the conclusion [3]."
    )
    max_sources = 9

    clamped, issues = SynthesizerNode._clamp_citations(report, max_sources)

    # Extract all citation numbers from the clamped report
    nums = [int(n) for n in re.findall(r"\[(\d+)\]", clamped)]
    assert all(n <= max_sources for n in nums), (
        f"Found citation > {max_sources} after clamping: {nums}"
    )
    assert len(issues) > 0, "Should have reported clamping issues"


def test_clamp_citations_no_change_when_valid():
    """Reports with valid citations should not be modified."""
    report = "Finding [1] and [2] confirm the hypothesis [3]."
    max_sources = 5

    clamped, issues = SynthesizerNode._clamp_citations(report, max_sources)

    assert clamped == report, "Valid report should not be modified"
    assert len(issues) == 0, "No issues expected for valid citations"


def test_clamp_citations_zero_sources():
    """Edge case: max_source_num=0 should return report unchanged."""
    report = "Finding [1] and [2]."
    clamped, issues = SynthesizerNode._clamp_citations(report, 0)
    assert clamped == report
    assert len(issues) == 0


def test_no_citation_numbers_exceed_source_count():
    """Simulates the exact scenario from the production run:
    24 inline citations but only 9 sources."""
    # Build a report with citations [1] through [24]
    sentences = [f"Claim {i} is supported by evidence [{i}]." for i in range(1, 25)]
    report = " ".join(sentences)
    max_sources = 9

    clamped, issues = SynthesizerNode._clamp_citations(report, max_sources)

    nums = [int(n) for n in re.findall(r"\[(\d+)\]", clamped)]
    max_citation = max(nums) if nums else 0
    assert max_citation <= max_sources, (
        f"Max citation [{max_citation}] exceeds source count [{max_sources}]"
    )
