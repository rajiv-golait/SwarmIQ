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


class ConflictResolverNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

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

        pending   = list(all_claims)
        accepted: list[Claim]          = []
        rejected: list[Claim]          = []
        uncertain: list[Claim]         = []
        rounds:   list[NegotiationRound] = []

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

            claims_text = "\n".join(
                f"ID:{c['claim_id'][:12]} | "
                f"Conf:{c['confidence']:.2f} | "
                f"{c['statement'][:150]}"
                for c in pending
            )

            groq_limiter.wait_if_needed(1200)
            try:
                resp = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Vote on each claim: accepted, rejected, or uncertain. "
                                'Return ONLY valid json: {"votes": [{"claim_id": "...", '
                                '"vote": "accepted|rejected|uncertain", "rationale": "..."}]}'
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Evidence:\n{evidence_ctx}\n\n"
                                f"Claims:\n{claims_text}"
                            ),
                        },
                    ],
                )
                data  = json.loads(resp.choices[0].message.content or "{}")
                votes = data.get("votes", [])
            except Exception as e:
                logger.error(f"[Negotiate] Round {round_num} failed: {e}")
                votes = [
                    {"claim_id": c["claim_id"][:12],
                     "vote": "accepted", "rationale": f"fallback:{e}"}
                    for c in pending
                ]

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
            "phase_log":          [log],
        }
