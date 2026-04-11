"""LangGraph state machine for SwarmIQ.

Replaces:
  agents/swarm/coordinator.py
  agents/swarm/supervisor.py
  agents/supervisor.py (legacy)

Fix from run fd92dd06a5ae:
  - Bug 9: 181 claims generated, 101 entered negotiation — 80 disappeared
    with no log entry. Added merge_and_validate node between detect_gaps
    and negotiate to deduplicate claims and log the transition count.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from agents.state import SwarmState
from agents.roles.planner             import PlannerNode
from agents.roles.literature_reviewer import LiteratureReviewNode
from agents.roles.summarizer          import SummarizerNode
from agents.roles.conflict_resolver   import ConflictResolverNode
from agents.roles.synthesizer         import SynthesizerNode
from agents.critic       import CriticNode
from agents.gap_detector import GapDetectorNode
from memory.lance_store  import LanceStore
from utils.progress import set_progress_callback
from utils.config import (
    MAX_RESEARCH_ITERATIONS,
    MAX_CRITIQUE_REVISIONS,
    SWARM_ENABLE_VISUALIZATION,
    COHERENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _fan_out_to_research(state: SwarmState) -> list:
    """Fan-out: send state to both research branches in parallel.

    FIX: Previous plan had add_edge("plan","literature_review") and
    add_edge("plan","summarize") which does NOT guarantee both complete
    before detect_gaps fires. Send API with operator.add reducers is
    the correct LangGraph pattern for parallel fan-out + fan-in.
    """
    return [
        Send("literature_review", state),
        Send("summarize", state),
    ]


def _should_research_more(state: SwarmState) -> str:
    has_gaps    = bool(state.get("unanswered_questions"))
    under_limit = state.get("research_iteration", 0) < MAX_RESEARCH_ITERATIONS
    if has_gaps and under_limit:
        logger.info(f"Gap detected — re-searching (iter {state['research_iteration']})")
        return "research_more"
    return "proceed"


def _should_revise(state: SwarmState) -> str:
    score       = state.get("coherence_score", 0.0)
    revision    = state.get("critique_revision", 0)
    has_issues  = bool(state.get("critique_issues"))
    under_limit = revision < MAX_CRITIQUE_REVISIONS

    if has_issues and under_limit and score < COHERENCE_THRESHOLD:
        logger.info(
            f"Critique failed (score={score:.2f}) — revising "
            f"({revision + 1}/{MAX_CRITIQUE_REVISIONS})"
        )
        return "revise"
    logger.info(f"Critique passed or max revisions reached (score={score:.2f})")
    return "finish"


def _merge_and_validate(state: SwarmState) -> dict:
    """Audit claims before negotiation — logs duplicate claim_id density.

    Does **not** return ``claims``: ``SwarmState.claims`` uses ``operator.add``,
    so emitting a deduped list here would *append* it to the accumulated list
    and duplicate every row.  ``ConflictResolverNode.run`` deduplicates by
    ``claim_id`` at negotiation entry instead.
    """
    claims   = state.get("claims", [])
    evidence = state.get("evidence_chunks", [])

    seen: set[str] = set()
    unique_count = 0
    for c in claims:
        cid = c.get("claim_id", "")
        if cid and cid not in seen:
            seen.add(cid)
            unique_count += 1

    removed = len(claims) - unique_count
    log = (
        f"[Merge] {len(claims)} claim rows, {unique_count} unique claim_ids "
        f"({removed} duplicate rows by id) | {len(evidence)} evidence chunks"
    )
    logger.info(log)

    return {"phase_log": [log]}


def build_graph(store: LanceStore):
    planner     = PlannerNode(store)
    lit_review  = LiteratureReviewNode(store)
    summarizer  = SummarizerNode(store)
    gap_detect  = GapDetectorNode()
    negotiator  = ConflictResolverNode(store)
    synthesizer = SynthesizerNode(store)
    critic      = CriticNode()

    g = StateGraph(SwarmState)

    g.add_node("plan",               planner.run)
    g.add_node("literature_review",  lit_review.run)
    g.add_node("summarize",          summarizer.run)
    g.add_node("detect_gaps",        gap_detect.run)
    g.add_node("merge_and_validate", _merge_and_validate)
    g.add_node("negotiate",          negotiator.run)
    g.add_node("synthesize",         synthesizer.run)
    g.add_node("critique",           critic.run)

    g.set_entry_point("plan")

    # Fan-out from plan → both research branches in parallel
    g.add_conditional_edges("plan", _fan_out_to_research)

    # Both branches fan-in to detect_gaps (operator.add merges their lists)
    g.add_edge("literature_review", "detect_gaps")
    g.add_edge("summarize",         "detect_gaps")

    # Gap loop — "proceed" now routes through merge_and_validate
    g.add_conditional_edges(
        "detect_gaps",
        _should_research_more,
        {"research_more": "plan", "proceed": "merge_and_validate"},
    )

    g.add_edge("merge_and_validate", "negotiate")
    g.add_edge("negotiate",          "synthesize")
    g.add_edge("synthesize",         "critique")

    # Critique loop
    g.add_conditional_edges(
        "critique",
        _should_revise,
        {"revise": "synthesize", "finish": END},
    )

    return g.compile()


def run_pipeline(
    query: str,
    event_callback: Callable[[str], None] | None = None,
) -> dict:
    """Execute the full research pipeline.

    FIX: Uses graph.stream(mode="updates") with delta merge loop.
    graph.stream() returns per-node DELTAS. Accumulating them manually
    gives us both streaming UI callbacks AND a complete final state.
    Previous plan's `final_state = node_state` would have lost all
    accumulated state from prior nodes.
    """
    store  = LanceStore()
    graph  = build_graph(store)
    run_id = uuid.uuid4().hex[:12]

    initial: SwarmState = {
        "query":                query,
        "run_id":               run_id,
        "research_questions":   [],
        "evidence_chunks":      [],
        "claims":               [],
        "accepted_claims":      [],
        "rejected_claims":      [],
        "uncertain_claims":     [],
        "negotiation_rounds":   [],
        "unanswered_questions": [],
        "research_iteration":   0,
        "report":               "",
        "word_count":           0,
        "sources_used":         [],
        "coherence_score":      0.0,
        "critique_issues":      [],
        "critique_revision":    0,
        "visualization":        {},
        "phase_log":            [],
        "errors":               [],
    }

    # Stream for UI callbacks while accumulating full final state via delta merge
    final_state = dict(initial)
    if event_callback:
        set_progress_callback(event_callback)
    try:
        for event in graph.stream(initial, stream_mode="updates"):
            for node_name, node_output in event.items():
                # Delta merge — operator.add fields accumulate, others overwrite
                for k, v in node_output.items():
                    if k in ("evidence_chunks", "claims", "phase_log", "errors"):
                        final_state[k] = final_state.get(k, []) + (v or [])
                    else:
                        final_state[k] = v

                # Stream phase log entries to UI callback
                if event_callback and node_output.get("phase_log"):
                    for entry in node_output["phase_log"]:
                        try:
                            event_callback(entry)
                        except Exception:
                            pass
    finally:
        set_progress_callback(None)

    accepted  = final_state.get("accepted_claims",  [])
    rejected  = final_state.get("rejected_claims",  [])
    uncertain = final_state.get("uncertain_claims", [])

    return {
        "query":           query,
        "run_id":          run_id,
        "report":          final_state.get("report",         ""),
        "sources":         final_state.get("sources_used",   []),
        "word_count":      final_state.get("word_count",      0),
        "coherence_score": final_state.get("coherence_score", 0.0),
        "claims_summary": {
            "total":     len(accepted) + len(rejected) + len(uncertain),
            "accepted":  len(accepted),
            "rejected":  len(rejected),
            "uncertain": len(uncertain),
        },
        "negotiation_rounds": len(final_state.get("negotiation_rounds", [])),
        "negotiation_log":    final_state.get("negotiation_rounds", []),
        "visualization":      final_state.get("visualization",  {}),
        "phase_log":          final_state.get("phase_log",       []),
        "errors":             final_state.get("errors",          []),
    }
