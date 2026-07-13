# fastapi_project/services/store_factory.py
"""
Vector Store Factory — Memilih provider berdasarkan konfigurasi.

Strategy:
    VECTOR_DB_PROVIDER="qdrant"  → QdrantStore (production)
    VECTOR_DB_PROVIDER="chroma"  → ChromaStore (legacy/fallback)
    VECTOR_DB_PROVIDER="dual"    → DualStore (write to BOTH)

Dual-write mode:
    Selama migrasi Phase 1, semua operasi write dikirim ke
    ChromaDB dan Qdrant secara paralel. Read tetap dari
    primary provider (Qdrant).
"""

import os
from typing import Optional

from .vector_store import VectorStore


# Provider constants
PROVIDER_QDRANT = "qdrant"
PROVIDER_CHROMA = "chroma"
PROVIDER_DUAL = "dual"
VALID_PROVIDERS = [PROVIDER_QDRANT, PROVIDER_CHROMA, PROVIDER_DUAL]


def get_vector_store(provider: Optional[str] = None) -> VectorStore:
    """
    Factory method — dapatkan VectorStore instance sesuai provider.

    Args:
        provider: "qdrant" | "chroma" | "dual"
                  Default: dari env VECTOR_DB_PROVIDER atau "qdrant"

    Returns:
        VectorStore instance

    Raises:
        ValueError: Jika provider tidak dikenal
    """
    if provider is None:
        provider = os.getenv("VECTOR_DB_PROVIDER", PROVIDER_QDRANT).lower()

    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"Unknown VECTOR_DB_PROVIDER '{provider}'. "
            f"Valid options: {VALID_PROVIDERS}"
        )

    if provider == PROVIDER_QDRANT:
        from .qdrant_store import QdrantStore
        print("[STORE FACTORY] Using QdrantStore (primary vector DB).")
        return QdrantStore()

    elif provider == PROVIDER_CHROMA:
        from .chroma_store import ChromaStore
        print("[STORE FACTORY] Using ChromaStore (legacy vector DB).")
        return ChromaStore()

    elif provider == PROVIDER_DUAL:
        from .qdrant_store import QdrantStore
        from .chroma_store import ChromaStore
        from .dual_store import DualStore

        primary = QdrantStore()
        secondary = ChromaStore()
        print("[STORE FACTORY] Using DualStore (write to Qdrant + ChromaDB).")
        return DualStore(primary=primary, secondary=secondary)

    # Fallback — seharusnya tidak sampai sini
    raise ValueError(f"Unexpected provider: {provider}")


def health_check_vector_store(store: VectorStore) -> dict:
    """
    Cek kesehatan vector store.

    Args:
        store: VectorStore instance

    Returns:
        dict dengan status kesehatan
    """
    is_healthy = store.health_check()
    count = store.count() if is_healthy else 0

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "type": type(store).__name__,
        "total_documents": count,
    }
