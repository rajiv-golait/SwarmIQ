import logging
from groq import Groq
from agents.state import SwarmState
from memory.lance_store import LanceStore
from memory.models import rerank
from utils.config import LLM_MODEL, FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)

# Groq free / low tiers: fast models often cap ~6k TPM per request; keep user prompt small.
_SYNTH_LIMITS = (
    {"sources": 6, "per_doc": 400, "claims_chars": 2800},
    {"sources": 5, "per_doc": 300, "claims_chars": 2200},
    {"sources": 4, "per_doc": 220, "claims_chars": 1600},
    {"sources": 3, "per_doc": 160, "claims_chars": 1200},
)

SYSTEM_PROMPT = """You are a research analyst writing a comprehensive cited report.

RULES:
1. Every factual claim MUST have inline citation [n]
2. Use ONLY the numbered sources provided
3. Write minimum 600 words
4. Professional academic tone

REQUIRED SECTIONS:
## Executive Summary
## Key Findings
## Conflicting Perspectives
## Analysis
## Limitations
## Conclusion
## References"""


class SynthesizerNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    @staticmethod
    def _evidence_block(
        top_evidence: list[dict],
        *,
        max_sources: int,
        per_doc: int,
    ) -> str:
        parts: list[str] = []
        for i, e in enumerate(top_evidence[:max_sources]):
            url = e.get("metadata", {}).get("source_url", "")
            doc = (e.get("document") or "")[:per_doc]
            parts.append(f"[Source {i+1}] {url}\n{doc}")
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _claims_block(accepted_claims: list, max_chars: int) -> str:
        lines: list[str] = []
        n = 0
        for c in accepted_claims:
            line = f"• {c['statement']} [conf:{c['confidence']:.2f}]"
            if n + len(line) + 1 > max_chars:
                break
            lines.append(line)
            n += len(line) + 1
        return "\n".join(lines)

    def run(self, state: SwarmState) -> dict:
        query            = state["query"]
        accepted_claims  = state.get("accepted_claims",  [])
        uncertain_claims = state.get("uncertain_claims", [])
        evidence_chunks  = state.get("evidence_chunks",  [])
        critique_issues  = state.get("critique_issues",  [])

        # Build numbered source list
        seen_urls: dict[str, int] = {}
        numbered: list[dict]      = []
        for claim in accepted_claims:
            for cid in claim.get("evidence_chunk_ids", []):
                chunk = next(
                    (c for c in evidence_chunks if c.get("chunk_id") == cid), None
                )
                if chunk:
                    url = chunk.get("source_url", "")
                    if url and url not in seen_urls:
                        idx = len(numbered) + 1
                        seen_urls[url] = idx
                        numbered.append({
                            "number":  idx,
                            "url":     url,
                            "domain":  chunk.get("source_domain", ""),
                            "content": chunk.get("content", "")[:2000],
                        })

        retrieved    = self.store.query(query, n_results=20)
        top_evidence = rerank(query, retrieved, top_k=15)

        def _cap(text: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            return text[: max_chars - 3].rstrip() + "..."

        uncertain_text = (
            "\n\nUNVERIFIED (mention with caution):\n"
            + "\n".join(f"• {c['statement'][:160]}" for c in uncertain_claims[:10])
        ) if uncertain_claims else ""
        uncertain_text = _cap(uncertain_text, 1200) if uncertain_text else ""

        revision_note = (
            "\n\nFIX THESE ISSUES FROM PREVIOUS DRAFT:\n"
            + "\n".join(f"• {i[:200]}" for i in critique_issues[:6])
        ) if critique_issues else ""
        revision_note = _cap(revision_note, 1200) if revision_note else ""

        sources_ref = "\n".join(
            f"[{s['number']}] {s['domain']} - {s['url']}"
            for s in numbered[:18]
        )
        sources_ref = _cap(sources_ref, 3500)

        # Groq TPM limits often apply to (prompt tokens + max_tokens); keep the sum conservative.
        model_used   = LLM_MODEL
        report       = ""
        tier_idx     = 0
        max_out_toks = 1536

        for attempt in range(8):
            lim = _SYNTH_LIMITS[min(tier_idx, len(_SYNTH_LIMITS) - 1)]
            evidence_text = self._evidence_block(
                top_evidence,
                max_sources=lim["sources"],
                per_doc=lim["per_doc"],
            )
            n_ev = min(len(top_evidence), lim["sources"])
            claims_text = self._claims_block(accepted_claims, lim["claims_chars"])
            user_prompt = (
                f"Query: {query}\n\n"
                f"Evidence ({n_ev} sources):\n{evidence_text}\n\n"
                f"Accepted Claims:\n{claims_text}"
                f"{uncertain_text}"
                f"{revision_note}\n\n"
                f"Numbered Sources:\n{sources_ref}\n\n"
                "Write the complete research paper with [n] citations."
            )
            user_prompt = _cap(user_prompt, 10000)

            try:
                groq_limiter.wait_if_needed(min(2000, max_out_toks + 400))
                resp = self.client.chat.completions.create(
                    model=model_used,
                    max_tokens=max_out_toks,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
                report = resp.choices[0].message.content or ""
                break
            except Exception as e:
                err = str(e).lower()
                tpm_big = (
                    "413" in str(e)
                    or "request too large" in err
                    or ("tpm" in err and "limit" in err)
                )
                if tpm_big:
                    if tier_idx < len(_SYNTH_LIMITS) - 1:
                        tier_idx += 1
                        logger.warning(
                            "[Synthesize] TPM too high — shrinking context "
                            f"(tier {tier_idx})"
                        )
                        continue
                    if max_out_toks > 768:
                        max_out_toks = 768
                        logger.warning(
                            "[Synthesize] TPM still high — reducing max_tokens"
                        )
                        continue
                if ("429" in str(e) or "rate_limit" in err) and model_used == LLM_MODEL:
                    model_used = FAST_MODEL
                    tier_idx = min(tier_idx + 1, len(_SYNTH_LIMITS) - 1)
                    max_out_toks = min(max_out_toks, 1200)
                    logger.warning(
                        "[Synthesize] Rate limit — fast model + tighter context"
                    )
                    continue
                if ("429" in str(e) or "rate_limit" in err) and model_used == FAST_MODEL:
                    max_out_toks = min(max_out_toks, 1200)
                    tier_idx = min(tier_idx + 1, len(_SYNTH_LIMITS) - 1)
                    logger.warning("[Synthesize] Fast model rate limit — backoff")
                    continue
                logger.error(f"[Synthesize] Failed: {e}")
                report = f"Synthesis failed: {e}"
                break

        if "## References" not in report and sources_ref:
            report += f"\n\n## References\n\n{sources_ref}"

        log = f"[Synthesize] {len(report.split())} words, {len(numbered)} sources"
        logger.info(log)

        return {
            "report":       report,
            "word_count":   len(report.split()),
            "sources_used": [s["url"] for s in numbered],
            "phase_log":    [log],
        }
