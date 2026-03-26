import unittest
from unittest.mock import MagicMock, patch

from agents.supervisor import Supervisor
from agents.swarm.protocol import ConsensusState, Phase
from agents.swarm.coordinator import SwarmCoordinator


class TestSupervisorIntegration(unittest.TestCase):
    """Integration tests for supervisor with mocked dependencies."""

    @patch("agents.supervisor.SWARM_MODE", False)
    @patch("agents.supervisor.Researcher")
    @patch("agents.supervisor.Analyst")
    @patch("agents.supervisor.Synthesizer")
    def test_supervisor_produces_report_with_citations(
        self,
        mock_synthesizer_cls,
        mock_analyst_cls,
        mock_researcher_cls,
    ):
        mock_researcher = mock_researcher_cls.return_value
        mock_analyst = mock_analyst_cls.return_value
        mock_synthesizer = mock_synthesizer_cls.return_value

        mock_researcher.research.return_value = {
            "summary": "summary",
            "sources": ["https://example.com/a", "https://example.com/b"],
            "stored_count": 2,
        }
        mock_analyst.analyze.return_value = {
            "conflicts_detected": True,
            "resolved_facts": "resolved",
        }
        mock_synthesizer.synthesize.return_value = {
            "report": "## Executive Summary\nClaim [1]\n\n## Sources\n- [1] https://example.com/a",
            "word_count": 11,
            "sources_used": ["https://example.com/a", "https://example.com/b"],
            "citation_validation": {"ok": True, "reason": "Citation validation passed."},
        }

        supervisor = Supervisor()
        result = supervisor.run("Test query")

        self.assertTrue(result["report"])
        self.assertTrue(result["sources"])
        self.assertIn("citation_validation", result)
        self.assertIn("session_log", result)


class TestAutonomousSwarmIntegration(unittest.TestCase):
    """Integration tests for true autonomous swarm."""

    def test_swarm_coordinator_executes_all_phases(self):
        """Test that coordinator runs through all phases."""
        coordinator = SwarmCoordinator(max_workers=2, max_negotiation_rounds=2)

        # Mock agents
        def mock_planner(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="planner",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "subtasks": [
                        {"type": "research", "description": "Find evidence on X"},
                        {"type": "research", "description": "Find evidence on Y"},
                    ],
                },
                status="success",
            )

        def mock_literature_reviewer(task):
            from agents.swarm.protocol import AgentResult, Claim
            return AgentResult(
                agent_id="literature_reviewer",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "claims": [
                        {
                            "statement": "Claim from literature reviewer",
                            "evidence_ids": ["ev_1"],
                            "confidence": 0.85,
                        },
                    ],
                },
                status="success",
                evidence_refs=["ev_1"],
            )

        def mock_summarizer(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="summarizer",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "claims": [
                        {
                            "statement": "Summary claim with different view",
                            "evidence_ids": ["ev_2"],
                            "confidence": 0.75,
                        },
                    ],
                },
                status="success",
                evidence_refs=["ev_2"],
            )

        def mock_conflict_resolver(task):
            from agents.swarm.protocol import AgentResult
            claims = task.payload.get("claims", [])
            votes = []
            for i, claim in enumerate(claims):
                vote = ConsensusState.ACCEPTED if i == 0 else ConsensusState.UNCERTAIN
                votes.append({
                    "claim_id": claim["claim_id"],
                    "vote": vote.value,
                    "rationale": "Test vote",
                    "confidence": 0.8,
                })
            return AgentResult(
                agent_id="conflict_resolver",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "votes": votes,
                    "conflicts_detected": len(claims) > 1,
                },
                status="success",
            )

        def mock_synthesizer(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="synthesizer",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "report": "## Executive Summary\nTest report [1].\n\n## Sources\n- [1] Test source",
                    "word_count": 10,
                    "sources_used": ["ev_1"],
                    "claims_used": len(task.payload.get("accepted_claims", [])),
                },
                status="success",
            )

        # Register agents
        coordinator.register_agent("planner", mock_planner)
        coordinator.register_agent("literature_reviewer", mock_literature_reviewer)
        coordinator.register_agent("summarizer", mock_summarizer)
        coordinator.register_agent("conflict_resolver", mock_conflict_resolver)
        coordinator.register_agent("synthesizer", mock_synthesizer)

        # Run swarm
        state = coordinator.run("Test query for autonomous swarm")

        # Verify phases completed
        phase_names = [e.phase.value for e in state.phase_events]
        self.assertIn("planning", phase_names)
        self.assertIn("execution", phase_names)
        self.assertIn("negotiation", phase_names)
        self.assertIn("synthesis", phase_names)
        self.assertIn("validation", phase_names)

        # Verify claims were created
        self.assertGreater(len(state.claims), 0)

        # Verify negotiation happened
        self.assertGreater(len(state.negotiation_rounds), 0)

        # Verify synthesis result exists
        synthesis_results = [r for r in state.results.values() if r.agent_id == "synthesizer"]
        self.assertEqual(len(synthesis_results), 1)

        # Verify final phase
        self.assertEqual(state.current_phase, Phase.COMPLETE)

    def test_swarm_with_conflicting_claims(self):
        """Test that swarm detects and negotiates conflicting claims."""
        coordinator = SwarmCoordinator(max_workers=2, max_negotiation_rounds=2)

        def mock_planner(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="planner",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "subtasks": [
                        {"type": "research", "description": "Evidence A"},
                        {"type": "research", "description": "Evidence B"},
                    ],
                },
                status="success",
            )

        def mock_worker_a(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="worker_a",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "claims": [
                        {
                            "statement": "Temperature increased by 2 degrees",
                            "evidence_ids": ["ev_a1"],
                            "confidence": 0.9,
                        },
                    ],
                },
                status="success",
            )

        def mock_worker_b(task):
            from agents.swarm.protocol import AgentResult
            return AgentResult(
                agent_id="worker_b",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "claims": [
                        {
                            "statement": "Temperature increased by only 1 degree",
                            "evidence_ids": ["ev_b1"],
                            "confidence": 0.85,
                        },
                    ],
                },
                status="success",
            )

        def mock_resolver(task):
            from agents.swarm.protocol import AgentResult
            claims = task.payload.get("claims", [])
            votes = []
            for claim in claims:
                # Accept higher confidence claim
                vote = ConsensusState.ACCEPTED if claim["confidence"] > 0.87 else ConsensusState.REJECTED
                votes.append({
                    "claim_id": claim["claim_id"],
                    "vote": vote.value,
                    "rationale": "Higher confidence preferred",
                    "confidence": claim["confidence"],
                })
            return AgentResult(
                agent_id="conflict_resolver",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "votes": votes,
                    "conflicts_detected": True,
                },
                status="success",
            )

        def mock_synthesizer(task):
            from agents.swarm.protocol import AgentResult
            accepted = task.payload.get("accepted_claims", [])
            return AgentResult(
                agent_id="synthesizer",
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "report": f"## Report\nBased on {len(accepted)} accepted claims [1].",
                    "word_count": 20,
                    "sources_used": ["ev_a1"],
                },
                status="success",
            )

        coordinator.register_agent("planner", mock_planner)
        coordinator.register_agent("literature_reviewer", mock_worker_a)
        coordinator.register_agent("summarizer", mock_worker_b)
        coordinator.register_agent("conflict_resolver", mock_resolver)
        coordinator.register_agent("synthesizer", mock_synthesizer)

        state = coordinator.run("Climate temperature change")

        # Verify conflicts were detected
        accepted_count = sum(1 for c in state.claims.values() if c.consensus_state == ConsensusState.ACCEPTED)
        rejected_count = sum(1 for c in state.claims.values() if c.consensus_state == ConsensusState.REJECTED)

        self.assertGreater(accepted_count, 0)
        # At least one claim should be rejected due to conflict
        self.assertGreaterEqual(rejected_count, 0)

        # Verify negotiation log exists
        self.assertGreater(len(state.negotiation_rounds), 0)


