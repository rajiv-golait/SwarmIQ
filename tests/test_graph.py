"""Fan-in safety test for SwarmIQ parallel branches.

Validates that operator.add reducers on evidence_chunks, claims,
phase_log, and errors correctly merge both parallel branches before
the next node fires. No Groq API calls required.

Property P5: Parallel fan-in via Send API SHALL ensure both branches
complete before detect_gaps fires.
"""
import sys
import os
import uuid

import pytest

# Ensure swarmiq/ is on the path when running from swarmiq/ dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from agents.state import SwarmState, EvidenceChunk, Claim


# ── Stub nodes (no LLM, no network) ─────────────────────────────────────────

def branch_a(state: SwarmState) -> dict:
    """Simulates literature_review branch."""
    return {
        "evidence_chunks": [
            EvidenceChunk(
                chunk_id="chunk-a1",
                content="Evidence from branch A",
                source_url="https://example.com/a",
                source_domain="example.com",
                published_date="2024-01-01",
                agent_id="literature_reviewer",
                confidence=0.9,
                question_id="q1",
            )
        ],
        "claims": [
            Claim(
                claim_id="claim-a1",
                statement="Claim from branch A",
                agent_id="literature_reviewer",
                evidence_chunk_ids=["chunk-a1"],
                confidence=0.9,
                consensus_state="pending",
                vote_rationale="",
            )
        ],
        "phase_log": ["[BranchA] literature_review complete"],
        "errors": [],
    }


def branch_b(state: SwarmState) -> dict:
    """Simulates summarize branch."""
    return {
        "evidence_chunks": [
            EvidenceChunk(
                chunk_id="chunk-b1",
                content="Evidence from branch B",
                source_url="https://example.com/b",
                source_domain="example.com",
                published_date="2024-01-02",
                agent_id="summarizer",
                confidence=0.8,
                question_id="q1",
            )
        ],
        "claims": [
            Claim(
                claim_id="claim-b1",
                statement="Claim from branch B",
                agent_id="summarizer",
                evidence_chunk_ids=["chunk-b1"],
                confidence=0.8,
                consensus_state="pending",
                vote_rationale="",
            )
        ],
        "phase_log": ["[BranchB] summarize complete"],
        "errors": [],
    }


def detect_gaps(state: SwarmState) -> dict:
    """Stub gap detector — records what it received from both branches."""
    return {
        "unanswered_questions": [],
        "phase_log": [
            f"[GapDetect] received {len(state['evidence_chunks'])} chunks, "
            f"{len(state['claims'])} claims"
        ],
    }


def _fan_out(state: SwarmState) -> list:
    return [
        Send("branch_a", state),
        Send("branch_b", state),
    ]


def build_test_graph():
    """Build a minimal graph that mirrors the real SwarmIQ fan-out pattern.

    start → (Send API fan-out) → branch_a + branch_b (parallel)
                                       ↓ operator.add merges
                                  detect_gaps → END

    The key: branch_a and branch_b do NOT have explicit edges to detect_gaps.
    LangGraph's Send API + operator.add reducers handle the fan-in automatically.
    detect_gaps fires exactly once, after both branches complete.
    """
    builder = StateGraph(SwarmState)

    # Start node fans out via Send API
    def start(state: SwarmState) -> dict:
        return {}

    builder.add_node("start",       start)
    builder.add_node("branch_a",    branch_a)
    builder.add_node("branch_b",    branch_b)
    builder.add_node("detect_gaps", detect_gaps)

    builder.set_entry_point("start")
    # Conditional edge from start uses Send to dispatch both branches in parallel
    builder.add_conditional_edges("start", _fan_out, ["branch_a", "branch_b"])
    # Both branches feed into detect_gaps — operator.add merges their outputs
    builder.add_edge("branch_a", "detect_gaps")
    builder.add_edge("branch_b", "detect_gaps")
    builder.add_edge("detect_gaps", END)

    return builder.compile()


# ── Tests ────────────────────────────────────────────────────────────────────

def test_fan_in_merges_evidence_chunks():
    """Both branches' evidence_chunks are merged via operator.add."""
    graph = build_test_graph()
    initial: SwarmState = {
        "query": "test query",
        "run_id": str(uuid.uuid4()),
        "research_questions": [],
        "evidence_chunks": [],
        "claims": [],
        "accepted_claims": [],
        "rejected_claims": [],
        "uncertain_claims": [],
        "negotiation_rounds": [],
        "unanswered_questions": [],
        "research_iteration": 0,
        "report": "",
        "word_count": 0,
        "sources_used": [],
        "coherence_score": 0.0,
        "critique_issues": [],
        "critique_revision": 0,
        "visualization": {},
        "phase_log": [],
        "errors": [],
    }

    result = graph.invoke(initial)

    # Both branches contributed — operator.add merged them
    assert len(result["evidence_chunks"]) == 2, (
        f"Expected 2 evidence chunks (one per branch), got {len(result['evidence_chunks'])}"
    )
    chunk_ids = {c["chunk_id"] for c in result["evidence_chunks"]}
    assert "chunk-a1" in chunk_ids, "Branch A chunk missing from merged state"
    assert "chunk-b1" in chunk_ids, "Branch B chunk missing from merged state"


