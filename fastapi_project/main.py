import os
import chromadb
from fastapi import FastAPI, UploadFile, File, Form, status, HTTPException
from fastapi.responses import RedirectResponse
from config import settings
from schemas import QueryRequest, QueryResponse
from services.embedding import EmbeddingService
from services.llm import LLMService
from pydantic import BaseModel
from typing import Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi



# Inisialisasi Database Sekali Saat Aplikasi Start
chroma_client = chromadb.PersistentClient(path=settings.DB_PATH)
# collection = chroma_client.get_collection(name=settings.COLLECTION_NAME)
collection = chroma_client.get_or_create_collection(name=settings.COLLECTION_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Sistem RAG Tekstil 100% Lokal Berbasis Clean Architecture"
)

chat_sessions: Dict[str, list[Dict[str, str]]] = {}
class QueryRequest(BaseModel):
    question: str
    division: str | None = None 
    session_id: str | None = None 


def get_hybrid_search(question: str, division: Optional[str] = None) -> str:
    """
    Mengambil korpus secara dinamis dari ChromaDB untuk BM25, 
    lalu digabungkan dengan Vector Search.
    """
    try:
        filter_metadata = {"division": division} if division else {}
        
        # 1. Ambil dokumen dari ChromaDB secara dinamis
        all_docs = collection.get(where=filter_metadata)
        
        corpus_texts = all_docs.get('documents', [])
        metadatas = all_docs.get('metadatas', [])

        # 🔥 PERBAIKAN UTAMA: Hitung embedding query terlebih dahulu agar dimensinya konsisten (768)
        query_embedding = EmbeddingService.get_embedding(question)

        # Antisipasi jika database ChromaDB masih kosong
        if not corpus_texts:
            print(" ⚠️ [HYBRID] Korpus ChromaDB kosong. Mengandalkan Vector Search utama saja.")
            # 🔥 PERBAIKAN: Gunakan query_embeddings=[query_embedding], bukan query_texts
            vector_results = collection.query(query_embeddings=[query_embedding], n_results=1)
            return vector_results['documents'][0][0] if vector_results['documents'] else "SOP tidak ditemukan."

        # 2. INISIALISASI BM25 SECARA LIVE BERDASARKAN ISI DB
        tokenized_corpus = [doc.lower().split(" ") for doc in corpus_texts]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # 3. JALANKAN KEYWORD SEARCH (BM25)
        tokenized_query = question.lower().split(" ")
        bm25_best_docs = bm25.get_top_n(tokenized_query, corpus_texts, n=1)
        keyword_result = bm25_best_docs[0] if bm25_best_docs else ""

        # 4. JALANKAN VECTOR SEARCH (CHROMADB)
        # 🔥 PERBAIKAN: Gunakan query_embeddings=[query_embedding] untuk menghindari error Dimension Mismatch (384 vs 768)
        vector_results = collection.query(
            query_embeddings=[query_embedding], 
            n_results=1, 
            where=filter_metadata
        )
        vector_result = vector_results['documents'][0][0] if vector_results['documents'] else ""

        # 5. STRATEGI RERANKING / PENGGABUNGAN SOLUSI
        has_exact_code = False
        if metadatas:
            for meta in metadatas:
                doc_code = meta.get("sop_code", "")
                if doc_code and doc_code.upper() in question.upper():
                    has_exact_code = True
                    break

        if has_exact_code and keyword_result:
            print(" 🎯 [RETRIEVER] Jalur BM25: Berhasil mengunci kode kata kunci eksak.")
            return keyword_result
        
        print(" 🌐 [RETRIEVER] Jalur Vektor: Menggunakan kedekatan makna semantik ChromaDB.")
        return vector_result if vector_result else keyword_result

    except Exception as e:
        print(f" 🚨 [HYBRID ERROR] Gagal melakukan hybrid search: {str(e)}")
        return "Gagal memproses pencarian dokumen SOP."

        
