from agents.graph import run_pipeline
from evaluation.coherence_scorer import CoherenceScorer


def main():
    print("SwarmIQ - Multi-Agent Research Assistant")
    print("Powered by Groq + LanceDB + DuckDuckGo")
    print("=========================================")

    query = input("Enter your research query: ")
    if not query or not query.strip():
        print("Please enter a valid query.")
        return

    print("Starting SwarmIQ agent swarm...")
    result = run_pipeline(query)

    for log_entry in result.get("phase_log", []):
        print(log_entry)

    print(result["report"])

    scorer = CoherenceScorer()
    score_result = scorer.score(query, result["report"], result.get("sources", []))
    print(f"COHERENCE SCORE: {score_result['score']} | PASSED: {score_result['passed']}")

    print("SOURCES USED:")
    for source in result.get("sources", []):
        print(source)

    print(f"word_count: {result.get('word_count', 0)}")
    print("Done.")


if __name__ == "__main__":
    main()
