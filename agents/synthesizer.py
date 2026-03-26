import re

from groq import Groq

from memory.chroma_store import ChromaStore
from utils.config import CHROMA_PERSIST_DIR, FAST_MODEL, GROQ_API_KEY, LLM_MODEL


class CitationValidator:
    citation_pattern = re.compile(r"\[(\d+)\]")

    def validate(self, report: str, source_count: int) -> dict:
        inline_matches = {int(match) for match in self.citation_pattern.findall(report)}
        has_sources_section = "## Sources" in report or "\nSources\n" in report

        if source_count <= 0:
            return {"ok": False, "reason": "No sources available for citation validation."}
        if not inline_matches:
            return {"ok": False, "reason": "No inline citations found."}
        if not has_sources_section:
            return {"ok": False, "reason": "Sources section missing."}

        out_of_range = [idx for idx in inline_matches if idx < 1 or idx > source_count]
        if out_of_range:
            return {
                "ok": False,
                "reason": f"Inline citations out of range: {out_of_range}.",
            }
        return {"ok": True, "reason": "Citation validation passed."}


class Synthesizer:
    def __init__(self):
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.model = LLM_MODEL
        self.chroma_store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR)
        self.validator = CitationValidator()

    def synthesize(self, query: str, research: dict, analysis: dict) -> dict:
        sources = research.get("sources", [])
        numbered_sources = "\n".join([f"[{i + 1}] {url}" for i, url in enumerate(sources)])

        report = ""
        validation = {"ok": False, "reason": "Synthesis not executed."}
        model_used = self.model
        fallback_used = False

        for attempt in range(2):
            try:
                prompt = (
                    f"Original Query:\n{query}\n\n"
                    f"Research Summary:\n{research.get('summary', '')}\n\n"
                    f"Resolved Facts:\n{analysis.get('resolved_facts', '')}\n\n"
                    f"Conflicts Detected: {analysis.get('conflicts_detected', False)}\n\n"
                    "Use only the numbered sources list below for citations. "
                    "Every major claim must cite one or more sources as [n].\n\n"
                    f"Numbered Sources:\n{numbered_sources}\n\n"
                    "Return markdown with these sections exactly:\n"
                    "## Executive Summary\n## Key Findings\n## Conflict Resolution\n## Conclusion\n## Sources\n"
                    "In ## Sources, reproduce all numbered references as '- [n] URL'."
                )

                completion = self.groq_client.chat.completions.create(
                    model=model_used,
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
                validation = self.validator.validate(report, source_count=len(sources))
                if validation["ok"]:
                    break

            except Exception as exc:
                error_str = str(exc).lower()
                is_rate_limit = (
                    "429" in str(exc)
                    or "rate_limit" in error_str
                    or "rate limit" in error_str
                    or "too many requests" in error_str
                )

                if is_rate_limit and attempt == 0:
                    # Fallback to FAST_MODEL on rate limit
                    model_used = FAST_MODEL
                    fallback_used = True
                    print(f"Rate limit hit, falling back to {FAST_MODEL}")
                    continue
                else:
                    # Either not rate limit or second attempt failed
                    error_report = f"Research synthesis failed: {exc}. "
                    if is_rate_limit:
                        error_report += "API rate limit exceeded. Please try again in a moment."
                    else:
                        error_report += "Please try again later."

                    return {
                        "report": error_report,
                        "query": query,
                        "sources_used": sources,
                        "word_count": len(error_report.split()),
                        "citation_validation": {"ok": False, "reason": f"Synthesis failed: {exc}"},
                        "fallback_used": fallback_used,
                        "error": str(exc),
                    }

        # Store in Chroma if we got a valid report
        try:
            self.chroma_store.add_documents(
                documents=[report],
                metadatas=[
                    {
                        "type": "final_report",
                        "query": query,
                        "citation_validated": validation["ok"],
                        "validation_reason": validation["reason"],
                        "fallback_used": fallback_used,
                    }
                ],
                ids=[self.chroma_store.stable_id("final_report", query)],
            )
        except Exception as exc:
            print(f"Error storing final report in ChromaDB: {exc}")

        return {
            "report": report,
            "query": query,
            "sources_used": sources,
            "word_count": len(report.split()),
            "citation_validation": validation,
            "fallback_used": fallback_used,
        }
