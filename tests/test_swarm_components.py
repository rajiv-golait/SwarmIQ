import unittest
from unittest.mock import MagicMock, patch

from agents.swarm.coordinator import SwarmCoordinator
from agents.swarm.protocol import (
    AgentMessage,
    AgentResult,
    AgentTask,
    Claim,
    ConsensusState,
    ConsensusVote,
    MessageType,
    NegotiationRound,
    Phase,
)
from agents.swarm.roles import PlannerRole
from agents.swarm.validator import ClaimValidator, CitationGroundingValidator
from agents.synthesizer import CitationValidator
from memory.chroma_store import ChromaStore


class TestProtocol(unittest.TestCase):
    """Test swarm protocol data structures."""

    def test_agent_message_creation(self):
        msg = AgentMessage(
            sender_id="planner",
            message_type=MessageType.TASK_ASSIGNMENT,
            content={"task": "test"},
            recipient_id="worker1",
        )
        self.assertEqual(msg.sender_id, "planner")
        self.assertEqual(msg.message_type, MessageType.TASK_ASSIGNMENT)
        self.assertIsNotNone(msg.timestamp)

    def test_claim_creation(self):
        claim = Claim(
            claim_id="claim_123",
            agent_id="literature_reviewer",
            statement="Test claim statement",
            evidence_chunk_ids=["chunk_1", "chunk_2"],
            confidence=0.85,
            consensus_state=ConsensusState.PENDING,
        )
        self.assertEqual(claim.claim_id, "claim_123")
        self.assertEqual(claim.consensus_state, ConsensusState.PENDING)
        self.assertIsNotNone(claim.created_at)

    def test_consensus_vote(self):
        vote = ConsensusVote(
            claim_id="claim_123",
            voter_id="conflict_resolver",
            vote=ConsensusState.ACCEPTED,
            rationale="Evidence supports this claim",
            confidence=0.9,
        )
        self.assertEqual(vote.vote, ConsensusState.ACCEPTED)
        self.assertEqual(vote.claim_id, "claim_123")

    def test_negotiation_round(self):
        round_data = NegotiationRound(
            round_number=1,
            claims_challenged=["claim_1", "claim_2"],
            votes=[],
            outcomes={"claim_1": ConsensusState.ACCEPTED},
            unresolved=["claim_2"],
        )
        self.assertEqual(round_data.round_number, 1)
        self.assertEqual(len(round_data.unresolved), 1)


class TestSwarmCoordinator(unittest.TestCase):
    """Test swarm coordinator phase execution."""

    def test_coordinator_initialization(self):
        coordinator = SwarmCoordinator(max_workers=3)
        self.assertEqual(coordinator.max_workers, 3)
        self.assertEqual(len(coordinator.agents), 0)

    def test_agent_registration(self):
        coordinator = SwarmCoordinator()
        mock_handler = MagicMock(return_value=AgentResult(
            agent_id="test",
            phase=Phase.PLANNING,
            task_id="task_1",
            content={},
        ))
        coordinator.register_agent("planner", mock_handler)
        self.assertIn("planner", coordinator.agents)

    def test_phase_event_emission(self):
        coordinator = SwarmCoordinator()
        coordinator.state = MagicMock()
        coordinator.state.phase_events = []

        coordinator._emit_phase_event(Phase.PLANNING, "Test event", "planner")

        self.assertEqual(len(coordinator.state.phase_events), 1)
        self.assertEqual(coordinator.state.phase_events[0].phase, Phase.PLANNING)

    def test_claim_id_generation(self):
        coordinator = SwarmCoordinator()
        id1 = coordinator._generate_claim_id("agent1", "statement one")
        id2 = coordinator._generate_claim_id("agent1", "statement one")
        id3 = coordinator._generate_claim_id("agent1", "statement two")

        self.assertEqual(id1, id2)  # Deterministic
        self.assertNotEqual(id1, id3)  # Different content = different ID


