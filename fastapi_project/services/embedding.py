import ollama
from config import settings

class EmbeddingService:
    @staticmethod
    def get_embedding(text: str) -> list[float]:
        """Convert text into a local vector embedding"""
        try:
            response = ollama.embeddings(
                model=settings.EMBEDDING_MODEL,
                prompt=text
            )
            return response['embedding']
        except Exception as e:
            raise RuntimeError(f"Failed to generate embedding via Ollama: {str(e)}")
