import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

# 1. Tentukan path sesuai dengan env atau default main.py Anda
CHROMA_DATA_PATH = os.getenv("CHROMA_DATA_PATH", "./chroma_db")
print(f"🔍 Memeriksa lokasi database di: {os.path.abspath(CHROMA_DATA_PATH)}")

try:
    # 2. Hubungkan ke persistent client
    chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
    
    # 3. Cek daftar koleksi yang ada di dalam database
    collections = chroma_client.list_collections()
    print(f"📦 Jumlah koleksi yang ditemukan: {len(collections)}")
    
    for col in collections:
        print(f"\n--- Koleksi: {col.name} ---")
        
        # Ambil sampel data untuk melihat strukturnya
        collection = chroma_client.get_collection(name=col.name)
        total_docs = collection.count()
        print(f"📄 Total dokumen di dalam koleksi: {total_docs}")
        
        if total_docs > 0:
            # Ambil 1 contoh dokumen untuk inspeksi metadata
            sample = collection.get(limit=1)
            print("🔬 Struktur Metadata Sampel:")
            print(sample.get("metadatas", [{}])[0])
            print("📝 Potongan Teks Dokumen Sampel:")
            print(sample.get("documents", [""])[0][:150] + "...")
        else:
            print("⚠️ Koleksi ini masih kosong. Belum ada data masuk dari Odoo.")

except Exception as e:
    print(f"🚨 Gagal membaca konfigurasi ChromaDB: {str(e)}")