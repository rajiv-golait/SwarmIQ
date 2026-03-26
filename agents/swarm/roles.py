from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.analyst import Analyst
from agents.researcher import Researcher
from agents.synthesizer import Synthesizer
from agents.swarm.protocol import AgentResult, AgentTask, Claim, ConsensusState, Phase
from utils.config import FAST_MODEL


@dataclass(frozen=True)
class RoleSpec:
    role_id: str
    description: str


ROLE_SPECS = {
    "planner": RoleSpec(
        role_id="planner",
        description="Decomposes user query into parallel subtasks with success criteria.",
    ),
    "literature_reviewer": RoleSpec(
        role_id="literature_reviewer",
        description="Retrieves evidence and publishes structured claims to vector memory.",
    ),
    "summarizer": RoleSpec(
        role_id="summarizer",
        description="Creates condensed evidence summaries with confidence scores.",
    ),
    "conflict_resolver": RoleSpec(
        role_id="conflict_resolver",
        description="Facilitates multi-round negotiation and votes on claim consensus.",
    ),
    "synthesizer": RoleSpec(
        role_id="synthesizer",
        description="Builds final report from consensus-approved claims only.",
    ),
    "visualizer": RoleSpec(
        role_id="visualizer",
        description="Generates data visualizations and charts from approved evidence.",
    ),
}


class PlannerRole:
    agent_id = "planner"

    def __call__(self, task: AgentTask) -> AgentResult:
        """Planner decomposes query into parallel subtasks."""
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        query = task.payload.get("query", "").strip()

        # More sophisticated decomposition
        segments = [part.strip() for part in query.split("?") if part.strip()]
        subtasks = []

        for seg in segments[:3]:
            if seg:
                subtasks.append({
                    "type": "evidence_gathering",
                    "description": f"Gather evidence on: {seg}",
                    "success_criteria": "Find at least 2 sources with conflicting or complementary evidence",
                })

        if len(subtasks) < 2 and query:
            subtasks = [
                {
                    "type": "context_research",
                    "description": f"Context and background for: {query}",
                    "success_criteria": "Identify key concepts and recent developments",
                },
                {
                    "type": "evidence_synthesis",
                    "description": f"Latest evidence and conflicting viewpoints for: {query}",
                    "success_criteria": "Find at least 2 sources with differing perspectives",
                },
            ]

        return AgentResult(
            agent_id=self.agent_id,
            phase=task.phase,
            task_id=task.task_id,
            content={"subtasks": subtasks, "original_query": query, "parallelizable": True},
            notes="Planner created decomposed subtasks for parallel execution.",
            status="success",
        )


class LiteratureReviewRole:
    agent_id = "literature_reviewer"

    def __init__(self, researcher: Researcher):
        self.researcher = researcher

    def __call__(self, task: AgentTask) -> AgentResult:
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        """Retrieve evidence and produce structured claims."""
        subtask = task.payload.get("subtask", {})
        query = task.payload.get("query", "")
        description = subtask.get("description", query)

        # Execute research
        result = self.researcher.research(description)

        # Convert research results to structured claims
        claims = []
        raw_results = result.get("raw_results", [])
        sources = result.get("sources", [])
        chunk_ids = result.get("chunk_ids", [])  # Real Chroma chunk IDs
        evidence_map = result.get("evidence_map", {})  # chunk_id -> metadata

        for i, (content, source) in enumerate(zip(raw_results, sources)):
            # Get the real chunk_id for this source
            chunk_id = chunk_ids[i] if i < len(chunk_ids) else None
            if not chunk_id:
                continue

            # Split content into key claims
            claim_statements = self._extract_claims(content)

            for claim_text in claim_statements[:3]:  # Top 3 claims per source
                claims.append({
                    "statement": claim_text,
                    "evidence_ids": [chunk_id],  # Use real chunk_id
                    "confidence": 0.8 if i < 2 else 0.7,
                    "source_url": source,
                })

        return AgentResult(
            agent_id=self.agent_id,
            phase=task.phase,
            task_id=task.task_id,
            content={
                "research_result": result,
                "claims": claims,
                "stored_count": result.get("stored_count", 0),
                "evidence_map": evidence_map,  # Pass real evidence metadata
            },
            notes=f"Literature reviewer produced {len(claims)} claims from {len(sources)} sources",
            status="success",
            evidence_refs=[c["evidence_ids"][0] for c in claims if c.get("evidence_ids")],
        )

    def _extract_claims(self, content: str) -> list[str]:
        """Extract key claim statements from content."""
        # Simple sentence-based extraction
        sentences = content.replace("!", ".").replace("?", ".").split(".")
        claims = [s.strip() for s in sentences if len(s.strip()) > 30 and len(s.strip()) < 200]
        return claims[:5]  # Return top 5 claims


