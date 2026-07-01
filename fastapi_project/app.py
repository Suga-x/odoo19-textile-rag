import os
import shutil
import chromadb
import ollama
from dotenv import load_dotenv

# Path untuk database lokal di Mac
DB_PATH = "chroma_storage_local"

# 1. HARD RESET DATABASE (Memastikan Index Fresh untuk Embedding Lokal)
if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)

print("[-] Menginisialisasi ChromaDB Lokal di Mac...")
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.create_collection(name="sop_pabrik_tekstil_local")

# 2. BACA DATA SOP MENTAH
path_sop = os.path.join("knowledge_base", "sop_celup_polyester.txt")
try:
    with open(path_sop, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
except FileNotFoundError:
    print(f"[Error]: File {path_sop} belum dibuat. Pastikan file SOP sudah ada!")
    exit(1)

# ======================================================================
# FUNGSI EMBEDDING LOKAL VIA OLLAMA (NOMIC EMBED)
# ======================================================================
def get_local_embedding(teks: str) -> list[float]:
    """Mengubah teks menjadi vektor menggunakan model khusus embedding"""
    response = ollama.embeddings(
        model='nomic-embed-text',
        prompt=teks
    )
    return response['embedding']
# ======================================================================

print(f"[-] Mentransformasikan {len(lines)} dokumen ke Vektor via Ollama...")
documents, ids, metadatas, embeddings = [], [], [], []

for index, text in enumerate(lines):
    # Memanggil fungsi get_local_embedding yang baru
    vektor = get_local_embedding(text)
    
    embeddings.append(vektor)
    documents.append(text)
    ids.append(f"id_sop_{index+1}")
    metadatas.append({"sumber": "sop_celup_polyester.txt", "engine": "nomic-embed"})

# Simpan data dan vektor murni ke ChromaDB
collection.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
print(f"[✓] Database Vektor Lokal Berhasil Dibangun! (Dimensi: {len(embeddings[0])})")

# 3. PROSES PENCARIAN SEMANTIK LOKAL
query_user = "Berapa temperature yang aman untuk tekstil sintetis?"
print(f"\n[Pertanyaan User]: '{query_user}'")

print("[-] Mengubah query menjadi vektor via Ollama lokal...")
vektor_query = get_local_embedding(query_user)

print("[-] Menghitung jarak kedekatan makna di memori lokal...")
hasil = collection.query(query_embeddings=[vektor_query], n_results=1)

terbaik_dokumen = hasil['documents'][0][0]
jarak_vektor = hasil['distances'][0][0]
print(f"[✓] SOP Terdekat Ditemukan (Jarak: {jarak_vektor:.4f}):\n    \"{terbaik_dokumen}\"")

# 4. GENERASI JAWABAN VIA OLLAMA QWEN 2.5 CODER 14B LOKAL
print("\n[-] Meminta Qwen 2.5 Coder 14B Lokal merangkum jawaban...")

prompt_rag = f"""
Anda adalah pakar sistem RAG Tekstil. Jawablah pertanyaan user secara taktis, padat, dan profesional 
HANYA berdasarkan fakta dari dokumen SOP yang disediakan. Jangan berasumsi di luar teks!

[DOKUMEN SOP PABRIK]:
{terbaik_dokumen}

[PERTANYAAN USER]:
{query_user}

Jawaban Akhir Anda (Bahasa Indonesia):
"""

try:
    # FIX: Mengubah model ke 'qwen2.5-coder:14b' sesuai environment lokal Anda
    response_ollama = ollama.generate(model='qwen2.5-coder:14b', prompt=prompt_rag)
    print("\n" + "="*20 + " RESPONS QWEN 2.5 LOKAL " + "="*20)
    print(response_ollama['response'].strip())
    print("="*64)
except Exception as e:
    print(f"[Error Ollama]: Gagal komputasi lokal. Detail: {e}")