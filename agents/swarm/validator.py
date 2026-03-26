from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from memory.chroma_store import ChromaStore


@dataclass
class ValidationResult:
    claim_text: str
    evidence_ids: list[str]
    grounding_score: float
    status: str  # "verified", "partial", "unverified"
    issues: list[str]


@dataclass
class CitationCheck:
    citation_number: int
    evidence_id: str | None
    verified: bool
    context_match: float


class ClaimValidator:
    """Validates that claims are properly grounded in evidence."""

    citation_pattern = re.compile(r"\[(\d+)\]")

    def __init__(self, chroma_store: ChromaStore | None = None):
        self.chroma_store = chroma_store

    def validate_report(
        self,
        report: str,
        accepted_claims: list[dict],
        evidence_lookup: dict[str, str],
    ) -> dict[str, Any]:
        """Validate entire report against claim-level grounding requirements."""
        validation_results = []
        total_score = 0.0

        # Extract claim sentences from report
        claim_sentences = self._extract_claim_sentences(report)

        for sentence in claim_sentences:
            # Find citations in sentence
            citations = self.citation_pattern.findall(sentence)

            if not citations:
                validation_results.append({
                    "sentence": sentence,
                    "status": "unverified",
                    "grounding_score": 0.0,
                    "issues": ["No inline citation found"],
                })
                continue

            # Validate each citation
            for citation_num in citations:
                evidence_id = evidence_lookup.get(citation_num)

                if not evidence_id:
                    validation_results.append({
                        "sentence": sentence,
                        "status": "unverified",
                        "grounding_score": 0.0,
                        "issues": [f"Citation [{citation_num}] not found in evidence lookup"],
                    })
                    continue

                # Check if evidence exists in store
                if self.chroma_store:
                    evidence_results = self.chroma_store.query_by_evidence_ids([evidence_id])
                    if not evidence_results:
                        validation_results.append({
                            "sentence": sentence,
                            "status": "unverified",
                            "grounding_score": 0.0,
                            "issues": [f"Evidence {evidence_id} not found in vector store"],
                        })
                        continue

                    # Semantic check: does evidence support the claim?
                    evidence_text = evidence_results[0]["document"]
                    grounding_score = self._compute_grounding_score(sentence, evidence_text)

                    status = "verified" if grounding_score > 0.7 else "partial" if grounding_score > 0.4 else "unverified"

                    validation_results.append({
                        "sentence": sentence,
                        "citation": citation_num,
                        "evidence_id": evidence_id,
                        "status": status,
                        "grounding_score": grounding_score,
                        "issues": [] if status == "verified" else [f"Low semantic match: {grounding_score:.2f}"],
                    })
                    total_score += grounding_score
                else:
                    # Fallback when vector store is unavailable in validator context.
                    validation_results.append({
                        "sentence": sentence,
                        "citation": citation_num,
                        "evidence_id": evidence_id,
                        "status": "partial",
                        "grounding_score": 0.5,
                        "issues": ["Vector store unavailable for semantic grounding check"],
                    })
                    total_score += 0.5

        # Calculate overall stats
        if validation_results:
            scored_results = [r for r in validation_results if r.get("grounding_score", 0) > 0]
            avg_score = total_score / len(scored_results) if scored_results else 0.0
            verified_count = sum(1 for r in validation_results if r["status"] == "verified")
            unverified_count = sum(1 for r in validation_results if r["status"] == "unverified")
        else:
            avg_score = 0.0
            verified_count = 0
            unverified_count = 0

        passed = verified_count > 0 and unverified_count == 0 and avg_score > 0.6

        return {
            "passed": passed,
            "average_grounding_score": avg_score,
            "verified_claims": verified_count,
            "partial_claims": sum(1 for r in validation_results if r["status"] == "partial"),
            "unverified_claims": unverified_count,
            "details": validation_results,
            "reason": "All claims properly grounded" if passed else f"{unverified_count} claims unverified",
        }

    def _extract_claim_sentences(self, report: str) -> list[str]:
        """Extract sentences that make factual claims."""
        # Split into sentences
        sentences = re.split(r'[.!?]+', report)

        # Filter for claim-like sentences (contain facts, data, assertions)
        claim_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue

            # Check for claim indicators
            claim_indicators = [
                "is", "are", "was", "were", "has", "have", "shows", "indicates",
                "demonstrates", "reveals", "found", "concluded", "reported",
                "according to", "data", "study", "research", "analysis",
            ]

            if any(indicator in sentence.lower() for indicator in claim_indicators):
                claim_sentences.append(sentence)

        return claim_sentences

    def _compute_grounding_score(self, claim: str, evidence: str) -> float:
        """Compute semantic similarity between claim and evidence."""
        # Simple keyword overlap score
        claim_words = set(claim.lower().split())
        evidence_words = set(evidence.lower().split())

        if not claim_words:
            return 0.0

        overlap = claim_words & evidence_words
        return len(overlap) / len(claim_words)

    def validate_consensus_alignment(
        self,
        report: str,
        accepted_claims: list[dict],
        uncertain_claims: list[dict],
    ) -> dict[str, Any]:
        """Verify report properly represents consensus states."""
        issues = []

        # Check that uncertain claims are properly marked
        uncertain_statements = [c["statement"] for c in uncertain_claims]

        for uncertain in uncertain_statements:
            # Check if uncertain claim appears in report without proper qualification
            if uncertain[:50] in report and "uncertain" not in report.lower():
                issues.append(f"Uncertain claim may not be properly qualified: {uncertain[:50]}...")

        # Check conflict resolution is mentioned
        has_conflict_section = "conflict" in report.lower() or "resolution" in report.lower()

        passed = len(issues) == 0

        return {
            "passed": passed,
            "issues": issues,
            "has_conflict_section": has_conflict_section,
            "uncertain_claims_count": len(uncertain_claims),
            "accepted_claims_count": len(accepted_claims),
            "reason": "Consensus alignment verified" if passed else f"{len(issues)} alignment issues",
        }


