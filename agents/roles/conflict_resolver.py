"""ConflictResolverNode — multi-round claim negotiation with batched voting.

Fixes from run fd92dd06a5ae:
  - Bug 5: Round 1 resolved only 14/101 claims (13.9%) because one LLM call
    for 101 claims hit max_tokens=800 and truncated.  Now batched at ≤15.
  - Bug 6: Duplicate claim_ids entered negotiation.  Now deduplicated at entry.
"""
import json
import logging
from groq import Groq
from agents.state import SwarmState, Claim, NegotiationRound
from memory.lance_store import LanceStore
from memory.models import rerank
from utils.config import LLM_MODEL, GROQ_API_KEY, SWARM_MAX_NEGOTIATION_ROUNDS
from utils.progress import emit_progress
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)

# Tuned: 15 claims fit in ~400 tokens of input, ~300 tokens of output.
# Ensures the LLM can vote on every claim without truncation.
BATCH_SIZE = 15


class BatchVoteFailed(Exception):
    """Groq/API or parse failure — caller should use uncertain fallback and log clearly."""


class ConflictResolverNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def _vote_batch(
        self,
        claims_batch: list[Claim],
        evidence_ctx: str,
    ) -> list[dict]:
        """Vote on a single batch of ≤15 claims. Raises BatchVoteFailed on API/parse errors."""
        claims_text = "\n".join(
            f"ID:{c['claim_id'][:12]} | "
            f"Conf:{c['confidence']:.2f} | "
            f"{c['statement'][:120]}"
            for c in claims_batch
        )

        groq_limiter.wait_if_needed(estimated_tokens=600)
        try:
            resp = self.client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=500,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Vote on ALL {len(claims_batch)} claims. "
                            "Every claim must get a vote: accepted, rejected, or uncertain. "
                            "Return ONLY valid JSON with this exact shape: "
                            '{"votes": [{"claim_id": "...", '
                            '"vote": "accepted|rejected|uncertain", '
                            '"rationale": "one sentence"}]}\n'
                            f"You MUST return exactly {len(claims_batch)} vote objects in the json."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Evidence:\n{evidence_ctx}\n\n"
                            f"Claims to vote on:\n{claims_text}"
                        ),
                    },
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            data  = json.loads(raw)
            votes = data.get("votes", [])

            # Validate we got votes for all claims in the batch
            voted_ids = {v.get("claim_id", "")[:12] for v in votes}
            for claim in claims_batch:
                if claim["claim_id"][:12] not in voted_ids:
                    # LLM missed this claim — add uncertain fallback
                    votes.append({
                        "claim_id":  claim["claim_id"][:12],
                        "vote":      "uncertain",
                        "rationale": "No vote returned by LLM",
                    })
            return votes

        except Exception as e:
            logger.error(f"[Negotiate] Batch vote failed: {e}")
            raise BatchVoteFailed(str(e)) from e

    @staticmethod
    def _fallback_votes(claims_batch: list[Claim], err: str) -> list[dict]:
        return [
            {
                "claim_id":  c["claim_id"][:12],
                "vote":      "uncertain",
                "rationale": f"Vote failed: {err}",
            }
            for c in claims_batch
        ]

    def run(self, state: SwarmState) -> dict:
        all_claims = state.get("claims", [])
        query      = state["query"]

        if not all_claims:
            return {
                "accepted_claims":    [],
                "rejected_claims":    [],
                "uncertain_claims":   [],
                "negotiation_rounds": [],
                "phase_log": ["[Negotiate] No claims to process"],
            }

        # ── Deduplicate by claim_id before negotiation ──
        seen_claim_ids: set[str] = set()
        deduped_claims: list[Claim] = []
        for claim in all_claims:
            cid = claim.get("claim_id", "")
            if cid and cid not in seen_claim_ids:
                seen_claim_ids.add(cid)
                deduped_claims.append(claim)
            elif not cid:
                logger.warning("[Negotiate] Claim with empty claim_id skipped")

        removed = len(all_claims) - len(deduped_claims)
        if removed > 0:
            logger.info(
                f"[Negotiate] Deduplicated {removed} duplicate claims "
                f"({len(all_claims)} → {len(deduped_claims)})"
            )

        pending   = list(deduped_claims)
        accepted: list[Claim]            = []
        rejected: list[Claim]            = []
        uncertain: list[Claim]           = []
        rounds:   list[NegotiationRound] = []
        negotiate_phase: list[str]       = []

        for round_num in range(1, SWARM_MAX_NEGOTIATION_ROUNDS + 1):
            if not pending:
                break

            emit_progress(
                f"[Negotiate] Round {round_num}/{SWARM_MAX_NEGOTIATION_ROUNDS} "
                f"({len(pending)} claims)..."
            )

            # Re-rank evidence for this round's context
            retrieved    = self.store.query(query, n_results=20)
            top_evidence = rerank(query, retrieved, top_k=5)
            evidence_ctx = "\n\n".join(
                f"[E{i+1}] {e['document'][:400]}"
                for i, e in enumerate(top_evidence)
            )

            # ── Batched voting instead of one call for all claims ──
            all_votes: list[dict] = []
            batch_no = 0
            for i in range(0, len(pending), BATCH_SIZE):
                batch = pending[i:i + BATCH_SIZE]
                batch_no += 1
                try:
                    batch_votes = self._vote_batch(batch, evidence_ctx)
                    all_votes.extend(batch_votes)
                    logger.info(
                        f"[Negotiate] Round {round_num} batch {batch_no}: "
                        f"{len(batch_votes)} LLM votes for {len(batch)} claims"
                    )
                except BatchVoteFailed as e:
                    batch_votes = self._fallback_votes(batch, str(e))
                    all_votes.extend(batch_votes)
                    logger.warning(
                        f"[Negotiate] Round {round_num} batch {batch_no}: "
                        f"fallback — marking {len(batch)} claims uncertain (API error)"
                    )
                    err_raw = str(e)
                    err_l = err_raw.lower()
                    if (
                        "429" in err_raw
                        or "rate_limit" in err_l
                        or "tpd" in err_l
                        or ("token" in err_l and "limit" in err_l)
                    ):
                        lim_msg = (
                            f"[Negotiate] Groq rate/token limit — round {round_num} "
                            f"batch {batch_no} fell back to uncertain verdicts"
                        )
                        emit_progress(lim_msg)
                        negotiate_phase.append(lim_msg)

            votes = all_votes

            outcomes: dict[str, str] = {}
            for v in votes:
                vid = v.get("claim_id", "")[:12]
                vst = v.get("vote", "uncertain")
                if vst not in ("accepted", "rejected", "uncertain"):
                    vst = "uncertain"
                outcomes[vid] = vst

            still_pending: list[Claim] = []
            for claim in pending:
                cid  = claim["claim_id"][:12]
                vote = outcomes.get(cid)
                claim["vote_rationale"] = next(
                    (v["rationale"] for v in votes
                     if v.get("claim_id", "")[:12] == cid), ""
                )
                if vote == "accepted":
                    claim["consensus_state"] = "accepted"
                    accepted.append(claim)
                elif vote == "rejected":
                    claim["consensus_state"] = "rejected"
                    rejected.append(claim)
                elif vote == "uncertain":
                    claim["consensus_state"] = "uncertain"
                    uncertain.append(claim)
                else:
                    still_pending.append(claim)

            rounds.append({
                "round_number":    round_num,
                "claims_reviewed": [c["claim_id"] for c in pending],
                "outcomes":        outcomes,
                "unresolved":      [c["claim_id"] for c in still_pending],
            })
            pending = still_pending

        # Any remaining pending claims become uncertain
        for claim in pending:
            claim["consensus_state"] = "uncertain"
            uncertain.append(claim)

        log = (
            f"[Negotiate] {len(accepted)} accepted, "
            f"{len(rejected)} rejected, {len(uncertain)} uncertain "
            f"({len(rounds)} rounds)"
        )
        logger.info(log)
        return {
            "accepted_claims":    accepted,
            "rejected_claims":    rejected,
            "uncertain_claims":   uncertain,
            "negotiation_rounds": rounds,
            "phase_log":          negotiate_phase + [log],
        }
