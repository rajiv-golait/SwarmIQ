"""LangGraph TypedDict state for SwarmIQ pipeline.

operator.add on list fields means parallel branches safely append
without overwriting each other. LangGraph merges them automatically.
"""
from __future__ import annotations
from typing import TypedDict, Annotated
import operator


class ResearchQuestion(TypedDict):
    question_id:    str
    text:           str
    search_queries: list[str]
    answered:       bool


class EvidenceChunk(TypedDict):
    chunk_id:       str
    content:        str
    source_url:     str
    source_domain:  str
    published_date: str
    agent_id:       str
    confidence:     float
    question_id:    str


class Claim(TypedDict):
    claim_id:           str
    statement:          str
    agent_id:           str
    evidence_chunk_ids: list[str]
    confidence:         float
    consensus_state:    str    # pending/accepted/rejected/uncertain
    vote_rationale:     str


class NegotiationRound(TypedDict):
    round_number:    int
    claims_reviewed: list[str]
    outcomes:        dict[str, str]
    unresolved:      list[str]


class SwarmState(TypedDict):
    # Input
    query:   str
    run_id:  str

    # Planning
    research_questions:   list[ResearchQuestion]

    # Evidence — operator.add means parallel branches merge their lists
    evidence_chunks: Annotated[list[EvidenceChunk], operator.add]
    claims:          Annotated[list[Claim],          operator.add]

    # After negotiation
    accepted_claims:  list[Claim]
    rejected_claims:  list[Claim]
    uncertain_claims: list[Claim]
    negotiation_rounds: list[NegotiationRound]

    # Gap detection loop control
    unanswered_questions: list[ResearchQuestion]
    research_iteration:   int

    # Synthesis
    report:       str
    word_count:   int
    sources_used: list[str]

    # Critique loop control
    coherence_score:   float
    critique_issues:   list[str]
    critique_revision: int

    # Visualization
    visualization: dict

    # Observability — operator.add merges from parallel branches
    phase_log: Annotated[list[str], operator.add]
    errors:    Annotated[list[str], operator.add]
