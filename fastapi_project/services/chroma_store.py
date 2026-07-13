# fastapi_project/services/chroma_store.py
"""
ChromaDB Vector Store Implementation (Legacy).

Mengimplementasikan VectorStore interface untuk ChromaDB.
Digunakan sebagai:
    - Backward compatibility selama migrasi Phase 1
    - Fallback jika Qdrant down
    - Dual-write: ChromaDB + Qdrant berjalan paralel

NOTE: ChromaDB sudah deprecated — semua data baru harus ditulis
ke Qdrant. ChromaStore hanya untuk migrasi dan fallback.
"""

import os
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from .vector_store import VectorStore


# ChromaDB default paths — dari config.py existing
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db_storage")
COLLECTION_NAME = "textile_sop_collection"


class ChromaStore(VectorStore):
    """
    ChromaDB implementation — LEGACY.
    
    Hanya digunakan untuk:
    1. Dual-write selama migrasi (Phase 1)
    2. Fallback ketika Qdrant tidak reachable
    3. Data migration ke Qdrant
    """

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        collection_name: str = COLLECTION_NAME,
    ):
        self.db_path = db_path
        self.collection_name = collection_name

        # Pastikan direktori exist
        os.makedirs(db_path, exist_ok=True)

        # Init ChromaDB client
        self.client = chromadb.PersistentClient(path=db_path)
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
        )

        print(f"[CHROMA] ✅ Connected to ChromaDB at '{db_path}', collection='{collection_name}'")

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> bool:
        """Upsert ke ChromaDB — embedding optional (ChromaDB auto-compute)."""
        try:
            if embeddings:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
            else:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
            return True
        except Exception as e:
            print(f"[CHROMA] ❌ Upsert failed: {e}")
            return False

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """Query ChromaDB dengan embedding."""
        try:
            where_filter = filter_metadata if filter_metadata else None

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter,
            )

            formatted = []
            if results and results.get("documents") and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    formatted.append({
                        "id": results["ids"][0][i] if results.get("ids") else str(i),
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "score": results["distances"][0][i] if results.get("distances") else 0.0,
                    })
            return formatted

        except Exception as e:
            print(f"[CHROMA] ❌ Query failed: {e}")
            return []

    def get_all(
        self,
        filter_metadata: Optional[dict] = None,
    ) -> tuple[list[str], list[str], list[dict]]:
        """Fetch semua dokumen dari ChromaDB."""
        try:
            where_filter = filter_metadata if filter_metadata else None
            all_data = self.collection.get(where=where_filter)

            ids = all_data.get("ids", [])
            documents = all_data.get("documents", [])
            metadatas = all_data.get("metadatas", [])

            return ids, documents, metadatas

        except Exception as e:
            print(f"[CHROMA] ❌ get_all failed: {e}")
            return [], [], []

    def delete(self, ids: list[str]) -> bool:
        """Delete dari ChromaDB."""
        try:
            self.collection.delete(ids=ids)
            return True
        except Exception as e:
            print(f"[CHROMA] ❌ Delete failed: {e}")
            return False

    def count(self) -> int:
        """Hitung total dokumen."""
        try:
            return self.collection.count()
        except Exception as e:
            print(f"[CHROMA] ❌ Count failed: {e}")
            return 0

    def health_check(self) -> bool:
        """Cek koneksi ChromaDB."""
        try:
            self.collection.count()
            return True
        except Exception:
            return False

    def delete_collection(self) -> bool:
        """Hapus collection."""
        try:
            self.client.delete_collection(self.collection_name)
            # Re-create
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
            )
            return True
        except Exception as e:
            print(f"[CHROMA] ❌ delete_collection failed: {e}")
            return False
