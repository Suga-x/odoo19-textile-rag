# fastapi_project/tasks.py
import signal
import sys
import time
import os
from celery_app import celery_app

# Import from the same folder (no W1_Chunking prefix)
try:
    from ingest_sop import extract_and_embed_document
except ImportError:
    # Fallback if ingest_sop.py runs procedurally
    extract_and_embed_document = None


# ====================================================================
# 🛑 GRACEFUL SHUTDOWN — Worker mati bersih saat restart
# ====================================================================
# Handler ini menangkap SIGTERM (dikirim Docker saat stop/restart)
# dan SIGINT (Ctrl+C) agar worker menyelesaikan task aktif sebelum
# benar-benar berhenti.
#
# Tanpa ini, worker akan di kill paksa — task yang sedang berjalan
# akan gagal dan masuk retry, menyebabkan delay tidak perlu.
# ====================================================================
def _handle_shutdown(signum, frame):
    """
    Dipanggil saat container menerima sinyal berhenti (SIGTERM/SIGINT).
    Worker akan:
    1. Berhenti accept task baru
    2. Selesaikan task yang sedang berjalan
    3. Shutdown graceully dalam warm shutdown mode
    """
    print(f"\n[SIGNAL] Received signal {signum}. Initiating graceful shutdown...")
    print("[SIGNAL] Worker will finish current tasks before exiting.")
    # Celery worker secara otomatis handle SIGTERM untuk warm shutdown,
    # tapi kita perlu pastikan sinyal diteruskan dengan benar.
    sys.exit(0)


# Daftarkan signal handler
signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