class CitationGroundingValidator:
    """Validates that citations in report map to actual evidence chunks."""

    def __init__(self, chroma_store: ChromaStore):
        self.chroma_store = chroma_store

    def validate(
        self,
        report: str,
        claim_to_evidence_map: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Validate that every claim maps to retrievable evidence."""
        results = []

        for claim_id, evidence_ids in claim_to_evidence_map.items():
            if not evidence_ids:
                results.append({
                    "claim_id": claim_id,
                    "status": "ungrounded",
                    "issues": ["No evidence IDs provided"],
                })
                continue

            # Verify evidence exists
            evidence_docs = self.chroma_store.query_by_evidence_ids(evidence_ids)

            if len(evidence_docs) != len(evidence_ids):
                missing = len(evidence_ids) - len(evidence_docs)
                results.append({
                    "claim_id": claim_id,
                    "status": "partial",
                    "issues": [f"{missing} evidence chunks not found in vector store"],
                })
            else:
                results.append({
                    "claim_id": claim_id,
                    "status": "grounded",
                    "evidence_count": len(evidence_docs),
                    "issues": [],
                })

        ungrounded = sum(1 for r in results if r["status"] == "ungrounded")
        passed = ungrounded == 0

        return {
            "passed": passed,
            "grounded_claims": sum(1 for r in results if r["status"] == "grounded"),
            "partial_claims": sum(1 for r in results if r["status"] == "partial"),
            "ungrounded_claims": ungrounded,
            "details": results,
            "reason": "All claims grounded in evidence" if passed else f"{ungrounded} claims ungrounded",
        }


class CitationReferenceValidator:
    """Validates that inline citations [n] map to URLs in the References/Sources section."""

    citation_pattern = re.compile(r"\[(\d+)\]")

    def parse_references_section(self, report: str) -> dict[int, str]:
        """Parse the References or Sources section to extract numbered URLs."""
        reference_map = {}

        # Find References or Sources section
        ref_match = re.search(r"(?:##?\s*(?:References|Sources|Bibliography).*?)(?:\n\n|\Z)", report, re.IGNORECASE | re.DOTALL)
        if not ref_match:
            return reference_map

        ref_section = ref_match.group(0)

        # Parse numbered references like [1] Title - URL or [1] URL
        ref_lines = ref_section.split("\n")
        for line in ref_lines:
            line = line.strip()
            if not line:
                continue

            # Match [n] pattern at start
            num_match = self.citation_pattern.match(line)
            if num_match:
                num = int(num_match.group(1))
                # Extract URL from line
                url_match = re.search(r"(https?://\S+)[\s\)\]]*", line)
                if url_match:
                    reference_map[num] = url_match.group(1)

        return reference_map

    def validate_citation_consistency(self, report: str) -> dict[str, Any]:
        """Validate that all inline citations appear in References section."""
        # Parse references
        reference_map = self.parse_references_section(report)

        # Find all inline citations
        inline_citations = set(self.citation_pattern.findall(report))
        inline_citations = {int(c) for c in inline_citations}

        # Check each citation has a matching reference
        missing_refs = []
        valid_refs = []

        for citation_num in inline_citations:
            if citation_num in reference_map:
                valid_refs.append({
                    "citation": citation_num,
                    "url": reference_map[citation_num],
                })
            else:
                missing_refs.append(citation_num)

        # Check for references not cited
        uncited_refs = [num for num in reference_map if num not in inline_citations]

        passed = len(missing_refs) == 0

        return {
            "passed": passed,
            "inline_citations_found": len(inline_citations),
            "references_parsed": len(reference_map),
            "valid_mappings": len(valid_refs),
            "missing_references": missing_refs,
            "uncited_references": uncited_refs,
            "reference_list": [
                {"number": num, "url": url} for num, url in reference_map.items()
            ],
            "reason": "All citations have matching references" if passed else f"{len(missing_refs)} citations missing references",
        }