class SummarizerRole:
    agent_id = "summarizer"

    def __init__(self, synthesizer: Synthesizer, researcher: Researcher = None):
        self.synthesizer = synthesizer
        self.researcher = researcher

    def __call__(self, task: AgentTask) -> AgentResult:
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        """Create summary claims from subtask execution using real research."""
        subtask = task.payload.get("subtask", {})
        query = task.payload.get("query", "")

        # For summarization, also do real research to get grounded claims
        description = subtask.get("description", f"Summary: {query}")

        # Execute research to get real evidence chunks
        research_result = None
        evidence_map = {}
        if self.researcher:
            try:
                research_result = self.researcher.research(description)
                evidence_map = research_result.get("evidence_map", {})
            except Exception as e:
                print(f"Summarizer research failed: {e}")

        # Use synthesizer's groq client for summary
        try:
            completion = self.synthesizer.groq_client.chat.completions.create(
                model=self.synthesizer.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract 2-3 key factual claims from the query topic. Return as bullet points.",
                    },
                    {"role": "user", "content": description},
                ],
            )
            summary_text = completion.choices[0].message.content or ""

            # Parse claims from summary and map to real evidence if available
            claims = []
            chunk_ids = list(evidence_map.keys()) if evidence_map else []

            for line in summary_text.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    claim_text = line.lstrip("-* ").strip()
                    if claim_text:
                        # Assign real chunk_id if available, otherwise mark as ungrounded
                        evidence_ids = []
                        if chunk_ids and len(claims) < len(chunk_ids):
                            evidence_ids = [chunk_ids[len(claims)]]
                        claims.append({
                            "statement": claim_text,
                            "evidence_ids": evidence_ids if evidence_ids else ["ungrounded"],
                            "confidence": 0.75,
                        })

            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "claims": claims,
                    "summary": summary_text,
                    "evidence_map": evidence_map,  # Pass real evidence metadata
                },
                notes=f"Summarizer produced {len(claims)} summary claims with {len(chunk_ids)} real evidence chunks",
                status="success",
                evidence_refs=[c["evidence_ids"][0] for c in claims if c.get("evidence_ids") and c["evidence_ids"][0] != "ungrounded"],
            )
        except Exception as e:
            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={"claims": [], "error": str(e)},
                notes=f"Summarizer failed: {e}",
                status="failure",
            )


class ConflictResolverRole:
    agent_id = "conflict_resolver"

    def __init__(self, analyst: Analyst):
        self.analyst = analyst

    def __call__(self, task: AgentTask) -> AgentResult:
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        """Negotiate claims and produce consensus votes."""
        claims_data = task.payload.get("claims", [])
        round_num = task.payload.get("round", 1)

        if not claims_data:
            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={"votes": [], "conflicts_detected": False},
                notes="No claims to negotiate",
                status="success",
            )

        # Use analyst to identify potential conflicts
        claims_text = "\n".join([
            f"Claim {c['claim_id']}: {c['statement']} (from {c['agent_id']}, confidence: {c['confidence']})"
            for c in claims_data
        ])

        try:
            completion = self.analyst.groq_client.chat.completions.create(
                model=self.analyst.model,
                max_tokens=800,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a conflict resolver. Review the claims and identify any contradictions. "
                            "For each claim, vote: ACCEPTED (no conflict, high confidence), "
                            "REJECTED (contradicted by stronger evidence), or "
                            "UNCERTAIN (insufficient evidence to decide). "
                            "Return your response as: CLAIM_ID|VOTE|RATIONALE"
                        ),
                    },
                    {"role": "user", "content": f"Claims to review:\n{claims_text}"},
                ],
            )
            resolution_text = completion.choices[0].message.content or ""

            # Parse votes
            votes = []
            for line in resolution_text.split("\n"):
                line = line.strip()
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        claim_id = parts[0].strip()
                        vote_str = parts[1].strip().upper()
                        rationale = parts[2].strip()

                        # Map to ConsensusState
                        vote_map = {
                            "ACCEPTED": ConsensusState.ACCEPTED,
                            "REJECTED": ConsensusState.REJECTED,
                            "UNCERTAIN": ConsensusState.UNCERTAIN,
                        }
                        vote_state = vote_map.get(vote_str, ConsensusState.UNCERTAIN)

                        votes.append({
                            "claim_id": claim_id,
                            "vote": vote_state.value,
                            "rationale": rationale,
                            "confidence": 0.8 if vote_state == ConsensusState.ACCEPTED else 0.6,
                        })

            conflicts_detected = any(v["vote"] != ConsensusState.ACCEPTED.value for v in votes)

            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "votes": votes,
                    "conflicts_detected": conflicts_detected,
                    "round": round_num,
                },
                notes=f"Conflict resolver cast {len(votes)} votes in round {round_num}",
                status="success",
            )

        except Exception as e:
            # Fallback: accept all claims if analysis fails
            votes = [
                {
                    "claim_id": c["claim_id"],
                    "vote": ConsensusState.ACCEPTED.value,
                    "rationale": f"Fallback acceptance due to error: {e}",
                    "confidence": 0.5,
                }
                for c in claims_data
            ]

            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={"votes": votes, "conflicts_detected": False, "fallback": True},
                notes=f"Conflict resolver used fallback due to error: {e}",
                status="partial",
            )


