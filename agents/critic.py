import logging
from agents.state import SwarmState

logger = logging.getLogger(__name__)


class CriticNode:
    """Stub critic — skips coherence scoring for this build.

    Returns coherence_score=1.0 and critique_revision=99 to force
    the graph to take the "finish" branch immediately without looping.
    """

    def run(self, state: SwarmState) -> dict:
        return {
            "coherence_score":   1.0,
            "critique_issues":   [],
            "critique_revision": 99,   # forces "finish" branch immediately
            "phase_log": ["[Critic] Stub — skipping critique"],
        }
