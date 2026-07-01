from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Simulasi teks SOP Pabrik Makloon Celup Anda
sop_text = """
SOP-03: PENGATURAN SUHU MESIN STENTER (PRE-SETTING KAIN POLYESTER)
Untuk mencegah kain polyester mengalami penyusutan (shrinkage) berlebih di atas 2%, operator wajib mengatur suhu oven mesin stenter pada rentang 180°C hingga 190°C. Durasi penarikan kain di dalam oven diatur stabil antara 30 sampai 45 detik saja.

SOP-09: KEBIJAKAN GANTI RUGI KERUSAKAN KAIN PELANGGAN
Jika kerusakan kain greige makloon akibat mesin jet dyeing meledak atau macet melebihi 10 persen dari total volume order, pabrik makloon wajib memberikan kompensasi ganti rugi senilai harga kain greige mentah yang rusak kepada pelanggan. Manajemen tidak bertanggung jawab atas kerugian jika disebabkan oleh kelalaian pihak ketiga.
"""

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,      # Target panjang karakter per chunk
    chunk_overlap=50,    # Irisan konteks antar chunk tetangga
    length_function=len,
)

# 3. Eksekusi Pemotongan Teks
chunks = text_splitter.create_documents([sop_text])

# 4. Tampilkan Hasil Cetakan di Terminal
print(f"Total chunk yang dihasilkan: {len(chunks)}\n")
for i, chunk in enumerate(chunks):
    print(f"--- CHUNK ke-{i+1} (Panjang: {len(chunk.page_content)} karakter) ---")
    print(chunk.page_content)
    print("-" * 40, "\n")