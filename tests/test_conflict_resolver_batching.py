"""Regression test: ConflictResolver batched voting and deduplication.

Reproduces Bug 5 (Round 1 resolved only 13.9% of claims) and
Bug 6 (duplicate claim_ids entering negotiation) from run fd92dd06a5ae.

These tests mock the Groq client to avoid API calls.
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents.roles.conflict_resolver import ConflictResolverNode, BATCH_SIZE


def _make_claims(n: int) -> list[dict]:
    """Generate n distinct pending claims."""
    return [
        {
            "claim_id": f"claim_{i:04d}",
            "statement": f"Claim number {i} about research topic",
            "agent_id": "test",
            "evidence_chunk_ids": [f"chunk_{i:04d}"],
            "confidence": 0.7 + (i % 3) * 0.1,
            "consensus_state": "pending",
            "vote_rationale": "",
        }
        for i in range(n)
    ]


def _mock_vote_response(claims: list[dict], vote: str = "accepted") -> str:
    """Build a mock JSON response voting on all claims in the batch."""
    votes = [
        {
            "claim_id": c["claim_id"][:12],
            "vote": vote,
            "rationale": f"Auto {vote}",
        }
        for c in claims
    ]
    return json.dumps({"votes": votes})


def test_batch_voting_resolves_all_claims():
    """All claims should be resolved — no silent loss."""
    n_claims = 47  # Not a multiple of BATCH_SIZE to test remainder handling
    claims = _make_claims(n_claims)

    store = MagicMock()
    store.query.return_value = []  # No stored evidence needed

    node = ConflictResolverNode(store)

    # Mock Groq: accept every claim in every batch
    mock_resp = MagicMock()
    def create_side_effect(**kwargs):
        # Parse the claims from the user message to build matching votes
        user_msg = kwargs.get("messages", [{}])[-1].get("content", "")
        # Count IDs in the message
        ids = [line.split("ID:")[1].split(" |")[0] for line in user_msg.split("\n") if "ID:" in line]
        votes_json = json.dumps({
            "votes": [
                {"claim_id": cid, "vote": "accepted", "rationale": "ok"}
                for cid in ids
            ]
        })
        mock_resp.choices = [MagicMock(message=MagicMock(content=votes_json))]
        return mock_resp

    node.client = MagicMock()
    node.client.chat.completions.create.side_effect = create_side_effect

    state = {
        "query": "test query",
        "claims": claims,
    }

    with patch("agents.roles.conflict_resolver.rerank", return_value=[]):
        with patch("agents.roles.conflict_resolver.groq_limiter"):
            with patch("agents.roles.conflict_resolver.emit_progress"):
                result = node.run(state)

    total_resolved = (
        len(result["accepted_claims"])
        + len(result["rejected_claims"])
        + len(result["uncertain_claims"])
    )
    assert total_resolved == n_claims, (
        f"Expected {n_claims} claims resolved, got {total_resolved} "
        f"(accepted={len(result['accepted_claims'])}, "
        f"rejected={len(result['rejected_claims'])}, "
        f"uncertain={len(result['uncertain_claims'])})"
    )


def test_deduplication_before_negotiation():
    """Duplicate claim_ids should be removed before voting begins."""
    claims = _make_claims(10)
    # Add 5 duplicates (same claim_id)
    duplicates = [dict(c) for c in claims[:5]]
    all_claims = claims + duplicates  # 15 total, 10 unique

    store = MagicMock()
    store.query.return_value = []

    node = ConflictResolverNode(store)

    # Mock Groq to accept everything
    mock_resp = MagicMock()
    def create_side_effect(**kwargs):
        user_msg = kwargs.get("messages", [{}])[-1].get("content", "")
        ids = [line.split("ID:")[1].split(" |")[0] for line in user_msg.split("\n") if "ID:" in line]
        votes_json = json.dumps({
            "votes": [
                {"claim_id": cid, "vote": "accepted", "rationale": "ok"}
                for cid in ids
            ]
        })
        mock_resp.choices = [MagicMock(message=MagicMock(content=votes_json))]
        return mock_resp

    node.client = MagicMock()
    node.client.chat.completions.create.side_effect = create_side_effect

    state = {"query": "test", "claims": all_claims}

    with patch("agents.roles.conflict_resolver.rerank", return_value=[]):
        with patch("agents.roles.conflict_resolver.groq_limiter"):
            with patch("agents.roles.conflict_resolver.emit_progress"):
                result = node.run(state)

    total = (
        len(result["accepted_claims"])
        + len(result["rejected_claims"])
        + len(result["uncertain_claims"])
    )
    # Should be 10 (unique), not 15 (with duplicates)
    assert total == 10, (
        f"Expected 10 unique claims after dedup, got {total}"
    )


def test_batch_size_is_reasonable():
    """BATCH_SIZE must be ≤ 20 to avoid token truncation."""
    assert BATCH_SIZE <= 20, f"BATCH_SIZE={BATCH_SIZE} is too large — risk of truncation"
    assert BATCH_SIZE >= 5, f"BATCH_SIZE={BATCH_SIZE} is too small — too many API calls"
