# fastapi_project/services/vector_store.py
"""
Abstract Base Class untuk Vector Database Operations.

Polymorphism Interface:
    - ChromaStore  → ChromaDB implementation (existing, legacy)
    - QdrantStore  → Qdrant implementation (target, production-grade)

Strategy Pattern:
    - Pilih provider via config → VECTOR_DB_PROVIDER="qdrant" | "chroma"
    - Dual-write mode: write to BOTH during migration Phase 1
    - Fallback: jika Qdrant down, fallback ke ChromaDB
"""

from abc import ABC, abstractmethod
from typing import Optional


class VectorStore(ABC):
    """
    Abstract interface untuk vector database operations.
    
    Semua vector DB (ChromaDB, Qdrant, Weaviate, Pinecone) harus
    mengimplementasikan method-method di bawah ini.
    """

    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> bool:
        """
        Insert atau update (upsert) dokumen ke vector store.

        Args:
            ids: List unique ID untuk setiap chunk
            documents: List teks chunk
            metadatas: List metadata dict (division, sop_code, dll)
            embeddings: Optional — precomputed embeddings. Jika None,
                       vector store akan compute sendiri (Chromadb default EF)

        Returns:
            True jika sukses
        """
        ...

    @abstractmethod
    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        Cari dokumen terdekat berdasarkan query embedding.

        Args:
            query_embedding: Vector embedding dari pertanyaan
            n_results: Jumlah hasil yang diminta
            filter_metadata: Optional filter dict (e.g., {"division": "Dyeing"})

        Returns:
            List of dict dengan keys: id, document, metadata, distance/score
        """
        ...

    @abstractmethod
    def get_all(
        self,
        filter_metadata: Optional[dict] = None,
    ) -> tuple[list[str], list[str], list[dict]]:
        """
        Fetch semua dokumen (untuk BM25 fallback, admin listing).

        Args:
            filter_metadata: Optional filter dict

        Returns:
            Tuple (ids, documents, metadatas)
        """
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> bool:
        """
        Hapus dokumen berdasarkan IDs.

        Args:
            ids: List ID yang akan dihapus

        Returns:
            True jika sukses
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """
        Hitung total dokumen di collection.

        Returns:
            Jumlah total dokumen
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """
        Cek apakah vector store connection sehat.

        Returns:
            True jika terkoneksi dan siap, False jika error
        """
        ...

    @abstractmethod
    def delete_collection(self) -> bool:
        """
        Hapus seluruh collection — untuk reset/testing.

        Returns:
            True jika sukses
        """
        ...
