import os

class Settings:
    PROJECT_NAME: str = "TekstilExpertAI"
    VERSION: str = "1.0.0"
    
    # Database Config
    DB_PATH: str = "chroma_storage_local"
    COLLECTION_NAME: str = "sop_pabrik_tekstil_local"
    
    # AI Models Config
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_MODEL: str = "qwen2.5-coder:14b"

    # Chunk size
    CHUNK_SIZE: int = 300
    CHUNK_OVERLAP: int = 50

settings = Settings()