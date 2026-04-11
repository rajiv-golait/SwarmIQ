"""CriticNode — evaluates synthesized reports using the CoherenceScorer.

Replaces the stub that returned coherence_score=1.0 unconditionally.
The _should_revise conditional edge in graph.py uses the score and
critique_issues to decide whether to loop back to the synthesizer.
"""
import logging
from agents.state import SwarmState
from evaluation.coherence_scorer import CoherenceScorer

logger = logging.getLogger(__name__)

# Sentinel value the stub used to return.  A real report should never
# score exactly 1.0 — if it does, something is likely wrong.
_STUB_SENTINEL = 1.0


class CriticNode:
    def __init__(self):
        self.scorer = CoherenceScorer()

    def run(self, state: SwarmState) -> dict:
        report   = state.get("report", "")
        query    = state.get("query", "")
        sources  = state.get("sources_used", [])
        revision = state.get("critique_revision", 0)

        if not report or len(report.split()) < 50:
            logger.warning("[Critic] Report too short to evaluate")
            return {
                "coherence_score":   0.0,
                "critique_issues":   ["Report is empty or too short to evaluate"],
                "critique_revision": revision + 1,
                "phase_log": ["[Critic] Report too short — score 0.0"],
            }

        result = self.scorer.score(query, report, sources)
        score  = result["score"]
        issues = result.get("issues", [])

        # Sanity check: flag if we somehow returned the stub sentinel
        if score == _STUB_SENTINEL and len(report.split()) > 100:
            logger.warning(
                f"[Critic] ALERT: Score is exactly {_STUB_SENTINEL} on a "
                f"{len(report.split())}-word report — verify this is real "
                "scoring, not a stub default"
            )

        passed = result.get("passed", False)
        label  = "PASSED" if passed else "BELOW THRESHOLD"
        log    = (
            f"[Critic] Score {score:.2f} ({label}) | "
            f"{len(issues)} issues | revision {revision + 1}"
        )
        logger.info(log)

        return {
            "coherence_score":   score,
            "critique_issues":   issues,
            "critique_revision": revision + 1,
            "phase_log":         [log],
        }
