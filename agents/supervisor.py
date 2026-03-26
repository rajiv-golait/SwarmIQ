from agents.analyst import Analyst
from agents.researcher import Researcher
from agents.swarm.supervisor import AutoGenSupervisor
from agents.synthesizer import Synthesizer
from memory.chroma_store import ChromaStore
from utils.config import CHROMA_PERSIST_DIR, SWARM_MODE


class Supervisor:
    def __init__(self):
        self.swarm_mode = SWARM_MODE
        self.chroma_store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR)
        self.researcher = Researcher(self.chroma_store)
        self.analyst = Analyst(self.chroma_store)
        self.synthesizer = Synthesizer()
        self.swarm_supervisor = AutoGenSupervisor() if self.swarm_mode else None
        self.session_log = []

    def run(self, query: str) -> dict:
        if self.swarm_mode and self.swarm_supervisor is not None:
            result = self.swarm_supervisor.run(query)
            self.session_log = result.get("session_log", [])
            return result

        start_log = f"SUPERVISOR: Starting research for: {query}"
        print(start_log)
        self.session_log.append(start_log)

        research_result = self.researcher.research(query)

        research_log = (
            f"SUPERVISOR: Research complete. {research_result.get('stored_count', 0)} docs stored."
        )
        print(research_log)
        self.session_log.append(research_log)

        analysis_result = self.analyst.analyze(
            query,
            research_result.get("summary", ""),
            research_result.get("sources", []),
        )

        analysis_log = (
            "SUPERVISOR: Analysis complete. Conflicts detected: "
            f"{analysis_result.get('conflicts_detected', False)}"
        )
        print(analysis_log)
        self.session_log.append(analysis_log)

        final_result = self.synthesizer.synthesize(query, research_result, analysis_result)

        final_log = f"SUPERVISOR: Report generated. Word count: {final_result.get('word_count', 0)}"
        print(final_log)
        self.session_log.append(final_log)

        return {
            "query": query,
            "report": final_result.get("report", ""),
            "sources": research_result.get("sources", []),
            "conflicts_detected": analysis_result.get("conflicts_detected", False),
            "word_count": final_result.get("word_count", 0),
            "citation_validation": final_result.get("citation_validation", {}),
            "session_log": self.session_log,
            "stage_events": [],
        }