@app.post("/api/query/history",tags=["Core RAG Engine"])
async def query_rag_engine_history(payload: QueryRequest):
    question = payload.question
    session_id = payload.session_id
    division = payload.division

    # 1. Ambil atau buat history baru khusus session_id ini
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    current_history = chat_sessions[session_id]
    
    # 2. Cari dokumen SOP dari ChromaDB (Simulasi data yang Anda temukan)
    retrieved_docs = get_hybrid_search(question=question, division=division)

    # 3. Panggil service dinamis LiteLLM dengan melemparkan riwayat chatnya
    ai_response = LLMService.generate_rag_answer_history(
        question=question, 
        retrieved_sop=retrieved_docs, 
        history=current_history
    )

    # 4. SIMPAN PERCAKAPAN BARU KE DALAM HISTORY SESI
    chat_sessions[session_id].append({"role": "Operator", "content": question})
    chat_sessions[session_id].append({"role": "AI", "content": ai_response})

    return {
        "status": "success",
        "answer": ai_response
    }

@app.get("/api/sops", status_code=status.HTTP_200_OK, tags=["Administrative Engine"])
async def get_registered_sops_list():
    try:
        # 1. Ambil seluruh metadata dan dokumen dari collection ChromaDB
        # include=["metadatas", "documents"] diperlukan untuk mengambil konten SOP
        db_content = collection.get(include=["metadatas", "documents"])
        all_metadatas = db_content.get("metadatas", [])
        all_documents = db_content.get("documents", [])
        
        if not all_metadatas:
            return {
                "status": "success",
                "message": "Belum ada dokumen SOP yang terdaftar di dalam sistem.",
                "total_sops": 0,
                "sops": []
            }
        
        # 2. Lakukan eliminasi duplikat menggunakan dictionary Python
        # Karena satu SOP bisa terpecah menjadi banyak chunk, kita kelompokkan berdasarkan kode SOP unik
        # sambil menggabungkan konten dari seluruh chunk milik SOP yang sama
        unique_sops = {}
        for i, meta in enumerate(all_metadatas):
            if meta and "sop_code" in meta:
                code = meta["sop_code"]
                doc_text = all_documents[i] if i < len(all_documents) else ""
                
                if code not in unique_sops:
                    unique_sops[code] = {
                        "sop_code": code,
                        "division": meta.get("division", "TIDAK DIKETAHUI"),
                        "content": ""
                    }
                
                # Gabungkan konten dari semua chunk milik SOP yang sama
                if doc_text:
                    unique_sops[code]["content"] += doc_text.strip() + "\n\n"
        
        # 3. Bersihkan trailing newline pada konten
        for sop in unique_sops.values():
            sop["content"] = sop["content"].strip()
        
        # 4. Ubah format menjadi list array JSON bersih
        sops_list = list(unique_sops.values())
        
        return {
            "status": "success",
            "total_sops": len(sops_list),
            "sops": sops_list
        }
        
    except Exception as e:
        print(f" [ERROR] Gagal menarik list SOP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengambil daftar SOP dari database: {str(e)}"
        )

