import ollama
from config import settings

class EmbeddingService:
    @staticmethod
    def get_embedding(text: str) -> list[float]:
        """Mengubah teks menjadi koordinat vektor secara lokal"""
        try:
            response = ollama.embeddings(
                model=settings.EMBEDDING_MODEL, 
                prompt=text
            )
            return response['embedding']
        except Exception as e:
            raise RuntimeError(f"Gagal melakukan embedding via Ollama: {str(e)}")