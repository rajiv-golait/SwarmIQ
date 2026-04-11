import logging
from agents.state import SwarmState

logger = logging.getLogger(__name__)


class GapDetectorNode:
    """Stub gap detector — skips LLM gap analysis for this build.

    Returns unanswered_questions=[] to force the graph to take
    the "proceed" branch immediately without looping back to plan.
    """

    def run(self, state: SwarmState) -> dict:
        return {
            "unanswered_questions": [],   # forces "proceed" branch immediately
            "phase_log": ["[GapDetect] Stub — assuming all answered"],
        }