class TestPlannerRole(unittest.TestCase):
    """Test planner role decomposition."""

    def test_planner_decomposes_nontrivial_query(self):
        planner = PlannerRole()
        task = AgentTask(
            task_id="task_1",
            agent_id="planner",
            phase=Phase.PLANNING,
            instruction="decompose",
            payload={"query": "AI regulation in India? Enforcement updates in 2025?"},
        )
        result = planner.run(task)
        self.assertGreaterEqual(len(result.content["subtasks"]), 2)
        self.assertIn("parallelizable", result.content)

    def test_planner_handles_simple_query(self):
        planner = PlannerRole()
        task = AgentTask(
            task_id="task_1",
            agent_id="planner",
            phase=Phase.PLANNING,
            instruction="decompose",
            payload={"query": "Simple query"},
        )
        result = planner.run(task)
        self.assertGreaterEqual(len(result.content["subtasks"]), 2)


class TestChromaStore(unittest.TestCase):
    """Test ChromaStore enhanced features."""

    def test_stable_id_is_deterministic(self):
        first = ChromaStore.stable_id("a", "b", "c")
        second = ChromaStore.stable_id("a", "b", "c")
        third = ChromaStore.stable_id("a", "b", "d")
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_citation_metadata_creation(self):
        metadata = ChromaStore.citation_metadata(
            source_url="https://example.com",
            title="Test Source",
            published_at="2025-01-01",
            chunk_id="chunk_123",
            agent_id="test_agent",
            query="test query",
        )
        self.assertEqual(metadata["source_url"], "https://example.com")
        self.assertEqual(metadata["title"], "Test Source")
        self.assertEqual(metadata["agent_id"], "test_agent")
        self.assertIn("retrieved_at", metadata)


class TestClaimValidator(unittest.TestCase):
    """Test claim-level validation."""

    def test_claim_validation_passes_with_citations(self):
        validator = ClaimValidator()
        report = (
            "This is a factual claim [1]. Another supported claim [2].\n\n"
            "## Sources\n- [1] Evidence 1\n- [2] Evidence 2"
        )
        accepted_claims = [
            {"statement": "factual claim", "evidence_chunk_ids": ["ev1"], "confidence": 0.8},
            {"statement": "supported claim", "evidence_chunk_ids": ["ev2"], "confidence": 0.9},
        ]
        evidence_lookup = {"1": "ev1", "2": "ev2"}

        result = validator.validate_report(report, accepted_claims, evidence_lookup)

        self.assertIn("verified_claims", result)
        self.assertIn("unverified_claims", result)
        self.assertIn("average_grounding_score", result)

    def test_consensus_alignment_validation(self):
        validator = ClaimValidator()
        report = (
            "## Conflict Resolution\n"
            "Some claims were uncertain due to insufficient evidence.\n\n"
            "Key finding is verified [1]."
        )
        accepted_claims = [
            {"statement": "Key finding is verified", "evidence_chunk_ids": ["ev1"]},
        ]
        uncertain_claims = [
            {"statement": "Uncertain claim needing verification"},
        ]

        result = validator.validate_consensus_alignment(report, accepted_claims, uncertain_claims)

        self.assertIn("passed", result)
        self.assertIn("has_conflict_section", result)


class TestCitationValidators(unittest.TestCase):
    """Test citation validation components."""

    def test_citation_validator_checks_inline_and_sources(self):
        validator = CitationValidator()
        report = (
            "## Executive Summary\nClaim [1].\n\n"
            "## Key Findings\nAnother claim [2].\n\n"
            "## Conflict Resolution\nNo major conflict.\n\n"
            "## Conclusion\nDone.\n\n"
            "## Sources\n- [1] https://a\n- [2] https://b\n"
        )
        passed = validator.validate(report, source_count=2)
        failed = validator.validate("No references.", source_count=2)
        self.assertTrue(passed["ok"])
        self.assertFalse(failed["ok"])


class TestMessageBroadcast(unittest.TestCase):
    """Test swarm message broadcasting."""

    def test_message_broadcast_adds_to_state(self):
        coordinator = SwarmCoordinator()
        coordinator.state = MagicMock()
        coordinator.state.messages = []

        coordinator.broadcast(
            "planner",
            MessageType.PHASE_TRANSITION,
            {"phase": "execution"},
        )

        self.assertEqual(len(coordinator.state.messages), 1)
        self.assertEqual(coordinator.state.messages[0].sender_id, "planner")


if __name__ == "__main__":
    unittest.main()