class SynthesisRole:
    agent_id = "synthesizer"

    def __init__(self, synthesizer: Synthesizer):
        self.synthesizer = synthesizer

    def __call__(self, task: AgentTask) -> AgentResult:
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        """Synthesize paper-like research report from consensus-approved claims with real citations."""
        query = task.payload.get("query", "")
        accepted_claims = task.payload.get("accepted_claims", [])
        uncertain_claims = task.payload.get("uncertain_claims", [])
        evidence_map = task.payload.get("evidence_map", {})  # chunk_id -> {source_url, title, published_at, content}

        if not accepted_claims:
            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={"report": "No consensus-approved claims to synthesize.", "word_count": 0},
                notes="No accepted claims available for synthesis",
                status="partial",
            )

        # Build numbered sources from evidence_map for proper citations
        # Create unique list of sources with URLs
        unique_sources = []
        chunk_id_to_source_idx = {}

        for i, claim in enumerate(accepted_claims):
            for chunk_id in claim.get("evidence_chunk_ids", []):
                if chunk_id and chunk_id in evidence_map and chunk_id not in chunk_id_to_source_idx:
                    evidence = evidence_map[chunk_id]
                    source_url = evidence.get("source_url", "")
                    if source_url:
                        idx = len(unique_sources) + 1  # 1-based indexing
                        chunk_id_to_source_idx[chunk_id] = idx
                        unique_sources.append({
                            "number": idx,
                            "url": source_url,
                            "title": evidence.get("title", "Unknown Source"),
                            "published_at": evidence.get("published_at", ""),
                            "excerpt": evidence.get("content", "")[:300],  # First 300 chars
                        })

        # Map claims to source numbers
        claims_with_sources = []
        for i, claim in enumerate(accepted_claims):
            source_numbers = []
            for chunk_id in claim.get("evidence_chunk_ids", []):
                if chunk_id in chunk_id_to_source_idx:
                    source_numbers.append(chunk_id_to_source_idx[chunk_id])
            claims_with_sources.append({
                "number": i + 1,
                "statement": claim["statement"],
                "confidence": claim["confidence"],
                "source_numbers": source_numbers,
            })

        # Build claims text with source references
        claims_text = "\n\n".join([
            f"[{c['number']}] {c['statement']} (confidence: {c['confidence']}, sources: {', '.join([f'[{n}]' for n in c['source_numbers']])})"
            for c in claims_with_sources
        ])

        # Build sources reference text
        sources_text = "\n".join([
            f"[{s['number']}] {s['title']} - {s['url']}{' (Published: ' + s['published_at'] + ')' if s['published_at'] else ''}"
            for s in unique_sources
        ])

        # Build evidence excerpts for synthesis context
        excerpts_text = "\n\n".join([
            f"[Source {s['number']}] {s['title']}\nURL: {s['url']}\nExcerpt: {s['excerpt']}..."
            for s in unique_sources[:5]  # Top 5 for context
        ])

        uncertain_text = ""
        if uncertain_claims:
            uncertain_text = "\n\nUncertain claims requiring further verification:\n" + "\n".join([
                f"- {c['statement']}"
                for c in uncertain_claims
            ])

        # Try synthesis with primary model, fallback to FAST_MODEL on 429
        report = ""
        model_used = self.synthesizer.model

        for attempt in range(2):
            try:
                completion = self.synthesizer.groq_client.chat.completions.create(
                    model=model_used,
                    max_tokens=2500,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a research synthesizer creating a professional research paper. "
                                "Use the provided evidence excerpts and claims to write a comprehensive, "
                                "well-structured research report. Cite sources using inline citation numbers "
                                "like [1], [2], etc. that correspond to the provided numbered sources. "
                                "\n\nStructure your report with these sections (adapt to the query):\n"
                                "1. Executive Summary - Brief overview of key findings\n"
                                "2. Key Findings / Evidence-backed claims - Main results with citations\n"
                                "3. Conflict/Uncertainty section - Note any rejected or uncertain claims\n"
                                "4. Policy Implications / Next Steps - Practical recommendations\n"
                                "5. Limitations / Gaps - Acknowledge evidence limitations\n"
                                "6. Conclusion - Summary and future outlook\n"
                                "7. References - List all numbered sources with full URLs (use format: [n] Title - URL)\n\n"
                                "Write in a professional academic tone. Ensure all claims are grounded in evidence."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Research Query: {query}\n\n"
                                f"Evidence Excerpts:\n{excerpts_text}\n\n"
                                f"Consensus-approved claims:\n{claims_text}"
                                f"{uncertain_text}\n\n"
                                f"Numbered Sources:\n{sources_text}\n\n"
                                f"Write a comprehensive research paper using the evidence above. "
                                f"Cite sources inline using [n] notation. Include all {len(unique_sources)} sources in the References section."
                            ),
                        },
                    ],
                )
                report = completion.choices[0].message.content or ""
                break  # Success, exit retry loop

            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = (
                    "429" in str(e)
                    or "rate_limit" in error_str
                    or "rate limit" in error_str
                    or "too many requests" in error_str
                )

                if is_rate_limit and attempt == 0:
                    # Fallback to FAST_MODEL on rate limit
                    model_used = FAST_MODEL
                    continue
                elif attempt == 1:
                    # Second attempt also failed
                    return AgentResult(
                        agent_id=self.agent_id,
                        phase=task.phase,
                        task_id=task.task_id,
                        content={
                            "report": f"Synthesis failed: {e}. Please try again later.",
                            "word_count": 0,
                            "error": str(e),
                            "fallback_used": model_used == FAST_MODEL,
                        },
                        notes=f"Synthesis failed after retry with {model_used}: {e}",
                        status="failure",
                    )
                else:
                    return AgentResult(
                        agent_id=self.agent_id,
                        phase=task.phase,
                        task_id=task.task_id,
                        content={
                            "report": f"Synthesis failed: {e}",
                            "word_count": 0,
                            "error": str(e),
                        },
                        notes=f"Synthesis failed: {e}",
                        status="failure",
                    )

        # Append References section if missing
        if "## References" not in report and "## Sources" not in report:
            report += f"\n\n## References\n\n{sources_text}"

        return AgentResult(
            agent_id=self.agent_id,
            phase=task.phase,
            task_id=task.task_id,
            content={
                "report": report,
                "word_count": len(report.split()),
                "sources_used": [s["url"] for s in unique_sources],
                "sources_count": len(unique_sources),
                "claims_used": len(accepted_claims),
                "uncertain_mentioned": len(uncertain_claims),
                "reference_list": unique_sources,  # For export
                "fallback_used": model_used == FAST_MODEL,
            },
            notes=f"Synthesized research paper from {len(accepted_claims)} claims with {len(unique_sources)} real sources (model: {model_used})",
            status="success",
        )