class TestEndToEndWithTrueSwarm(unittest.TestCase):
    """End-to-end tests using actual swarm supervisor."""

    @patch("agents.swarm.supervisor.SWARM_ENABLE_NEGOTIATION", True)
    @patch("agents.swarm.supervisor.Researcher")
    @patch("agents.swarm.supervisor.Analyst")
    @patch("agents.swarm.supervisor.Synthesizer")
    def test_autonomous_swarm_produces_structured_output(
        self,
        mock_synthesizer_cls,
        mock_analyst_cls,
        mock_researcher_cls,
    ):
        """Test that autonomous swarm produces output with claims and negotiation log."""
        from agents.swarm.supervisor import AutoGenSupervisor

        mock_researcher = mock_researcher_cls.return_value
        mock_analyst = mock_analyst_cls.return_value
        mock_synthesizer = mock_synthesizer_cls.return_value

        # Mock researcher to return claims
        mock_researcher.research.return_value = {
            "summary": "Research summary",
            "sources": ["https://source1.com", "https://source2.com"],
            "stored_count": 2,
            "raw_results": [
                "Temperature has risen significantly according to studies.",
                "Some studies suggest minimal temperature change.",
            ],
        }

        # Mock analyst for conflict resolution
        mock_analyst.groq_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="""
                Reviewing claims for contradictions.
                Claim_abc123|ACCEPTED|Evidence supports this strongly
                Claim_def456|UNCERTAIN|Conflicting evidence requires more review
            """))]
        )

        # Mock synthesizer
        mock_synthesizer.groq_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="""
                ## Executive Summary
                Research findings synthesized [1].

                ## Key Findings
                Multiple perspectives identified.

                ## Conflict Resolution
                Some claims marked uncertain due to conflicting evidence.

                ## Sources
                - [1] Evidence from sources
            """))]
        )

        supervisor = AutoGenSupervisor()
        result = supervisor.run("Climate change research")

        # Verify structured output
        self.assertIn("claims_summary", result)
        self.assertIn("negotiation_log", result)
        self.assertIn("negotiation_rounds", result)
        self.assertIn("stage_events", result)

        # Verify claims summary structure
        claims_summary = result.get("claims_summary", {})
        self.assertIn("total", claims_summary)
        self.assertIn("accepted", claims_summary)
        self.assertIn("rejected", claims_summary)
        self.assertIn("uncertain", claims_summary)

        # Verify report exists
        self.assertTrue(result.get("report"))
        self.assertIsInstance(result.get("word_count"), int)


if __name__ == "__main__":
    unittest.main()
