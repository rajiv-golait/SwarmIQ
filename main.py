from agents.supervisor import Supervisor
from evaluation.coherence_scorer import CoherenceScorer


def main():
    print("SwarmIQ - Multi-Agent Research Assistant")
    print("Powered by Groq + ChromaDB + Tavily")
    print("=========================================")

    query = input("Enter your research query: ")
    if not query or not query.strip():
        print("Please enter a valid query.")
        return

    print("Starting SwarmIQ agent swarm...")
    supervisor = Supervisor()
    result = supervisor.run(query)

    for log_entry in result["session_log"]:
        print(log_entry)

    print(result["report"])

    scorer = CoherenceScorer()
    score_result = scorer.score(query, result["report"], result["sources"])
    print(f"COHERENCE SCORE: {score_result['score']} | PASSED: {score_result['passed']}")

    print("SOURCES USED:")
    for source in result["sources"]:
        print(source)

    print("Done.")


if __name__ == "__main__":
    main()
