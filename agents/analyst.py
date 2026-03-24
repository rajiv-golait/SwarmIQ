from groq import Groq

from memory.chroma_store import ChromaStore
from utils.config import GROQ_API_KEY, LLM_MODEL


class Analyst:
    def __init__(self, chroma_store: ChromaStore):
        self.chroma_store = chroma_store
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.model = LLM_MODEL

    def analyze(self, query: str, research_summary: str, sources: list[str]) -> dict:
        try:
            retrieved_chunks = self.chroma_store.query(query, n_results=5)
            chunk_text = []

            for index, chunk in enumerate(retrieved_chunks, start=1):
                metadata = chunk.get("metadata") or {}
                chunk_text.append(
                    f"Chunk {index}:\n"
                    f"Source: {metadata.get('url', 'Unknown')}\n"
                    f"Distance: {chunk.get('distance')}\n"
                    f"Content: {chunk.get('document', '')}"
                )

            prompt = (
                f"Original Query:\n{query}\n\n"
                f"Research Summary:\n{research_summary}\n\n"
                f"Sources:\n" + "\n".join(sources) + "\n\n"
                f"Top Retrieved Chunks:\n{chr(10).join(chunk_text) if chunk_text else 'No chunks retrieved.'}\n\n"
                "Identify any contradictions or conflicting facts between these sources. "
                "If conflicts exist, list them clearly. Then determine which claim is more credible "
                "based on recency and source authority. Return your analysis as structured text with "
                "sections: FINDINGS, CONFLICTS DETECTED, RESOLVED FACTS."
            )

            completion = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a careful research analyst focused on consistency and source credibility.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            findings = completion.choices[0].message.content or ""

            conflicts_detected = False
            conflicts_section = ""
            if "CONFLICTS DETECTED" in findings:
                after_conflicts = findings.split("CONFLICTS DETECTED", 1)[1]
                if "RESOLVED FACTS" in after_conflicts:
                    conflicts_section = after_conflicts.split("RESOLVED FACTS", 1)[0].strip(" :\n\t")
                else:
                    conflicts_section = after_conflicts.strip(" :\n\t")
                conflicts_detected = bool(conflicts_section)

            resolved_facts = ""
            if "RESOLVED FACTS:" in findings:
                resolved_facts = findings.split("RESOLVED FACTS:", 1)[1].strip()
            elif "RESOLVED FACTS" in findings:
                resolved_facts = findings.split("RESOLVED FACTS", 1)[1].strip(" :\n\t")

            return {
                "findings": findings,
                "conflicts_detected": conflicts_detected,
                "resolved_facts": resolved_facts,
                "chunks_used": len(retrieved_chunks),
            }
        except Exception as exc:
            print(f"Error during analysis: {exc}")
            return {
                "findings": "",
                "conflicts_detected": False,
                "resolved_facts": "",
                "chunks_used": 0,
            }