class VisualizationRole:
    agent_id = "visualizer"

    def __call__(self, task: AgentTask) -> AgentResult:
        return self.run(task)

    def run(self, task: AgentTask) -> AgentResult:
        """Generate visualization artifacts from approved claims."""
        accepted_claims = task.payload.get("accepted_claims", [])
        query = task.payload.get("query", "")

        if not accepted_claims:
            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={"visualization": None, "type": None},
                notes="No data available for visualization",
                status="success",
            )

        # Generate a mermaid diagram or table
        viz_type = "timeline" if "timeline" in query.lower() or "history" in query.lower() else "table"

        if viz_type == "timeline":
            # Create a simple timeline mermaid diagram
            timeline_items = []
            for i, claim in enumerate(accepted_claims[:5]):
                timeline_items.append(f"    {i+1} : {claim['statement'][:50]}...")

            mermaid = "timeline\n    title Key Claims Timeline\n" + "\n".join(timeline_items)

            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "visualization": mermaid,
                    "type": "mermaid_timeline",
                    "claims_count": len(accepted_claims),
                },
                notes=f"Generated timeline visualization with {len(accepted_claims)} claims",
                status="success",
            )
        else:
            # Create a claims summary table
            table_rows = []
            for claim in accepted_claims:
                table_rows.append({
                    "claim": claim["statement"][:60] + "...",
                    "confidence": claim["confidence"],
                    "evidence_count": len(claim.get("evidence_chunk_ids", [])),
                })

            return AgentResult(
                agent_id=self.agent_id,
                phase=task.phase,
                task_id=task.task_id,
                content={
                    "visualization": table_rows,
                    "type": "table",
                    "claims_count": len(accepted_claims),
                },
                notes=f"Generated table visualization with {len(accepted_claims)} claims",
                status="success",
            )
