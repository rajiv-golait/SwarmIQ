from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class MessageType(Enum):
    TASK_ASSIGNMENT = "task_assignment"
    EVIDENCE_CLAIM = "evidence_claim"
    CHALLENGE = "challenge"
    CONSENSUS_VOTE = "consensus_vote"
    FINALIZE = "finalize"
    PHASE_TRANSITION = "phase_transition"
    STATUS_UPDATE = "status_update"


class Phase(Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    NEGOTIATION = "negotiation"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    COMPLETE = "complete"


class ConsensusState(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"
    PENDING = "pending"


@dataclass
class AgentMessage:
    """Message passed between agents in the swarm."""
    sender_id: str
    message_type: MessageType
    content: dict[str, Any]
    recipient_id: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    message_id: str = field(default_factory=lambda: f"msg_{datetime.now(timezone.utc).timestamp()}")


@dataclass
class AgentTask:
    task_id: str
    agent_id: str
    phase: Phase
    instruction: str
    payload: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class AgentResult:
    agent_id: str
    phase: Phase
    task_id: str
    content: dict[str, Any]
    notes: str = ""
    status: Literal["success", "failure", "partial"] = "success"
    evidence_refs: list[str] = field(default_factory=list)
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class Claim:
    """A claim made by an agent with evidence backing."""
    claim_id: str
    agent_id: str
    statement: str
    evidence_chunk_ids: list[str]
    confidence: float
    consensus_state: ConsensusState = ConsensusState.PENDING
    parent_claim_id: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class ConsensusVote:
    """A vote on a claim during negotiation."""
    claim_id: str
    voter_id: str
    vote: ConsensusState
    rationale: str
    confidence: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class PhaseEvent:
    phase: Phase
    message: str
    agent_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class NegotiationRound:
    round_number: int
    claims_challenged: list[str]
    votes: list[ConsensusVote]
    outcomes: dict[str, ConsensusState]
    unresolved: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class SwarmState:
    """Complete state of the swarm execution."""
    query: str
    current_phase: Phase
    messages: list[AgentMessage] = field(default_factory=list)
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    results: dict[str, AgentResult] = field(default_factory=dict)
    claims: dict[str, Claim] = field(default_factory=dict)
    votes: list[ConsensusVote] = field(default_factory=list)
    negotiation_rounds: list[NegotiationRound] = field(default_factory=list)
    phase_events: list[PhaseEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    evidence_map: dict[str, dict] = field(default_factory=dict)  # chunk_id -> {source_url, title, published_at, content}