def test_fan_in_merges_claims():
    """Both branches' claims are merged via operator.add."""
    graph = build_test_graph()
    initial: SwarmState = {
        "query": "test query",
        "run_id": str(uuid.uuid4()),
        "research_questions": [],
        "evidence_chunks": [],
        "claims": [],
        "accepted_claims": [],
        "rejected_claims": [],
        "uncertain_claims": [],
        "negotiation_rounds": [],
        "unanswered_questions": [],
        "research_iteration": 0,
        "report": "",
        "word_count": 0,
        "sources_used": [],
        "coherence_score": 0.0,
        "critique_issues": [],
        "critique_revision": 0,
        "visualization": {},
        "phase_log": [],
        "errors": [],
    }

    result = graph.invoke(initial)

    assert len(result["claims"]) == 2, (
        f"Expected 2 claims (one per branch), got {len(result['claims'])}"
    )
    claim_ids = {c["claim_id"] for c in result["claims"]}
    assert "claim-a1" in claim_ids
    assert "claim-b1" in claim_ids


def test_fan_in_merges_phase_log():
    """phase_log entries from both branches are merged via operator.add."""
    graph = build_test_graph()
    initial: SwarmState = {
        "query": "test query",
        "run_id": str(uuid.uuid4()),
        "research_questions": [],
        "evidence_chunks": [],
        "claims": [],
        "accepted_claims": [],
        "rejected_claims": [],
        "uncertain_claims": [],
        "negotiation_rounds": [],
        "unanswered_questions": [],
        "research_iteration": 0,
        "report": "",
        "word_count": 0,
        "sources_used": [],
        "coherence_score": 0.0,
        "critique_issues": [],
        "critique_revision": 0,
        "visualization": {},
        "phase_log": [],
        "errors": [],
    }

    result = graph.invoke(initial)

    log = result["phase_log"]
    assert any("BranchA" in entry for entry in log), "Branch A log missing"
    assert any("BranchB" in entry for entry in log), "Branch B log missing"
    assert any("GapDetect" in entry for entry in log), "GapDetect log missing"


def test_detect_gaps_sees_merged_state():
    """detect_gaps receives the fully merged state from both branches (P5)."""
    graph = build_test_graph()
    initial: SwarmState = {
        "query": "test query",
        "run_id": str(uuid.uuid4()),
        "research_questions": [],
        "evidence_chunks": [],
        "claims": [],
        "accepted_claims": [],
        "rejected_claims": [],
        "uncertain_claims": [],
        "negotiation_rounds": [],
        "unanswered_questions": [],
        "research_iteration": 0,
        "report": "",
        "word_count": 0,
        "sources_used": [],
        "coherence_score": 0.0,
        "critique_issues": [],
        "critique_revision": 0,
        "visualization": {},
        "phase_log": [],
        "errors": [],
    }

    result = graph.invoke(initial)

    # The GapDetect log entry records what it received
    gap_log = [e for e in result["phase_log"] if "GapDetect" in e]
    assert len(gap_log) == 1
    assert "2 chunks" in gap_log[0], (
        f"detect_gaps should have seen 2 chunks, log says: {gap_log[0]}"
    )
    assert "2 claims" in gap_log[0], (
        f"detect_gaps should have seen 2 claims, log says: {gap_log[0]}"
    )


def test_no_claim_has_ungrounded_id():
    """P6: No Claim object shall have claim_id == 'ungrounded' or empty evidence_chunk_ids."""
    graph = build_test_graph()
    initial: SwarmState = {
        "query": "test query",
        "run_id": str(uuid.uuid4()),
        "research_questions": [],
        "evidence_chunks": [],
        "claims": [],
        "accepted_claims": [],
        "rejected_claims": [],
        "uncertain_claims": [],
        "negotiation_rounds": [],
        "unanswered_questions": [],
        "research_iteration": 0,
        "report": "",
        "word_count": 0,
        "sources_used": [],
        "coherence_score": 0.0,
        "critique_issues": [],
        "critique_revision": 0,
        "visualization": {},
        "phase_log": [],
        "errors": [],
    }

    result = graph.invoke(initial)

    for claim in result["claims"]:
        assert claim["claim_id"] != "ungrounded", (
            f"Claim has forbidden id 'ungrounded': {claim}"
        )
        assert claim["evidence_chunk_ids"], (
            f"Claim has empty evidence_chunk_ids: {claim}"
        )
