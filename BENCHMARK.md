# SwarmIQ Benchmark — Production Run Data

## Run: fd92dd06a5ae

| Field | Value |
|---|---|
| **Query** | `Latest Claude Model Released in 2026 April` |
| **Run ID** | `fd92dd06a5ae` |
| **Date** | 2026-04-11T11:20:28 UTC |
| **Pipeline** | SwarmIQ v3 — LangGraph + Groq + LanceDB + DDG/Jina |
| **LLM** | `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` (fallback) |

---

## Results Summary

| Metric | Value | Status |
|---|---|---|
| Word count | 596 | ✅ |
| Coherence score | 1.00 | ❌ Fraudulent (critic was stub) |
| Sources found | 9 unique | ⚠️ Inflated to 24 citations |
| Claims generated | 181 | — |
| Claims entering negotiation | 101 | ❌ 80 lost silently (44%) |
| Round 1 resolution | 14 / 101 (13.9%) | ❌ Token truncation |
| Final: accepted | 44 | — |
| Final: rejected | 6 | — |
| Final: uncertain | 51 | ❌ 51.5% unresolved |
| Negotiation rounds | 3 | — |

---

## Bugs Identified

### Bug 1 — Factual Hallucination
**Severity:** Critical  
Report states "Claude Mythos 5 — a 10-trillion parameter model."  
**Ground truth:** Anthropic announced "Claude Mythos Preview" on April 7, 2026 via "Project Glasswing." No "Mythos 5" exists. No "10 trillion parameters" was announced.  
**Root cause:** Source arbitration failure — low-authority blog data accepted over official announcements.

### Bug 2 — Critic Stub
**Severity:** P0  
`CriticNode.run()` returned `coherence_score: 1.0` and `critique_revision: 99`, bypassing all evaluation.  
**Fix:** Replaced with real CoherenceScorer integration.

### Bug 3 — Gap Detector Stub
**Severity:** P0  
`GapDetectorNode.run()` returned `unanswered_questions: []`, disabling the research iteration loop.  
**Fix:** Replaced with LLM-based evidence coverage evaluation.

### Bug 4 — Planner Typo Queries
**Severity:** P1  
5 of 7 search queries contained "cluade" instead of "claude."  
**Fix:** Added `_validate_and_fix_queries()` with token overlap check.

### Bug 5 — Negotiation Resolution Rate
**Severity:** P1  
Round 1 resolved only 14 of 101 claims (13.9%). All 101 claims were sent in a single LLM call with `max_tokens=800`, causing output truncation.  
**Fix:** Batched voting at ≤15 claims per call.

### Bug 6 — Silent Claim Loss + Duplicates
**Severity:** P2  
181 claims generated → 101 entered negotiation. 80 claims (44%) vanished without any log entry. Duplicate `chunk_id`s found in LanceDB.  
**Fix:** Added `merge_and_validate` node with claim deduplication and logging. Added upsert-guard in `LanceStore.add_documents()`.

### Bug 7 — Citation Inflation
**Severity:** P3  
Report used `[1]`–`[24]` inline citations but only 9 unique source URLs existed. The LLM recycled sources under different citation numbers.  
**Fix:** Added `_clamp_citations()` post-processing. Updated system prompt to forbid `[n]` where `n > N`.

---

## Ground Truth Sources

For "Latest Claude Model Released in 2026 April":

1. **Anthropic Blog** (2026-04-07): "Introducing Claude Mythos Preview" — available through Project Glasswing
2. **Anthropic Docs** (anthropic.com): Claude model versioning and naming conventions
3. **The Verge** (2026-04-07): Coverage of Claude Mythos Preview announcement

---

## Next Benchmark

After all fixes are deployed, re-run the same query and verify:

- [ ] Coherence score < 1.0 and is a real evaluation
- [ ] `[Critic]` log entry shows a real score, not "Stub"
- [ ] `[GapDetect]` evaluates question coverage, not "Stub"
- [ ] No "cluade" typos in search queries
- [ ] `[Merge]` log shows dedup count
- [ ] Negotiation Round 1 resolves > 50% of claims
- [ ] Max `[n]` citation ≤ unique source count
- [ ] No "Claude Mythos 5" hallucination in report
