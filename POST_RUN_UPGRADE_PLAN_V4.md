# SwarmIQ — Post-Run Upgrade Plan v4.0

> Grounded in production run: query **“Latest Claude Model Released in 2026 April”**, `run_id` **fd92dd06a5ae**, **April 11, 2026**.  
> This file records **observed** failures from logs/JSON and the **code changes** shipped in this repo to address them.

See also **`BENCHMARK.md`** for the metric table and re-benchmark checklist.

---

## Part 1 — What the run showed (rating summary)

**Overall (pre-fix): ~3.5 / 10** — pipeline completed but key quality signals were wrong or missing.

| Issue | Evidence |
|--------|-----------|
| Factual error in report | Low-authority blog claim treated like fact; weak source arbitration |
| `coherence_score: 1.0` misleading | Critic was a stub; score not measured |
| Gap loop inactive | `[GapDetect] Stub — assuming all answered` |
| Planner typos | Multiple DDG queries with **“cluade”** instead of **Claude** |
| Negotiation under-voting | ~14 votes for 101 claims in round 1 → mass **uncertain** |
| Duplicate `chunk_id` | Same id repeated in negotiation unresolved lists |
| Citation inflation | Many inline `[n]` mapped to fewer unique URLs |
| Claim count drop | LitReview logs summed to more claims than negotiation saw |
| Runtime | ~3m35s with stubs skipped; full stack will be longer |

---

## Part 2 — Implemented fixes (this repository)

| Change | Location | Purpose |
|--------|----------|---------|
| Query validation + typo fix | `agents/planner_validate.py`, wired from `agents/roles/planner.py` | Cap length, fix **cluade→Claude**, anchor queries with no token overlap |
| Batched negotiation | `agents/roles/conflict_resolver.py` | Vote in batches (15), higher output budget, fill missing votes as uncertain |
| Claim dedupe before negotiate | `agents/roles/conflict_resolver.py` | One row per `claim_id` |
| Real gap detector | `agents/gap_detector.py` | Groq JSON + heuristic; respects `MAX_RESEARCH_ITERATIONS` |
| Real critic | `agents/critic.py` + `evaluation/coherence_scorer.py` | `CoherenceScorer`; `is_stub: False` on scorer dicts; sentinel warning on 1.0 |
| Lance dedupe on insert | `memory/lance_store.py` | Skip `chunk_id` already present |
| Citation discipline | `agents/roles/synthesizer.py` | Prompt + post `_clamp_citations` to allowed source count |
| Claim integrity log | `agents/graph.py` | `merge_and_validate` logs claim row count vs unique `claim_id` before negotiate (does not emit `claims` — `operator.add` would duplicate); negotiator dedupes |
| Regression tests | `tests/test_planner_validate.py` | Typo + anchoring behavior |

---

## Part 3 — Priority order (by observed impact)

| Priority | Item | Status in repo |
|----------|------|----------------|
| P0 | Remove critic stub | Done — real `CriticNode` |
| P0 | Remove gap stub | Done — real `GapDetectorNode` |
| P1 | Batch claim voting | Done |
| P1 | Planner query validation | Done |
| P2 | Dedupe claims / log transitions | Negotiator dedupe + `merge_and_validate` audit log done |
| P2 | Lance upsert / skip duplicate `chunk_id` | Done (skip existing ids) |
| P3 | Citation inflation | Prompt + clamp done |
| P4 | Benchmark doc + tests | `BENCHMARK.md` + planner tests done; extend tests as needed |

---

## Part 4 — Honest system summary

**What worked:** End-to-end LangGraph run, retrieval, LanceDB, negotiation rounds, streaming logs, exports.

**What was broken (pre-v4):** Stubs masked core loops; planner emitted bad queries; negotiation truncated; duplicate storage and IDs; citations and scores misrepresented quality.

**After v4:** The architecture matches the README’s intent much more closely; **re-run the same benchmark query** to validate uncertain %, coherence distribution, and citations against ground truth.

---

*Version 4.0 — aligned with run `fd92dd06a5ae` and the fixes above.*
