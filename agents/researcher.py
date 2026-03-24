from groq import Groq
from tavily import TavilyClient

from memory.chroma_store import ChromaStore
from utils.config import FAST_MODEL, GROQ_API_KEY, TAVILY_API_KEY


class Researcher:
    def __init__(self, chroma_store: ChromaStore):
        self.chroma_store = chroma_store
        self.tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        self.groq_client = Groq(api_key=GROQ_API_KEY)

    def research(self, query: str) -> dict:
        try:
            search_response = self.tavily_client.search(query, max_results=5)
            results = search_response.get("results", [])

            raw_results = []
            sources = []
            metadatas = []
            ids = []

            for i, result in enumerate(results):
                content = result.get("content", "")
                url = result.get("url", "")

                if not content:
                    continue

                raw_results.append(content)
                sources.append(url)
                metadatas.append({"url": url, "query": query})
                ids.append(f"doc_{i}_{abs(hash(url))}")

            if raw_results:
                try:
                    self.chroma_store.add_documents(
                        documents=raw_results,
                        metadatas=metadatas,
                        ids=ids,
                    )
                except Exception as exc:
                    print(f"Error storing documents in ChromaDB: {exc}")

            combined_content = "\n\n".join(raw_results) if raw_results else "No search results found."
            summary = "No summary generated."

            try:
                completion = self.groq_client.chat.completions.create(
                    model=FAST_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "Summarize the research into concise key findings.",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Query: {query}\n\n"
                                f"Research content:\n{combined_content}"
                            ),
                        },
                    ],
                )
                summary = completion.choices[0].message.content or summary
            except Exception as exc:
                print(f"Error generating Groq summary: {exc}")

            return {
                "query": query,
                "sources": sources,
                "raw_results": raw_results,
                "summary": summary,
                "stored_count": len(raw_results),
            }
        except Exception as exc:
            print(f"Error during research: {exc}")
            return {
                "query": query,
                "sources": [],
                "raw_results": [],
                "summary": "",
                "stored_count": 0,
            }
