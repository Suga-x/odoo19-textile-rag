# fastapi_project/services/dual_store.py
"""
DualStore — Dual-write vector store untuk migrasi Phase 1.

Menulis ke Qdrant (primary) dan ChromaDB (secondary) secara paralel.
Read selalu dari primary (Qdrant).

Filosofi:
    - Write ke BOTH selama migrasi (zero data loss)
    - Read dari Qdrant (lebih cepat, lebih lengkap)
    - Jika Qdrant write gagal, tetap lanjut ke ChromaDB (no downtime)
    - Grafual cutover: tinggal ganti provider dari "dual" ke "qdrant"
"""

from typing import Optional

from .vector_store import VectorStore


class DualStore(VectorStore):
    """
    Dual-write: menulis ke primary (Qdrant) dan secondary (ChromaDB).
    Read selalu dari primary.

    Args:
        primary: VectorStore utama (QdrantStore)
        secondary: VectorStore secondary (ChromaStore)
    """

    def __init__(self, primary: VectorStore, secondary: VectorStore):
        self.primary = primary
        self.secondary = secondary
        print(f"[DUAL STORE] ✅ Dual-write mode active.")
        print(f"[DUAL STORE]   Primary:   {type(primary).__name__}")
        print(f"[DUAL STORE]   Secondary: {type(secondary).__name__}")

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> bool:
        """Upsert ke PRIMARY dan SECONDARY secara paralel."""
        primary_ok = False
        secondary_ok = False

        # 1. Write ke primary (Qdrant)
        try:
            primary_ok = self.primary.upsert(ids, documents, metadatas, embeddings)
        except Exception as e:
            print(f"[DUAL STORE] ⚠️ Primary upsert failed: {e}")

        # 2. Write ke secondary (ChromaDB)
        try:
            secondary_ok = self.secondary.upsert(ids, documents, metadatas, embeddings)
        except Exception as e:
            print(f"[DUAL STORE] ⚠️ Secondary upsert failed: {e}")

        if primary_ok:
            return True
        elif secondary_ok:
            print(f"[DUAL STORE] ⚠️ Primary failed but secondary succeeded.")
            return True
        else:
            print(f"[DUAL STORE] ❌ Both primary and secondary upsert failed.")
            return False

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """Read dari PRIMARY (Qdrant). Jika gagal, fallback ke secondary."""
        try:
            return self.primary.query(query_embedding, n_results, filter_metadata)
        except Exception as e:
            print(f"[DUAL STORE] ⚠️ Primary query failed, falling back to secondary: {e}")
            try:
                return self.secondary.query(query_embedding, n_results, filter_metadata)
            except Exception as e2:
                print(f"[DUAL STORE] ❌ Both primary and secondary query failed: {e2}")
                return []

    def get_all(
        self,
        filter_metadata: Optional[dict] = None,
    ) -> tuple[list[str], list[str], list[dict]]:
        """Read dari PRIMARY."""
        try:
            return self.primary.get_all(filter_metadata)
        except Exception as e:
            print(f"[DUAL STORE] ⚠️ Primary get_all failed, fallback: {e}")
            return self.secondary.get_all(filter_metadata)

    def delete(self, ids: list[str]) -> bool:
        """Delete dari kedua store."""
        primary_ok = self.primary.delete(ids)
        secondary_ok = self.secondary.delete(ids)
        return primary_ok or secondary_ok

    def count(self) -> int:
        """Count dari PRIMARY."""
        try:
            return self.primary.count()
        except Exception:
            return self.secondary.count()

    def health_check(self) -> bool:
        """Cek PRIMARY. Jika gagal, cek SECONDARY."""
        if self.primary.health_check():
            return True
        return self.secondary.health_check()

    def delete_collection(self) -> bool:
        """Delete collection dari kedua store."""
        primary_ok = self.primary.delete_collection()
        secondary_ok = self.secondary.delete_collection()
        return primary_ok or secondary_ok