@app.post("/api/query/guards", status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def query_rag_system_guards(request: QueryRequest):
    try:
        # LAPIS 1: PRE-FILTER GUARDRAIL (Pembersihan Input)
        clean_question = request.question.strip()
        
        # Batasi panjang karakter untuk mencegah serangan overload teks (max 300 karakter)
        if len(clean_question) > 300:
            return {
                "status": "rejected",
                "answer": "<b>Peringatan Sistem:</b> Pertanyaan terlalu panjang (Maksimal 300 karakter). Mohon persingkat pertanyaan Anda.",
                "chunks_used": 0
            }
            
        # Tolong cegah karakter regex/simbol aneh yang tidak perlu
        karakter_terlarang = ["#", "DROP TABLE", "SELECT", "INSERT", "DELETE", "html", "<script>"]
        if any(keyword in clean_question.upper() for keyword in karakter_terlarang):
            return {
                "status": "rejected",
                "answer": "<b>Peringatan Sistem:</b> Pertanyaan Anda terdeteksi mengandung simbol atau instruksi database terlarang.",
                "chunks_used": 0
            }

        # LAPIS 2: PROSES DATABASE (CHROMADB) DENGAN SAFE-GUARD
        try:
            query_embedding = EmbeddingService.get_embedding(clean_question)
        except Exception as embed_err:
            print(f" Gagal menghitung embedding query: {str(embed_err)}")
            raise HTTPException(status_code=500, detail="Gagal mengenali maksud pertanyaan.")

        search_filter = {}
        if request.division:
            search_filter = {"division": request.division}
            
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            where=search_filter
        )
        
        retrieved_documents = results.get("documents", [[]])[0]
        retrieved_metadatas = results.get("metadatas", [[]])[0]
        retrieved_distances = results.get("distances", [[]])[0]

        # LAPIS 3: DISTANCE THRESHOLD GUARDRAIL (Uji Relevansi)
        # Jika jarak vektor di atas 1.2, berarti database tidak punya data SOP yang cocok
        if not retrieved_documents or (len(retrieved_distances) > 0 and retrieved_distances[0] > 1.2):
            return {
                "status": "out_of_scope",
                "answer": "<b>Sistem AI Pabrik:</b> Maaf, informasi mengenai hal tersebut tidak diatur di dalam dokumen SOP resmi divisi Anda saat ini.",
                "chunks_used": 0
            }
        
        # LANGKAH CONTEXT STRUCTURING XML (Jalan jika lolos semua guardrail)
        context_blocks = []
        for index, (doc_text, metadata) in enumerate(zip(retrieved_documents, retrieved_metadatas)):
            sop_code = metadata.get("sop_code", "TIDAK DIKETAHUI")
            division = metadata.get("division", "TIDAK DIKETAHUI")
            
            block = (
                f"<Dokumen_SOP_Referensi index='{index+1}'>\n"
                f"  <Kode_SOP>{sop_code}</Kode_SOP>\n"
                f"  <Divisi_Terkait>{division}</Divisi_Terkait>\n"
                f"  <Isi_Instruksi_Kerja>\n{doc_text}\n  </Isi_Instruksi_Kerja>\n"
                f"</Dokumen_SOP_Referensi>"
            )
            context_blocks.append(block)
        
        context_sop = "\n\n".join(context_blocks)
            
        # EXECUTE GENERATION (Dengan proteksi internal LLMService)
        ai_response_html = LLMService.generate_rag_answer(
            question=clean_question,
            retrieved_sop=context_sop
        )
        
        # Bersihkan sisa karakter baris baru agar HTML solid rapat
        ai_response_html = ai_response_html.replace("\n", "").strip()
        
        return {
            "status": "success",
            "answer": ai_response_html,
            "chunks_used": len(retrieved_documents)
        }
        
    except Exception as fatal_err:
        # Pagar Pengaman Terakhir: Jika ada skenario aneh yang lolos, sistem tidak boleh melempar HTTP 500 ke Odoo
        print(f" CRITICAL ERROR ON QUERY: {str(fatal_err)}")
        return {
            "status": "system_error",
            "answer": "<b>Kesalahan Sistem Internal:</b> Terjadi kendala saat memproses jawaban. Mohon ulangi beberapa saat lagi atau hubungi IT.",
            "chunks_used": 0
        }

