from groq import Groq

from memory.chroma_store import ChromaStore
from utils.config import CHROMA_PERSIST_DIR, GROQ_API_KEY, LLM_MODEL


class Synthesizer:
    def __init__(self):
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.model = LLM_MODEL
        self.chroma_store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR)

    def synthesize(self, query: str, research: dict, analysis: dict) -> dict:
        try:
            prompt = (
                f"Original Query:\n{query}\n\n"
                f"Research Summary:\n{research.get('summary', '')}\n\n"
                f"Resolved Facts:\n{analysis.get('resolved_facts', '')}\n\n"
                f"Sources:\n" + "\n".join(research.get("sources", [])) + "\n\n"
                "Write a comprehensive, well-structured research report on the query. "
                "Include: an Executive Summary, Key Findings (with inline citations like [Source: URL]), "
                "Analysis, and Conclusion. Use markdown formatting. Be factual, coherent, and cite "
                "every major claim."
            )

            completion = self.groq_client.chat.completions.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {
                        "role": "system",
                        "content": "You write rigorous research reports with explicit source citation.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            report = completion.choices[0].message.content or ""

            try:
                self.chroma_store.add_documents(
                    documents=[report],
                    metadatas=[{"type": "final_report", "query": query}],
                    ids=[f"final_report_{abs(hash(query))}"],
                )
            except Exception as exc:
                print(f"Error storing final report in ChromaDB: {exc}")

            return {
                "report": report,
                "query": query,
                "sources_used": research.get("sources", []),
                "word_count": len(report.split()),
            }
        except Exception as exc:
            print(f"Error during synthesis: {exc}")
            return {
                "report": "",
                "query": query,
                "sources_used": research.get("sources", []),
                "word_count": 0,
            }
