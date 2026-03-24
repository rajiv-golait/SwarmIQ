from pathlib import Path
import sys

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.supervisor import Supervisor
from evaluation.coherence_scorer import CoherenceScorer


def run_swarmiq(query: str):
    if not query or not query.strip():
        return "Error: Please enter a valid research query."

    supervisor = Supervisor()
    result = supervisor.run(query)

    scorer = CoherenceScorer()
    score_result = scorer.score(query, result["report"], result["sources"])

    sources_block = "\n".join(result["sources"]) if result["sources"] else "No sources found."
    log_block = "\n".join(result["session_log"]) if result["session_log"] else "No logs recorded."
    score_label = "PASSED" if score_result["passed"] else "BELOW THRESHOLD"
    conflicts_label = "Yes" if result["conflicts_detected"] else "No"

    output = (
        f"{result['report']}\n\n"
        "---\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        f"COHERENCE SCORE: {score_result['score']} {score_label}\n\n"
        f"CONFLICTS DETECTED: {conflicts_label}\n\n"
        f"WORD COUNT: {result['word_count']}\n\n"
        f"AGENT LOG:\n{log_block}"
    )
    return output


demo = gr.Interface(
    fn=run_swarmiq,
    inputs=gr.Textbox(
        label="Research Query",
        placeholder="e.g. Latest AI regulations in India 2025",
        lines=2,
    ),
    outputs=gr.Markdown(label="Research Report"),
    title="SwarmIQ - Multi-Agent Research Assistant",
    description="Powered by Groq + ChromaDB + Tavily + AutoGen | Enter any research query and get a cited, coherent report.",
    examples=[
        ["Latest AI regulations in India 2025"],
        ["Maharashtra agriculture technology initiatives"],
        ["India startup ecosystem funding trends 2025"],
        ["Digital health policy in India"],
        ["Climate policy updates COP30"],
    ],
    theme=gr.themes.Soft(),
)


if __name__ == "__main__":
    demo.launch()
