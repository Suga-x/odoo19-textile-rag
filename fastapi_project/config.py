import os


class Settings:
    PROJECT_NAME: str = "TekstilExpertAI"
    VERSION: str = "1.0.0"

    # ──────────────────────────────────────────────────────────────
    # Vector Database — Provider Selection
    # ──────────────────────────────────────────────────────────────
    # VECTOR_DB_PROVIDER:
    #   "qdrant"  → QdrantStore (production, recommended)
    #   "chroma"  → ChromaStore (legacy, backward compat)
    #   "dual"    → DualStore (write to BOTH during migration)
    # ──────────────────────────────────────────────────────────────
    VECTOR_DB_PROVIDER: str = os.getenv("VECTOR_DB_PROVIDER", "qdrant")

    # ──────────────────────────────────────────────────────────────
    # ChromaDB (Legacy) — hanya untuk fallback / migrasi
    # ──────────────────────────────────────────────────────────────
    CHROMA_DB_PATH: str = "chroma_db_storage"
    CHROMA_COLLECTION_NAME: str = "textile_sop_collection"

    # ──────────────────────────────────────────────────────────────
    # OLD ChromaDB paths — masih dipakai main.py (akan dihapus)
    # ──────────────────────────────────────────────────────────────
    DB_PATH: str = "chroma_storage_local"
    COLLECTION_NAME: str = "sop_pabrik_tekstil_local"

    # ──────────────────────────────────────────────────────────────
    # Qdrant — Production Vector Database
    # ──────────────────────────────────────────────────────────────
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_GRPC_PORT: int = int(os.getenv("QDRANT_GRPC_PORT", 6334))
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "sop_textile")
    QDRANT_VECTOR_SIZE: int = int(os.getenv("QDRANT_VECTOR_SIZE", 768))
    QDRANT_TIMEOUT: int = int(os.getenv("QDRANT_TIMEOUT", 30))

    # ──────────────────────────────────────────────────────────────
    # AI Models Config
    # ──────────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_MODEL: str = "qwen2.5-coder:14b"

    # ──────────────────────────────────────────────────────────────
    # Chunk size
    # ──────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 300
    CHUNK_OVERLAP: int = 50


settings = Settings()
