# SwarmIQ — Known limitations

This document records behaviors we observed in real runs and how the system mitigates or accepts them. It is meant for evaluators and operators.

## 1. Planner query quality vs. model knowledge cutoff

The planner is an LLM with a training cutoff. Even with **current date / year** injected into prompts, it may not name entities that appeared after that cutoff (for example exact product version strings). It tends to produce generic web-style queries (“latest X features”) rather than precise release names.

**Mitigation:** Date-aware prompts and re-search query rotation improve recall; **full mitigation** would require live model-metadata or retrieval-augmented planning, which is out of scope for this build.

## 2. Web search rate limiting and empty first-pass results

DuckDuckGo / Bing-backed search can return **zero results** for bursts of similar queries from the same IP in a short window. The first research iteration may show all branches empty; a later iteration (after a gap-driven re-plan and slightly different query strings) may succeed.

**Note:** The gap-detection re-search loop **also behaves like a retry** with spacing between attempts. That is environmental, not a guaranteed backoff API.

## 3. Ungrounded synthesis when negotiation produces no accepted claims

If every claim stays **uncertain** or **rejected** (weak evidence, resolver fallbacks, or API limits), the synthesizer **does not** invent a long report from thin air. It returns a short “No Report Generated” placeholder and zero word count.

**Rationale:** Reduces **entity-anchored confabulation** when the pipeline has no consensus-backed claims.

## 4. Groq free tier: TPM / TPD and graceful degradation

When Groq returns **429** (tokens-per-minute or tokens-per-day exceeded), negotiation batches may fall back to **uncertain** votes, and synthesis may switch to a **smaller fast model** with reduced context. The pipeline keeps running; quality may drop until quotas reset.

**Visibility:** Negotiation and synthesis append explicit lines to **`phase_log`** (and SSE `log` events) when these fallbacks occur so the UI activity feed explains the behavior.

## 5. Coherence score is local, not full semantic BERTScore

The critic’s coherence score is produced by **`evaluation/coherence_scorer.py`** using **local** signals: citation density, structural completeness, references with URLs, and a length-based substitute for the BERTScore path (BERTScore is disabled by default to avoid a large one-time model download on first run). The number is **auditable and reproducible**, not a claim of deep semantic equivalence to human judgment.

Reports with **no pipeline sources** are treated as ungrounded: composite score is capped and the check **fails**, so a long, well-structured but unsourced report cannot receive a misleading “perfect” score.