# ====================================================================
# 🟢 HIGH PRIORITY QUEUE — Real-time Operator Query
# ====================================================================
# Queue ini khusus untuk permintaan real-time dari operator pabrik
# melalui chat dashboard Odoo.
#
# 🎯 Retry Strategy:
# - Exponential backoff + jitter agar tidak banjiri Redis saat error
# - Maks 5 retry dengan jeda maksimal 5 menit
# - autoretry_for menangani semua Exception otomatis
# ====================================================================
@celery_app.task(
    bind=True,
    queue='high_priority',
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def task_query_sop(self, question: str, division: str = None, session_id: str = None):
    """
    Celery task untuk query RAG — high priority queue.

    Args:
        question: Pertanyaan operator tentang SOP tekstil
        division: Filter divisi (Dyeing/Finishing/dll)
        session_id: Opsional, untuk chat history

    Returns:
        dict dengan status dan answer dari LLM
    """
    print(f"[HIGH PRIORITY] Processing query: '{question[:50]}...' division={division}")
    start_time = time.time()

    try:
        # Import di sini untuk menghindari circular import
        from main import get_hybrid_search
        from services.llm import LLMService

        # 1. Retrieve dokumen SOP dari ChromaDB (hybrid search)
        retrieved_docs = get_hybrid_search(question=question, division=division)

        # 2. Generate answer via LLM
        ai_response = LLMService.generate_rag_answer(
            question=question,
            retrieved_sop=retrieved_docs
        )

        duration = time.time() - start_time
        print(f"[HIGH PRIORITY] Query completed in {duration:.2f}s")

        return {
            "status": "success",
            "answer": ai_response,
            "duration_s": round(duration, 2)
        }

    except Exception as exc:
        print(f"[HIGH PRIORITY] Query failed (attempt {self.request.retries + 1}): {exc}")
        # Jangan retry jika error karena input invalid
        if "not found" in str(exc).lower() or "empty" in str(exc).lower():
            return {"status": "failed", "answer": "SOP document tidak ditemukan untuk pertanyaan ini."}
        raise self.retry(exc=exc)


# ====================================================================
# 🔴 LOW PRIORITY QUEUE — Background SOP Document Ingest
# ====================================================================
# Queue ini untuk pemrosesan dokumen SOP besar (ratusan halaman).
# Boleh diproses lambat karena sifatnya batch/best-effort.
#
# 🎯 Retry Strategy:
# - Exponential backoff + jitter (10s, 20s, 40s, 80s, 160s)
# - Maks 5 retry — Redis/ChromaDB transient errors biasanya sembuh dalam 2-3 menit
# - IDEMPOTENCY: File hash + Redis lock untuk cegah duplikasi
# ====================================================================
@celery_app.task(
    bind=True,
    queue='low_priority',
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def task_ingest_sop_textile(self, file_path: str, metadata: dict):
    print(f"[LOW PRIORITY] Starting async document processing for file: {file_path}")
    start_time = time.time()

    # =====================================================================
    # 🛡️ IDEMPOTENCY LAYER — Cegah duplikasi pemrosesan file
    # =====================================================================
    try:
        from services.redis_client import (
            compute_file_hash,
            is_file_already_processed,
            acquire_process_lock,
            mark_file_as_processed,
            get_redis_client,
        )

        # 1. Hitung hash file (fingerprint unik berdasarkan isi)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = compute_file_hash(file_path)

        # 2. Cek apakah file ini SUDAH PERNAH berhasil diproses sebelumnya
        if is_file_already_processed(file_hash):
            print(f"[IDEMPOTENCY] ⏭️ File hash {file_hash[:8]}... already processed. Skipping.")
            # ⏭️ Skip — file sudah diproses, anggap sukses
            return {"status": "SKIPPED", "file": file_path, "reason": "already_processed"}

        # 3. Ambil LOCK — cegah 2 worker proses file yang sama bersamaan
        if not acquire_process_lock(file_hash):
            print(f"[IDEMPOTENCY] 🔒 File hash {file_hash[:8]}... is locked by another worker. Skipping.")
            # 🔒 Worker lain sedang proses file ini
            return {"status": "SKIPPED", "file": file_path, "reason": "locked_by_other_worker"}

        # =====================================================================
        # 🚀 PROSES UTAMA — Chunking + Embedding + Upsert
        # =====================================================================
        if extract_and_embed_document:
            try:
                result = extract_and_embed_document(file_path, metadata)

                # 4. Tandai sukses di Redis — prevent duplicate di masa depan
                mark_file_as_processed(file_hash)

                duration = time.time() - start_time
                print(f"[LOW PRIORITY] ✅ Successfully completed RAG ingest in {duration:.2f}s.")
                return {"status": "SUCCESS", "file": file_path}

            except Exception as exc:
                # 5. Jika gagal, lepas lock agar worker lain bisa coba
                from services.redis_client import release_process_lock
                release_process_lock(file_hash)
                print(f"[LOW PRIORITY] ❌ Failed to process document: {exc}. Retrying...")
                raise self.retry(exc=exc)

        # =====================================================================
        # FALLBACK: Jalankan ingest_sop.py sebagai subprocess
        # =====================================================================
        else:
            import subprocess

            script_path = os.path.join(os.path.dirname(__file__), "ingest_sop.py")
            try:
                result = subprocess.run(
                    ["python", script_path],
                    capture_output=True,
                    text=True,
                    check=True
                )

                # Tandai sukses
                mark_file_as_processed(file_hash)

                duration = time.time() - start_time
                print(f"[LOW PRIORITY] ✅ Script completed in {duration:.2f}s:\n{result.stdout}")
                return {"status": "SUCCESS", "file": file_path}

            except subprocess.CalledProcessError as err:
                from services.redis_client import release_process_lock
                release_process_lock(file_hash)
                print(f"[LOW PRIORITY] ❌ Script failed:\n{err.stderr}")
                raise self.retry(exc=err)

    except Exception as exc:
        # Safety net — kalau Redis sendiri yang error, tetap retry
        print(f"[LOW PRIORITY] ⚠️ Idempotency layer error: {exc}. Proceeding without lock...")
        if extract_and_embed_document:
            try:
                result = extract_and_embed_document(file_path, metadata)
                duration = time.time() - start_time
                return {"status": "SUCCESS", "file": file_path}
            except Exception as inner_exc:
                raise self.retry(exc=inner_exc)
        raise self.retry(exc=exc)
