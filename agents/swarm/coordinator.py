from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from typing import Any, Callable

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
    PhaseEvent,
    SwarmState,
)


class SwarmCoordinator:
    """Coordinates autonomous agent team execution with phase-based state machine."""

    def __init__(
        self,
        max_workers: int = 3,
        consensus_threshold: float = 0.6,
        max_negotiation_rounds: int = 3,
    ):
        self.max_workers = max_workers
        self.consensus_threshold = consensus_threshold
        self.max_negotiation_rounds = max_negotiation_rounds
        self.agents: dict[str, Callable[[AgentTask], AgentResult]] = {}
        self.state: SwarmState | None = None
        self.message_handlers: dict[MessageType, list[Callable]] = {}

    def register_agent(
        self, agent_id: str, handler: Callable[[AgentTask], AgentResult]
    ) -> None:
        """Register an agent with its task handler."""
        self.agents[agent_id] = handler

    def on_message(self, message_type: MessageType) -> Callable:
        """Decorator for message handlers."""
        def decorator(func: Callable):
            if message_type not in self.message_handlers:
                self.message_handlers[message_type] = []
            self.message_handlers[message_type].append(func)
            return func
        return decorator

    def broadcast(self, sender_id: str, message_type: MessageType, content: dict[str, Any]) -> None:
        """Broadcast a message to all agents."""
        message = AgentMessage(sender_id=sender_id, message_type=message_type, content=content)
        if self.state:
            self.state.messages.append(message)
        # Notify handlers
        handlers = self.message_handlers.get(message_type, [])
        for handler in handlers:
            try:
                handler(message)
            except Exception as e:
                if self.state:
                    self.state.errors.append(f"Handler error: {e}")

    def _emit_phase_event(self, phase: Phase, message: str, agent_id: str | None = None, details: dict | None = None) -> None:
        """Record a phase transition event."""
        if self.state:
            event = PhaseEvent(
                phase=phase,
                message=message,
                agent_id=agent_id,
                details=details or {},
            )
            self.state.phase_events.append(event)
            self.state.current_phase = phase

    def _generate_task_id(self, agent_id: str, phase: Phase) -> str:
        """Generate deterministic task ID."""
        nonce = uuid.uuid4().hex[:8]
        return hashlib.sha256(f"{agent_id}:{phase.value}:{nonce}".encode()).hexdigest()[:16]

    def _generate_claim_id(self, agent_id: str, statement: str) -> str:
        """Generate deterministic claim ID."""
        return hashlib.sha256(f"{agent_id}:{statement[:100]}".encode()).hexdigest()[:16]

    def run(self, query: str) -> SwarmState:
        """Execute full swarm workflow with parallel agents."""
        self.state = SwarmState(query=query, current_phase=Phase.PLANNING)

        # Phase 1: Planning
        self._run_planning_phase()

        # Phase 2: Parallel Execution
        self._run_execution_phase()

        # Phase 3: Negotiation (if conflicts exist)
        self._run_negotiation_phase()

        # Phase 4: Synthesis
        self._run_synthesis_phase()

        # Phase 5: Validation
        self._run_validation_phase()

        return self.state

    def _run_planning_phase(self) -> None:
        """Planner creates tasks and subtasks."""
        self._emit_phase_event(Phase.PLANNING, "Planner started task decomposition")

        # Create planning task for the planner agent
        planner_id = "planner"
        if planner_id not in self.agents:
            raise RuntimeError("Planner agent not registered")

        task_id = self._generate_task_id(planner_id, Phase.PLANNING)
        task = AgentTask(
            task_id=task_id,
            agent_id=planner_id,
            phase=Phase.PLANNING,
            instruction="Decompose query into parallel subtasks",
            payload={"query": self.state.query if self.state else ""},
        )

        if self.state:
            self.state.tasks[task_id] = task

        # Execute planning
        result = self.agents[planner_id](task)

        if self.state:
            self.state.results[task_id] = result

        subtasks = result.content.get("subtasks", [])
        self._emit_phase_event(
            Phase.PLANNING,
            f"Planner produced {len(subtasks)} subtasks",
            planner_id,
            {"subtask_count": len(subtasks)},
        )

        # Broadcast planning complete
        self.broadcast(
            planner_id,
            MessageType.PHASE_TRANSITION,
            {"phase": Phase.EXECUTION.value, "subtasks": subtasks},
        )

    def _run_execution_phase(self) -> None:
        """Execute subtasks in parallel across multiple agents."""
        self._emit_phase_event(Phase.EXECUTION, "Starting parallel worker execution")

        # Get subtasks from planning result
        planner_result = None
        for task_id, result in (self.state.results.items() if self.state else []):
            if result.agent_id == "planner":
                planner_result = result
                break

        if not planner_result:
            self._emit_phase_event(Phase.EXECUTION, "No planning result found", details={"error": True})
            return

        subtasks = planner_result.content.get("subtasks", [])

        # Create tasks for parallel workers
        worker_tasks = []
        for i, subtask in enumerate(subtasks):
            # Literature reviewer for odd indices, summarizer for even
            agent_id = "literature_reviewer" if i % 2 == 0 else "summarizer"
            if agent_id not in self.agents:
                continue

            task_id = self._generate_task_id(agent_id, Phase.EXECUTION)
            task = AgentTask(
                task_id=task_id,
                agent_id=agent_id,
                phase=Phase.EXECUTION,
                instruction=f"Execute: {subtask}",
                payload={
                    "query": self.state.query if self.state else "",
                    "subtask": subtask,
                    "subtask_index": i,
                },
            )
            worker_tasks.append((task_id, agent_id, task))
            if self.state:
                self.state.tasks[task_id] = task

        if not worker_tasks:
            self._emit_phase_event(Phase.EXECUTION, "No worker tasks created")
            return

        # Execute workers in parallel
        claims_created = []
        evidence_maps = {}  # Aggregate evidence maps from all workers
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.agents[agent_id], task): (task_id, agent_id)
                for task_id, agent_id, task in worker_tasks
            }

            for future in as_completed(futures):
                task_id, agent_id = futures[future]
                try:
                    result = future.result()
                    if self.state:
                        self.state.results[task_id] = result

                    # Aggregate evidence_map from this worker
                    worker_evidence_map = result.content.get("evidence_map", {})
                    if worker_evidence_map:
                        evidence_maps.update(worker_evidence_map)

                    # Convert results to claims
                    raw_claims = result.content.get("claims", [])
                    for claim_data in raw_claims:
                        claim = Claim(
                            claim_id=self._generate_claim_id(agent_id, claim_data["statement"]),
                            agent_id=agent_id,
                            statement=claim_data["statement"],
                            evidence_chunk_ids=claim_data.get("evidence_ids", []),
                            confidence=claim_data.get("confidence", 0.8),
                        )
                        if self.state:
                            self.state.claims[claim.claim_id] = claim
                        claims_created.append(claim.claim_id)

                    self._emit_phase_event(
                        Phase.EXECUTION,
                        f"Worker {agent_id} completed task",
                        agent_id,
                        {"task_id": task_id, "claims_count": len(raw_claims)},
                    )
                except Exception as e:
                    if self.state:
                        self.state.errors.append(f"Worker {agent_id} failed: {e}")

        # Store aggregated evidence map in state
        if self.state:
            self.state.evidence_map = evidence_maps

        self._emit_phase_event(
            Phase.EXECUTION,
            f"Parallel execution complete. {len(claims_created)} claims created, {len(evidence_maps)} evidence chunks",
            details={"claims_created": claims_created, "evidence_chunks": len(evidence_maps)},
        )

        # Broadcast execution complete
        self.broadcast(
            "coordinator",
            MessageType.PHASE_TRANSITION,
            {"phase": Phase.NEGOTIATION.value, "claims_count": len(claims_created)},
        )

    def _run_negotiation_phase(self) -> None:
        """Multi-round negotiation to resolve conflicting claims."""
        if not self.state or not self.state.claims:
            self._emit_phase_event(Phase.NEGOTIATION, "No claims to negotiate")
            return

        self._emit_phase_event(Phase.NEGOTIATION, "Starting conflict resolution negotiation")

        # Get conflict resolver agent
        resolver_id = "conflict_resolver"
        if resolver_id not in self.agents:
            self._emit_phase_event(Phase.NEGOTIATION, "No conflict resolver available")
            return

        pending_claims = [
            cid for cid, claim in self.state.claims.items()
            if claim.consensus_state == ConsensusState.PENDING
        ]

        for round_num in range(1, self.max_negotiation_rounds + 1):
            if not pending_claims:
                break

            self._emit_phase_event(
                Phase.NEGOTIATION,
                f"Negotiation round {round_num} started",
                details={"claims_to_review": pending_claims},
            )

            # Create negotiation task
            task_id = self._generate_task_id(resolver_id, Phase.NEGOTIATION)
            task = AgentTask(
                task_id=task_id,
                agent_id=resolver_id,
                phase=Phase.NEGOTIATION,
                instruction=f"Round {round_num}: Review and vote on pending claims",
                payload={
                    "claims": [
                        {
                            "claim_id": cid,
                            "statement": self.state.claims[cid].statement,
                            "agent_id": self.state.claims[cid].agent_id,
                            "confidence": self.state.claims[cid].confidence,
                            "evidence_ids": self.state.claims[cid].evidence_chunk_ids,
                        }
                        for cid in pending_claims
                    ],
                    "round": round_num,
                },
            )

            # Run conflict resolution
            result = self.agents[resolver_id](task)

            # Process votes
            votes_data = result.content.get("votes", [])
            round_votes = []
            outcomes = {}

            for vote_data in votes_data:
                vote = ConsensusVote(
                    claim_id=vote_data["claim_id"],
                    voter_id=resolver_id,
                    vote=ConsensusState(vote_data["vote"]),
                    rationale=vote_data.get("rationale", ""),
                    confidence=vote_data.get("confidence", 0.5),
                )
                round_votes.append(vote)
                if self.state:
                    self.state.votes.append(vote)

                # Update claim state
                claim_id = vote.claim_id
                if claim_id in self.state.claims:
                    self.state.claims[claim_id].consensus_state = vote.vote
                    outcomes[claim_id] = vote.vote

            # Track unresolved claims
            unresolved = [
                cid for cid in pending_claims
                if cid not in outcomes or outcomes[cid] == ConsensusState.PENDING
            ]

            negotiation_round = NegotiationRound(
                round_number=round_num,
                claims_challenged=pending_claims,
                votes=round_votes,
                outcomes=outcomes,
                unresolved=unresolved,
            )
            self.state.negotiation_rounds.append(negotiation_round)

            self._emit_phase_event(
                Phase.NEGOTIATION,
                f"Round {round_num} complete",
                resolver_id,
                {
                    "votes_cast": len(round_votes),
                    "resolved": len(outcomes),
                    "unresolved": len(unresolved),
                },
            )

            pending_claims = unresolved

        # Final status
        final_states = {
            "accepted": sum(1 for c in self.state.claims.values() if c.consensus_state == ConsensusState.ACCEPTED),
            "rejected": sum(1 for c in self.state.claims.values() if c.consensus_state == ConsensusState.REJECTED),
            "uncertain": sum(1 for c in self.state.claims.values() if c.consensus_state == ConsensusState.UNCERTAIN),
        }

        self._emit_phase_event(
            Phase.NEGOTIATION,
            f"Negotiation complete: {final_states['accepted']} accepted, "
            f"{final_states['rejected']} rejected, {final_states['uncertain']} uncertain",
            details=final_states,
        )

        # Broadcast negotiation complete
        self.broadcast(
            resolver_id,
            MessageType.PHASE_TRANSITION,
            {"phase": Phase.SYNTHESIS.value, "final_states": final_states},
        )

    def _run_synthesis_phase(self) -> None:
        """Synthesize final report from consensus-approved claims."""
        self._emit_phase_event(Phase.SYNTHESIS, "Starting synthesis from approved claims")

        synthesizer_id = "synthesizer"
        if synthesizer_id not in self.agents:
            self._emit_phase_event(Phase.SYNTHESIS, "No synthesizer available")
            return

        # Get accepted claims
        accepted_claims = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "agent_id": c.agent_id,
                "evidence_chunk_ids": c.evidence_chunk_ids,
                "confidence": c.confidence,
            }
            for c in (self.state.claims.values() if self.state else [])
            if c.consensus_state == ConsensusState.ACCEPTED
        ]

        uncertain_claims = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "agent_id": c.agent_id,
            }
            for c in (self.state.claims.values() if self.state else [])
            if c.consensus_state == ConsensusState.UNCERTAIN
        ]

        task_id = self._generate_task_id(synthesizer_id, Phase.SYNTHESIS)
        task = AgentTask(
            task_id=task_id,
            agent_id=synthesizer_id,
            phase=Phase.SYNTHESIS,
            instruction="Synthesize final report from consensus-approved claims",
            payload={
                "query": self.state.query if self.state else "",
                "accepted_claims": accepted_claims,
                "uncertain_claims": uncertain_claims,
                "negotiation_rounds": len(self.state.negotiation_rounds) if self.state else 0,
                "evidence_map": self.state.evidence_map if self.state else {},  # Pass real evidence metadata
            },
        )

        result = self.agents[synthesizer_id](task)

        if self.state:
            self.state.results[task_id] = result

        self._emit_phase_event(
            Phase.SYNTHESIS,
            f"Synthesis complete: {result.content.get('word_count', 0)} words",
            synthesizer_id,
            {
                "report_length": len(result.content.get("report", "")),
                "sources_count": len(result.content.get("sources_used", [])),
            },
        )

        # Broadcast synthesis complete
        self.broadcast(
            synthesizer_id,
            MessageType.PHASE_TRANSITION,
            {"phase": Phase.VALIDATION.value, "word_count": result.content.get("word_count", 0)},
        )

    def _run_validation_phase(self) -> None:
        """Validate final output against claim-level grounding and consensus alignment."""
        from agents.swarm.validator import ClaimValidator, CitationGroundingValidator

        self._emit_phase_event(Phase.VALIDATION, "Running claim-level validation gates")

        # Find synthesis result
        synthesis_result = None
        for result in (self.state.results.values() if self.state else []):
            if result.agent_id == "synthesizer" and result.phase == Phase.SYNTHESIS:
                synthesis_result = result
                break

        if not synthesis_result:
            if self.state:
                self.state.errors.append("No synthesis result found for validation")
            return

        report = synthesis_result.content.get("report", "")

        # Get accepted and uncertain claims
        accepted_claims = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "confidence": c.confidence,
                "evidence_chunk_ids": c.evidence_chunk_ids,
            }
            for c in (self.state.claims.values() if self.state else [])
            if c.consensus_state == ConsensusState.ACCEPTED
        ]

        uncertain_claims = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
            }
            for c in (self.state.claims.values() if self.state else [])
            if c.consensus_state == ConsensusState.UNCERTAIN
        ]

        # Build evidence lookup from memory store
        evidence_lookup = {}
        for claim in accepted_claims:
            for i, ev_id in enumerate(claim.get("evidence_chunk_ids", []), 1):
                evidence_lookup[str(i)] = ev_id

        # Run claim-level validation
        from agents.swarm.validator import ClaimValidator, CitationReferenceValidator
        validator = ClaimValidator()
        claim_validation = validator.validate_report(report, accepted_claims, evidence_lookup)

        # Run consensus alignment validation
        consensus_validation = validator.validate_consensus_alignment(
            report, accepted_claims, uncertain_claims
        )

        # Run citation reference validation (check [n] citations map to real URLs)
        ref_validator = CitationReferenceValidator()
        citation_validation = ref_validator.validate_citation_consistency(report)

        # Combined validation result
        validation_passed = (
            claim_validation["passed"]
            and consensus_validation["passed"]
            and citation_validation["passed"]
        )

        self._emit_phase_event(
            Phase.VALIDATION,
            f"Validation complete: {claim_validation['verified_claims']} verified, "
            f"{claim_validation['unverified_claims']} unverified, "
            f"{citation_validation['valid_mappings']} citations match references",
            details={
                "passed": validation_passed,
                "claim_validation": claim_validation,
                "consensus_validation": consensus_validation,
                "citation_validation": citation_validation,
                "report_length": len(report),
                "word_count": synthesis_result.content.get("word_count", 0),
            },
        )

        # Store validation results in state
        if self.state:
            self.state.results["validation"] = AgentResult(
                agent_id="validator",
                phase=Phase.VALIDATION,
                task_id="validation_task",
                content={
                    "claim_validation": claim_validation,
                    "consensus_validation": consensus_validation,
                    "citation_validation": citation_validation,
                    "passed": validation_passed,
                    "reference_count": citation_validation.get("references_parsed", 0),
                },
                notes="Citation and claim validation completed",
                status="success" if validation_passed else "partial",
            )

        # Emit completion phase
        self._emit_phase_event(
            Phase.COMPLETE,
            f"Swarm execution complete. {len(self.state.claims if self.state else [])} claims processed, "
            f"{len(self.state.negotiation_rounds if self.state else [])} negotiation rounds.",
            details={
                "validation_passed": validation_passed,
                "total_claims": len(self.state.claims) if self.state else 0,
                "total_rounds": len(self.state.negotiation_rounds) if self.state else 0,
            },
        )

        # Broadcast completion
        self.broadcast(
            "coordinator",
            MessageType.FINALIZE,
            {
                "phase": Phase.COMPLETE.value,
                "validation_passed": validation_passed,
                "total_claims": len(self.state.claims) if self.state else 0,
                "total_rounds": len(self.state.negotiation_rounds) if self.state else 0,
                "claim_validation": {
                    "verified": claim_validation["verified_claims"],
                    "unverified": claim_validation["unverified_claims"],
                },
            },
        )

    def get_summary(self) -> dict[str, Any]:
        """Get execution summary."""
        if not self.state:
            return {}

        return {
            "query": self.state.query,
            "current_phase": self.state.current_phase.value,
            "total_tasks": len(self.state.tasks),
            "total_results": len(self.state.results),
            "total_claims": len(self.state.claims),
            "total_votes": len(self.state.votes),
            "negotiation_rounds": len(self.state.negotiation_rounds),
            "phase_events": [asdict(e) for e in self.state.phase_events],
            "errors": self.state.errors,
            "final_report": self._get_final_report(),
        }

    def _get_final_report(self) -> str:
        """Extract final report from synthesis result."""
        for result in (self.state.results.values() if self.state else []):
            if result.agent_id == "synthesizer" and result.phase == Phase.SYNTHESIS:
                return result.content.get("report", "")
        return ""
