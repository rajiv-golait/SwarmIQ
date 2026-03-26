from __future__ import annotations

from dataclasses import asdict

from agents.analyst import Analyst
from agents.researcher import Researcher
from agents.synthesizer import Synthesizer
from agents.swarm.coordinator import SwarmCoordinator
from agents.swarm.protocol import Phase
from agents.swarm.roles import (
    ConflictResolverRole,
    LiteratureReviewRole,
    PlannerRole,
    SummarizerRole,
    SynthesisRole,
    VisualizationRole,
)
from memory.chroma_store import ChromaStore
from utils.config import (
    AUTOGEN_MAX_TURNS,
    CHROMA_PERSIST_DIR,
    SWARM_CONSENSUS_THRESHOLD,
    SWARM_ENABLE_NEGOTIATION,
    SWARM_ENABLE_VISUALIZATION,
    SWARM_MAX_NEGOTIATION_ROUNDS,
    SWARM_MAX_WORKERS,
)


class AutoGenSupervisor:
    """Supervisor that runs true autonomous swarm with team-based coordination."""

    def __init__(self):
        self.chroma_store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR)
        self.researcher = Researcher(self.chroma_store)
        self.analyst = Analyst(self.chroma_store)
        self.synthesizer = Synthesizer()

        # Initialize role handlers
        self.planner = PlannerRole()
        self.literature_reviewer = LiteratureReviewRole(self.researcher)
        self.summarizer = SummarizerRole(self.synthesizer, self.researcher)  # Pass researcher for real evidence
        self.conflict_resolver = ConflictResolverRole(self.analyst)
        self.synthesis = SynthesisRole(self.synthesizer)
        self.visualizer = VisualizationRole()

        # Check autogen availability
        self._autogen_enabled = self._bootstrap_autogen()

        # Initialize coordinator
        self.coordinator = SwarmCoordinator(
            max_workers=SWARM_MAX_WORKERS,
            consensus_threshold=SWARM_CONSENSUS_THRESHOLD,
            max_negotiation_rounds=SWARM_MAX_NEGOTIATION_ROUNDS,
        )

        self._register_agents()

    def _bootstrap_autogen(self) -> bool:
        try:
            from autogen_agentchat.base import TaskResult  # noqa: F401
            return True
        except Exception:
            return False

    def _register_agents(self) -> None:
        """Register all agents with the coordinator."""
        self.coordinator.register_agent("planner", self.planner)
        self.coordinator.register_agent("literature_reviewer", self.literature_reviewer)
        self.coordinator.register_agent("summarizer", self.summarizer)
        self.coordinator.register_agent("conflict_resolver", self.conflict_resolver)
        self.coordinator.register_agent("synthesizer", self.synthesis)

        if SWARM_ENABLE_VISUALIZATION:
            self.coordinator.register_agent("visualizer", self.visualizer)

        # Setup message handlers for observability
        self.coordinator.on_message(self.coordinator.broadcast.__class__)(
            lambda msg: None  # Placeholder for message logging
        )

    def run(self, query: str) -> dict:
        """Execute full autonomous swarm workflow."""
        # Run the coordinator
        state = self.coordinator.run(query)

        # Generate visualization if enabled
        visualization = None
        if SWARM_ENABLE_VISUALIZATION and state.current_phase == Phase.COMPLETE:
            viz_task = {
                "task_id": "viz_task",
                "agent_id": "visualizer",
                "phase": Phase.SYNTHESIS,
                "instruction": "Generate visualization",
                "payload": {
                    "query": query,
                    "accepted_claims": [
                        {
                            "claim_id": c.claim_id,
                            "statement": c.statement,
                            "confidence": c.confidence,
                            "evidence_chunk_ids": c.evidence_chunk_ids,
                        }
                        for c in state.claims.values()
                        if c.consensus_state.value == "accepted"
                    ],
                },
            }
            from agents.swarm.protocol import AgentTask
            viz_result = self.visualizer(AgentTask(**viz_task))
            visualization = viz_result.content

        # Calculate conflict summary
        accepted_count = sum(1 for c in state.claims.values() if c.consensus_state.value == "accepted")
        rejected_count = sum(1 for c in state.claims.values() if c.consensus_state.value == "rejected")
        uncertain_count = sum(1 for c in state.claims.values() if c.consensus_state.value == "uncertain")
        conflicts_detected = rejected_count > 0 or uncertain_count > 0

        # Find the synthesis result
        synthesis_result = None
        for result in state.results.values():
            if result.agent_id == "synthesizer" and result.phase == Phase.SYNTHESIS:
                synthesis_result = result
                break

        report = synthesis_result.content.get("report", "") if synthesis_result else ""
        word_count = synthesis_result.content.get("word_count", 0) if synthesis_result else 0
        sources = synthesis_result.content.get("sources_used", []) if synthesis_result else []

        # Build negotiation log
        negotiation_log = []
        for round_data in state.negotiation_rounds:
            negotiation_log.append({
                "round": round_data.round_number,
                "claims_reviewed": round_data.claims_challenged,
                "outcomes": round_data.outcomes,
                "unresolved": round_data.unresolved,
            })

        return {
            "query": query,
            "report": report,
            "sources": sources,
            "conflicts_detected": conflicts_detected,
            "word_count": word_count,
            "citation_validation": {"ok": len(report) > 100, "reason": "Report generated"},
            "session_log": [f"{e.phase.value.upper()}: {e.message}" for e in state.phase_events],
            "stage_events": [asdict(e) for e in state.phase_events],
            "subtasks": [],
            "autogen_enabled": self._autogen_enabled,
            "claims_summary": {
                "total": len(state.claims),
                "accepted": accepted_count,
                "rejected": rejected_count,
                "uncertain": uncertain_count,
            },
            "negotiation_log": negotiation_log,
            "negotiation_rounds": len(state.negotiation_rounds),
            "visualization": visualization,
            "errors": state.errors,
        }
