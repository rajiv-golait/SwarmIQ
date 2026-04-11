import re
import logging

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = [
    "executive summary",
    "key findings",
    "references",
    "conclusion",
]

CITATION_RE = re.compile(r"\[(\d+)\]")
URL_RE      = re.compile(r"https?://([^/\s\)]+)")


class CoherenceScorer:
    """Composite coherence scorer — fully local, zero external API calls.

    Components and weights:
      citation_density        25%  — inline [n] count relative to report length
      structural_completeness 25%  — required sections present
      references_present      25%  — References section with URLs
      length_adequacy         25%  — word count vs 500-word minimum

    BERTScore branch is DISABLED — _bert_or_length always returns the length
    score to avoid a 5-minute model download on first run.

    FIX: Previous version checked every sentence for "is/are/was" which
    matches ALL English text, making citation_coverage score near 0 for
    any real report. Replaced with citation density — simpler, honest.
    """

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def score(self, query: str, report: str, sources: list[str]) -> dict:
        if not report:
            return {
                "score":     0.0,
                "passed":    False,
                "issues":    ["Empty report"],
                "threshold": self.threshold,
                "components": {},
                "is_stub":   False,
            }

        words = len(report.split())
        if words < 50:
            return {
                "score":     0.0,
                "passed":    False,
                "issues":    ["Report too short"],
                "threshold": self.threshold,
                "components": {},
                "is_stub":   False,
            }

        c1 = self._citation_density(report, words)
        c2 = self._structural_completeness(report)
        c3 = self._references_present(report)
        c4 = self._bert_or_length(query, report, words)

        components = {
            "citation_density":        c1,
            "structural_completeness": c2,
            "references_present":      c3,
            "length_or_semantic":      c4,
        }
        weights   = [0.25, 0.25, 0.25, 0.25]
        composite = round(
            sum(v * w for v, w in zip(components.values(), weights)), 3
        )

        issues = self._issues(report, words, c1, c2, c3)
        return {
            "score":      composite,
            "passed":     composite >= self.threshold,
            "issues":     issues,
            "threshold":  self.threshold,
            "components": components,
            "is_stub":    False,
        }

    def _citation_density(self, report: str, words: int) -> float:
        """Citations per 100 words. 3+ per 100 words = 1.0."""
        n_citations = len(CITATION_RE.findall(report))
        density     = n_citations / max(words / 100, 1)
        return min(density / 3.0, 1.0)

    def _structural_completeness(self, report: str) -> float:
        rl = report.lower()
        return sum(1 for s in REQUIRED_SECTIONS if s in rl) / len(REQUIRED_SECTIONS)

    def _references_present(self, report: str) -> float:
        """Does the References section have actual URLs?"""
        has_section = bool(re.search(r"##\s*references", report, re.I))
        has_urls    = bool(URL_RE.search(report))
        if has_section and has_urls:
            return 1.0
        if has_section or has_urls:
            return 0.5
        return 0.0

    def _bert_or_length(self, query: str, report: str, words: int) -> float:
        """Always returns length score — BERTScore branch disabled.

        BERTScore requires a 5-minute model download on first call.
        Disabled for this build to keep startup fast.
        Length score: min(words / 500, 1.0)
        """
        return min(words / 500, 1.0)

    def _issues(
        self, report: str, words: int,
        c1: float, c2: float, c3: float
    ) -> list[str]:
        issues = []
        if c1 < 0.4:
            n = len(CITATION_RE.findall(report))
            issues.append(
                f"Too few citations ({n} found) — add [n] to factual claims"
            )
        if c2 < 0.75:
            missing = [s for s in REQUIRED_SECTIONS if s not in report.lower()]
            issues.append(f"Missing sections: {', '.join(missing)}")
        if c3 < 0.5:
            issues.append("References section missing or has no URLs")
        if words < 400:
            issues.append(f"Report too short ({words} words — target 500+)")
        return issues
