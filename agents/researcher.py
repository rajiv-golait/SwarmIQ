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
                title = result.get("title", "")
                published_at = result.get("published_date", "") or result.get("published_at", "")

                if not content:
                    continue

                chunk_id = self.chroma_store.stable_id(query, url, str(i), content[:200])
                raw_results.append(content)
                sources.append(url)
                metadatas.append(
                    self.chroma_store.citation_metadata(
                        source_url=url,
                        title=title,
                        published_at=published_at,
                        chunk_id=chunk_id,
                        agent_id="literature_reviewer",
                        query=query,
                    )
                )
                ids.append(chunk_id)

            if raw_results:
                try:
                    self.chroma_store.add_documents(
                        documents=raw_results,
                        metadatas=metadatas,
                        ids=ids,
                    )
                except Exception as exc:
                    print(f"Error storing documents in ChromaDB: {exc}")

            # Build evidence metadata mapping (chunk_id -> source_url, title, published_at)
            evidence_map = {}
            for i, chunk_id in enumerate(ids):
                evidence_map[chunk_id] = {
                    "source_url": sources[i] if i < len(sources) else "",
                    "title": metadatas[i].get("title", "") if i < len(metadatas) else "",
                    "published_at": metadatas[i].get("published_at", "") if i < len(metadatas) else "",
                    "content": raw_results[i] if i < len(raw_results) else "",
                }

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
                "chunk_ids": ids,  # Real Chroma chunk IDs
                "evidence_map": evidence_map,  # chunk_id -> {source_url, title, published_at, content}
            }
        except Exception as exc:
            print(f"Error during research: {exc}")
            return {
                "query": query,
                "sources": [],
                "raw_results": [],
                "summary": "",
                "stored_count": 0,
                "chunk_ids": [],
                "evidence_map": {},
            }
