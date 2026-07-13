# Menggunakan python base image yang stabil dan ringan
FROM python:3.11-slim

# Atur direktori kerja di dalam kontainer
WORKDIR /app

# Salin requirements.txt terlebih dahulu untuk memanfaatkan Docker layer caching
RUN pip install --no-cache-dir \
    google-generativeai==0.8.3 \
    numpy==1.26.4 \
    fastapi==0.110.0 \
    uvicorn==0.28.0 \
    chromadb==0.4.24 \
    pydantic==2.6.4 \
    langchain-text-splitters==0.0.1 \
    rank-bm25==0.2.2 \
    litellm==1.34.22 \
    python-multipart==0.0.9 \
    ollama==0.2.1 \
    celery==5.3.6 \
    redis==5.0.7 \
    qdrant-client==1.9.0

# Salin seluruh kode sumber proyek ke dalam kontainer
COPY . .

# Ekspos port FastAPI sesuai standar aplikasi Anda
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]