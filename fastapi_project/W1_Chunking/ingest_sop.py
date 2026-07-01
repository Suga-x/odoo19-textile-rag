import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Inisialisasi Client ChromaDB Lokal Anda
# (Sesuaikan path direktori jika Anda menggunakan persistent storage berbeda)
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Buat atau ambil koleksi yang sudah ada
collection = chroma_client.get_or_create_collection(name="textile_sop")

# 2. Data Master SOP Mentah beserta Metadatanya
raw_documents = [
    {
        "text": "SOP-03: Untuk mencegah kain polyester mengalami penyusutan (shrinkage) berlebih di atas 2%, operator wajib mengatur suhu oven mesin stenter pada rentang 180°C hingga 190°C. Durasi penarikan kain di dalam oven diatur stabil antara 30 sampai 45 detik saja.",
        "metadata": {"sop_code": "SOP-03", "division": "Finishing", "topic": "Stenter"}
    },
    {
        "text": "SOP-09: Jika kerusakan kain greige makloon akibat mesin jet dyeing meledak atau macet melebihi 10 persen dari total volume order, pabrik makloon wajib memberikan kompensasi ganti rugi senilai harga kain greige mentah yang rusak kepada pelanggan.",
        "metadata": {"sop_code": "SOP-09", "division": "Dyeing", "topic": "Compensation"}
    }
]

# 3. Konfigurasi Splitter Cerdas LangChain
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=250,      # Ukuran dibuat lebih padat agar pas per pasal
    chunk_overlap=40,     # Jembatan antar chunk
)

# 4. Proses Eksekusi Pemotongan dan Pengemasan Data
final_documents = []
final_metadatas = []
final_ids = []

for index, doc in enumerate(raw_documents):
    # Potong teks mentah menjadi bagian-bagian kecil
    chunks = text_splitter.split_text(doc["text"])
    
    for chunk_index, chunk_text in enumerate(chunks):
        final_documents.append(chunk_text)
        
        # Tempelkan metadata asli ke setiap potongan chunk
        final_metadatas.append(doc["metadata"])
        
        # Buat ID unik penanda chunk (Contoh: SOP-03_chunk_0)
        sop_code = doc["metadata"]["sop_code"]
        final_ids.append(f"{sop_code}_chunk_{chunk_index}")

# 5. Suntikkan Data Bersih ke dalam ChromaDB
collection.upsert(
    ids=final_ids,
    documents=final_documents,
    metadatas=final_metadatas
)

print("🚀 DATA INGESTION BERHASIL!")
print(f"Berhasil memproses dan menyimpan {len(final_ids)} chunk cerdas ke ChromaDB.")
for idx, cid in enumerate(final_ids):
    print(f" -> Terbentuk ID: {cid} | Divisi: {final_metadatas[idx]['division']}")