@app.post("/api/query/ask", response_model=QueryResponse, status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def tanya_sop(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong.")
    
    try:
        # 1. Ambil Representasi Vektor dari Pertanyaan (Konsisten dengan EmbeddingService)
        vektor_query = EmbeddingService.get_embedding(request.question)
        
        # 2. Lakukan Retrieval ke ChromaDB
        hasil = collection.query(query_embeddings=[vektor_query], n_results=1)
        
        if not hasil['documents'] or not hasil['documents'][0]:
            raise HTTPException(status_code=404, detail="SOP Tekstil relevan tidak ditemukan.")
            
        terbaik_dokumen = hasil['documents'][0][0]
        jarak_vektor = hasil['distances'][0][0]
        THRESHOLD_LIMIT = 260.0
        
        if jarak_vektor > THRESHOLD_LIMIT:
            return QueryResponse(
                question=request.question,
                retrieved_sop="DOKUMEN DIBAWAH AMBANG BATAS AMAN",
                vector_distance=jarak_vektor,
                ai_answer="Maaf, pertanyaan Anda tidak dapat dijawab karena topiknya berada di luar jangkauan Dokumen SOP Resmi Pabrik saat ini."
            )
        
        # 4. Jika lolos Guard, kirim ke LLM Service untuk Sintesis Jawaban
        ai_answer = LLMService.generate_rag_answer(request.question, terbaik_dokumen)
        
        return QueryResponse(
            question=request.question,
            retrieved_sop=terbaik_dokumen,
            vector_distance=jarak_vektor,
            ai_answer=ai_answer
        )
        
    except RuntimeError as error_layanan:
        raise HTTPException(status_code=502, detail=str(error_layanan))
    except Exception as general_error:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(general_error)}")

@app.post("/api/query", status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def query_rag_system(request: QueryRequest):
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong.")
        
        # 1. Hitung embedding dari pertanyaan operator
        query_embedding = EmbeddingService.get_embedding(request.question)
        
        # 2. Filter opsional berdasarkan divisi operator
        search_filter = {}
        if request.division:
            search_filter = {"division": request.division}
            
        # 3. Ambil 3 chunk terdekat dari ChromaDB beserta metadatanya
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            where=search_filter
        )
        
        retrieved_documents = results.get("documents", [[]])[0]
        retrieved_metadatas = results.get("metadatas", [[]])[0] # <-- Ambil metadata bawaan
        
        # 4. TEKNIK CONTEXT STRUCTURING (Mengubah menjadi format XML Terstruktur)
        context_blocks = []
        
        if not retrieved_documents:
            context_sop = "PERINGATAN: Tidak ada dokumen SOP resmi yang ditemukan di database untuk pertanyaan ini."
        else:
            for index, (doc_text, metadata) in enumerate(zip(retrieved_documents, retrieved_metadatas)):
                sop_code = metadata.get("sop_code", "TIDAK DIKETAHUI")
                division = metadata.get("division", "TIDAK DIKETAHUI")
                
                # Bungkus teks dengan tag terstruktur agar dipahami LLM dengan instan
                block = (
                    f"<Dokumen_SOP_Referensi index='{index+1}'>\n"
                    f"  <Kode_SOP>{sop_code}</Kode_SOP>\n"
                    f"  <Divisi_Terkait>{division}</Divisi_Terkait>\n"
                    f"  <Isi_Instruksi_Kerja>\n{doc_text}\n  </Isi_Instruksi_Kerja>\n"
                    f"</Dokumen_SOP_Referensi>"
                )
                context_blocks.append(block)
            
            # Gabungkan semua blok menjadi satu string besar
            context_sop = "\n\n".join(context_blocks)
            
        # 5. Kirim konteks terstruktur ini ke LLM Service
        ai_response_html = LLMService.generate_rag_answer(
            question=request.question,
            retrieved_sop=context_sop
        )
        
        return {
            "status": "success",
            "question": request.question,
            "answer": ai_response_html,
            "chunks_used": len(retrieved_documents)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses RAG: {str(e)}")

@app.get("/api/health", tags=["System Utility"])
async def health_check():
    return {"status": "healthy"}

@app.post("/api/ingest", status_code=status.HTTP_201_CREATED,tags=["Core RAG Engine"])
async def ingest_document_file(sop_code: str = Form(...),division: str = Form(...),file: UploadFile = File(...)):
    try:
        # 1. Baca konten file yang diunggah
        file_content = await file.read()
        
        # 2. Ekstrak teks (Contoh ini untuk file .txt bersih)
        # Jika nanti ingin mendukung PDF, gunakan library 'pypdf' di bagian ini
        raw_text = file_content.decode("utf-8")
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            add_start_index=True,
        )
        # 3. Jalankan Chunking Cerdas LangChain (Sesuai materi Minggu 1)
        chunks = text_splitter.split_text(raw_text)
        
        if not chunks:
            raise HTTPException(status_code=400, detail="File kosong atau tidak dapat diekstrak.")
            
        final_documents = []
        final_metadatas = []
        final_ids = []
        
        # 4. Ambil Embedding Service Anda untuk memproses per chunk
        for chunk_index, chunk_text in enumerate(chunks):
            final_documents.append(chunk_text)
            final_metadatas.append({
                "sop_code": sop_code,
                "division": division
            })
            final_ids.append(f"{sop_code}_chunk_{chunk_index}")
        final_embeddings = [EmbeddingService.get_embedding(text) for text in final_documents]
            
        # 5. Suntikkan langsung ke ChromaDB secara real-time
        collection.upsert(
            ids=final_ids,
            documents=final_documents,
            metadatas=final_metadatas,
            embeddings=final_embeddings
        )
        
        return {
            "status": "success",
            "message": f"Berhasil memproses SOP {sop_code}. {len(final_ids)} chunk baru disimpan."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses file: {str(e)}")

@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/docs")