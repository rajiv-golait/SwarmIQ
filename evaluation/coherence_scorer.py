class CoherenceScorer:
    def __init__(self):
        self.threshold = 0.90

    def score(self, query: str, report: str, sources: list[str]) -> dict:
        try:
            from deepeval.metrics import GEval
            from deepeval.test_case import LLMTestCase, LLMTestCaseParams
        except ImportError:
            return {
                "score": 0.0,
                "passed": False,
                "reason": "DeepEval not installed",
                "threshold": 0.90,
            }

        try:
            metric = GEval(
                name="Coherence",
                criteria=(
                    "The report is well-structured, logically flows from one section to "
                    "the next, contains no contradictions, cites sources appropriately, and "
                    "directly answers the original query without going off-topic."
                ),
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                threshold=0.90,
            )
            test_case = LLMTestCase(
                input=query,
                actual_output=report,
            )
            metric.measure(test_case)

            return {
                "score": float(metric.score),
                "passed": float(metric.score) >= 0.90,
                "reason": metric.reason,
                "threshold": 0.90,
            }
        except Exception as exc:
            return {
                "score": 0.0,
                "passed": False,
                "reason": f"DeepEval scoring failed: {exc}",
                "threshold": 0.90,
            }
