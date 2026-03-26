import hashlib
from datetime import datetime, timezone
from typing import Literal

from chromadb import PersistentClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

EvidenceType = Literal["fact", "counter_fact", "summary", "visual_data", "claim", "report"]


class ChromaStore:
    def __init__(self, collection_name="swarmiq", persist_dir="./chroma_db"):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.embedding_function = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.client = PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )

    def add_documents(self, documents: list[str], metadatas: list[dict], ids: list[str]):
        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def add_claim(
        self,
        *,
        claim_id: str,
        statement: str,
        agent_id: str,
        evidence_chunk_ids: list[str],
        confidence: float,
        parent_claim_id: str = "",
        consensus_state: str = "pending",
        source_url: str = "",
    ) -> str:
        """Add a structured claim with provenance to the store."""
        metadata = {
            "type": "claim",
            "claim_id": claim_id,
            "agent_id": agent_id,
            "evidence_chunk_ids": ",".join(evidence_chunk_ids),
            "confidence": confidence,
            "parent_claim_id": parent_claim_id,
            "consensus_state": consensus_state,
            "source_url": source_url,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        self.collection.upsert(
            documents=[statement],
            metadatas=[metadata],
            ids=[claim_id],
        )
        return claim_id

    def add_evidence(
        self,
        *,
        content: str,
        evidence_type: EvidenceType,
        agent_id: str,
        source_url: str = "",
        claim_id: str = "",
        parent_evidence_id: str = "",
        confidence: float = 1.0,
    ) -> str:
        """Add evidence with full provenance tracking."""
        evidence_id = self.stable_id(agent_id, source_url, content[:100], str(datetime.now(timezone.utc).timestamp()))

        metadata = {
            "type": evidence_type,
            "agent_id": agent_id,
            "source_url": source_url,
            "claim_id": claim_id,
            "parent_evidence_id": parent_evidence_id,
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        self.collection.upsert(
            documents=[content],
            metadatas=[metadata],
            ids=[evidence_id],
        )
        return evidence_id

    @staticmethod
    def stable_id(*parts: str) -> str:
        normalized = "::".join((part or "").strip().lower() for part in parts)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def citation_metadata(
        *,
        source_url: str,
        title: str,
        published_at: str = "",
        chunk_id: str,
        agent_id: str,
        query: str = "",
    ) -> dict:
        return {
            "type": "citation",
            "source_url": source_url or "",
            "title": title or "",
            "published_at": published_at or "",
            "chunk_id": chunk_id,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "agent_id": agent_id,
            "query": query,
        }

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        results = self.collection.query(query_texts=[query_text], n_results=n_results)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "id": doc_id,
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances)
        ]

    def query_by_agent(self, agent_id: str, n_results: int = 20) -> list[dict]:
        """Query all evidence produced by a specific agent."""
        results = self.collection.query(
            query_texts=[""],
            where={"agent_id": agent_id},
            n_results=n_results,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "id": doc_id,
                "document": document,
                "metadata": metadata,
            }
            for doc_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def query_claims_by_state(self, consensus_state: str, n_results: int = 20) -> list[dict]:
        """Query claims by their consensus state (accepted/rejected/uncertain/pending)."""
        results = self.collection.query(
            query_texts=[""],
            where={"consensus_state": consensus_state},
            n_results=n_results,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "id": doc_id,
                "statement": document,
                "metadata": metadata,
            }
            for doc_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def query_by_evidence_ids(self, evidence_ids: list[str]) -> list[dict]:
        """Retrieve specific evidence chunks by their IDs."""
        if not evidence_ids:
            return []

        results = self.collection.get(ids=evidence_ids)

        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        ids = results.get("ids", [])

        return [
            {
                "id": doc_id,
                "document": document,
                "metadata": metadata,
            }
            for doc_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def update_claim_consensus(self, claim_id: str, consensus_state: str) -> bool:
        """Update the consensus state of a claim."""
        try:
            # Get existing
            existing = self.collection.get(ids=[claim_id])
            if not existing.get("ids"):
                return False

            # Update metadata
            metadata = existing["metadatas"][0]
            metadata["consensus_state"] = consensus_state
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

            self.collection.upsert(
                documents=[existing["documents"][0]],
                metadatas=[metadata],
                ids=[claim_id],
            )
            return True
        except Exception:
            return False

    def clear_collection(self):
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )
