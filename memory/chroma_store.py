from chromadb import PersistentClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


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

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        results = self.collection.query(query_texts=[query_text], n_results=n_results)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for document, metadata, distance in zip(documents, metadatas, distances)
        ]

    def clear_collection(self):
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )
