# 📚 Laporan Progress Belajar — Enterprise Scalability

> **Nama:** Agus Rian Sirojudin  
> **Proyek:** High-Performance AI Backend (FastAPI RAG) & Odoo 19 ERP Enterprise Scalability  
> **Lokasi Device Asal:** `/Users/rian/Docker/Odoo19CE`  
> **Tanggal Laporan:** 13 Juli 2026  
> **Progress Keseluruhan:** ~35% (Modul 1 selesai, Modul 2 Phase 1 selesai)

---

## 📋 Daftar Isi

1. [Ringkasan Arsitektur](#ringkasan-arsitektur)
2. [Progress Detail Per Modul](#progress-detail-per-modul)
3. [File & Kode Penting](#file--kode-penting)
4. [Resume Prompt untuk AI Agent](#resume-prompt-untuk-ai-agent)
5. [Docker Services](#docker-services)
6. [API Endpoints](#api-endpoints)
7. [Catatan Teknis](#catatan-teknis)

---

## Ringkasan Arsitektur

Proyek ini mengintegrasikan **FastAPI RAG Engine + Odoo 19 ERP** untuk membantu operator pabrik tekstil mencari SOP (Standard Operating Procedure) melalui chat dashboard berbasis AI.

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Odoo 19 CE  │────▶│  FastAPI RAG     │────▶│  Qdrant (VDB)   │
│  :8019       │     │  :8000           │     │  :6333          │
│  textile_rag │     │  Hybrid Search   │     │  (Production)   │
│  mrp_ai_...  │     │  (Vector + BM25) │     │                 │
└──────────────┘     └────────┬─────────┘     └─────────────────┘
                              │
                     ┌────────▼─────────┐
                     │  Redis (Broker)  │
                     │  :6379           │
                     └────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐ ┌─────▼────────┐ ┌────▼────────┐
     │ Celery HIGH   │ │ Celery LOW   │ │ Flower      │
     │ Query RAG     │ │ SOP Ingest   │ │ Monitoring  │
     │ concurrency=4 │ │ concurrency=1│ │ :5555       │
     │ time-limit=180│ │ time-limit=600│ │ admin/...   │
     └───────────────┘ └──────────────┘ └─────────────┘
```

**Vector Database Architecture:**

```
┌──────────────────────────────────────────────────────────┐
│                    Factory Pattern                        │
│                    (store_factory.py)                     │
│                                                          │
│  VECTOR_DB_PROVIDER="qdrant"  ─── QdrantStore  (primary) │
│  VECTOR_DB_PROVIDER="chroma"  ─── ChromaStore (legacy)   │
│  VECTOR_DB_PROVIDER="dual"    ─── DualStore   (both)     │
└──────────────────────────────────────────────────────────┘
```

---

## Progress Detail Per Modul

### ✅ Modul 1.1 — Foundation & Core Integration (100% Selesai)

| # | Topik | Detail Implementasi | Status |
|---|-------|---------------------|--------|
| 1 | **FastAPI Setup** | App dengan ChromaDB persistent client, CORS, upload directory | ✅ |
| 2 | **ChromaDB Vector Store** | Single-node persistent, collection `sop_textile_collection` | ✅ |
| 3 | **Embedding Service** | `fastapi_project/services/embedding.py` — OLLaMA `nomic-embed-text` | ✅ |
| 4 | **Hybrid Search** | Vector similarity + BM25 keyword fusion (weighted 0.7/0.3) | ✅ |
| 5 | **LLM Service** | `fastapi_project/services/llm.py` — Support Ollama & Gemini, 3 method (RAG, history, context list) | ✅ |
| 6 | **SOP Ingestion Pipeline** | `fastapi_project/ingest_sop.py` — RecursiveCharacterTextSplitter, semantic chunking, metadata | ✅ |
| 7 | **Odoo Bridge** | `addons/textile_rag/controllers/controllers.py` — JSON endpoint, chat session management | ✅ |
| 8 | **V1 API** | Endpoint `/api/v1/ingest`, `/api/v1/query`, `/api/v1/query/async`, `/api/v1/task/{id}` | ✅ |
| 9 | **Docker Compose** | 8 services: Odoo, PostgreSQL, FastAPI, Redis, Ollama, 2x Celery Worker, Flower | ✅ |
| 10| **Odoo Widget Chat** | `addons/textile_rag/static/src/components/chat_dashboard.js` | ✅ |

### ✅ Modul 1.2 — Resiliency, Monitoring & Error Handling (100% Selesai)

| # | Tahap | Topik | Detail Implementasi | Status |
|---|-------|-------|---------------------|--------|
| 1 | **Tahap 1** | Advanced Task Routing | Priority queue `high_priority` (query) & `low_priority` (ingest) via kombu Queue | ✅ |
| 2 | **Tahap 1** | Worker Separation | 2 container: `celery_worker_high` (conc=4, max-tasks=100) & `celery_worker_low` (conc=1, max-tasks=10) | ✅ |
| 3 | **Tahap 2** | Exponential Backoff | `retry_backoff=True`, `retry_backoff_max=300/600`, `retry_jitter=True`, `max_retries=5` | ✅ |
| 4 | **Tahap 2** | Idempotency | MD5 file hash → Redis SETNX lock → `is_file_already_processed` check → skip duplicate | ✅ |
| 5 | **Tahap 2** | Redis Lock | `fastapi_project/services/redis_client.py` — acquire/release lock, 1h TTL, 7d processed key | ✅ |
| 6 | **Tahap 2** | Safety Net | Fallback proceed without lock jika Redis down | ✅ |
| 7 | **Tahap 3** | Flower Dashboard | docker-compose.yaml flower service, port 5555, auth `admin/s3cur3P@ss`, persistent DB | ✅ |
| 8 | **Tahap 3** | Time Limits | `--time-limit=180/600`, `--soft-time-limit=150/540`, `--events` flag | ✅ |
| 9 | **Tahap 3** | Event Tracking | `worker_send_task_events=True`, `task_send_sent_event=True`, `task_track_started=True` | ✅ |
| 10 | **Tahap 3** | Graceful Shutdown | SIGTERM/SIGINT handler, warm shutdown (task selesai dulu baru mati) | ✅ |

### ✅ Modul 2.1 — Migrasi ChromaDB → Qdrant (Phase 1 — 100% Selesai)

| # | Topik | Detail Implementasi | Status |
|---|-------|---------------------|--------|
| 1 | **Abstract Vector Store Interface** | `services/vector_store.py` — ABC dengan 7 abstract method (upsert, query, get_all, delete, count, health_check, delete_collection) | ✅ |
| 2 | **QdrantStore Implementation** | `services/qdrant_store.py` — Full implementation dengan HNSW config (m=32, ef_construct=200), scalar quantization INT8, payload indexing (division, sop_code, doc_id, file_hash), Scroll API pagination, deterministic UUID v5 | ✅ |
| 3 | **ChromaStore (Legacy)** | `services/chroma_store.py` — Backward compatibility, fallback jika Qdrant down, dual-write support | ✅ |
| 4 | **Factory Pattern** | `services/store_factory.py` — Pilih provider via env `VECTOR_DB_PROVIDER` (qdrant/chroma/dual), `health_check_vector_store()` helper | ✅ |
| 5 | **DualStore Dual-Write** | `services/dual_store.py` — Phase 1 migration: write ke Qdrant + ChromaDB paralel, read dari primary, fallback ke secondary | ✅ |
| 6 | **Config Update** | `config.py` — Tambah `VECTOR_DB_PROVIDER`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION`, dll | ✅ |
| 7 | **Docker Qdrant Service** | `docker-compose.yaml` — Tambah service qdrant (image: qdrant/qdrant:v1.9.0, port 6333/6334, volume qdrant_storage), env vars, depends_on | ✅ |
| 8 | **main.py Update** | Ganti semua `chromadb` langsung dengan `vector_store = get_vector_store()` via factory | ✅ |
| 9 | **ingest_sop.py Update** | Ganti ChromaDB dengan factory + precomputed embeddings untuk Qdrant | ✅ |
| 10 | **Migration Script** | `scripts/migrate_chroma_to_qdrant.py` — Batch migration (50 docs/batch), compute embeddings via Ollama, verify count, support --force/--verify/--dry-run/--batch | ✅ |
| 11 | **Dependencies** | `requirements.txt` & `Dockerfile` — Tambah `qdrant-client==1.9.0` | ✅ |

### ⏳ Modul 2.2 — Advanced RAG Pipeline & Query Optimization (0% — Belum Dimulai)

Topik yang akan dipelajari:
1. **Multi-Query Retrieval** — generate multiple query variations untuk improve recall
2. **Reranking Pipeline** — cross-encoder reranker (Cohere / BGE) untuk refine hasil
3. **HyDE (Hypothetical Document Embeddings)** — improve zero-shot retrieval
4. **Parent-Child Recursive Retrieval** — chunk optimization untuk konteks lebih besar
5. **Qdrant Filter Optimization** — leveraging payload index untuk fast filtering

### ⏳ Modul 3 — Database & ORM Optimization (0% — Belum Dimulai)

Topik yang akan dipelajari:
1. **PostgreSQL Performance Tuning** — indexing strategy, connection pooling (PgBouncer)
2. **Odoo ORM Optimization** — prefetching, selective field loading, `_auto_join`
3. **Read Replicas** — PostgreSQL streaming replication, Odoo multi-DB routing
4. **Slow Query Logging & Analysis** — pg_stat_statements, auto_explain

### ⏳ Modul 4 — Production-Grade Load Testing, Monitoring & ROI (0% — Belum Dimulai)

Topik yang akan dipelajari:
1. **Locust / k6 Load Testing** — simulate 500+ concurrent users
2. **Prometheus + Grafana** — infrastructure monitoring stack
3. **Distributed Tracing** — OpenTelemetry, Jaeger
4. **ROI Analysis** — cost per query, throughput benchmarking, scalability projection

---

## File & Kode Penting

### Core Backend

| File | Path | Fungsi |
|------|------|--------|
| Main App | `fastapi_project/main.py` | FastAPI app, 12+ endpoints, Hybrid Search logic, VectorStore integration |
| Ingestion | `fastapi_project/ingest_sop.py` | Chunking, embedding, upsert ke Qdrant/Chroma via factory |
| Config | `fastapi_project/config.py` | Settings via environment variables (Qdrant, ChromaDB, Provider) |
| Schemas | `fastapi_project/schemas.py` | Pydantic models |
| Celery App | `fastapi_project/celery_app.py` | Konfigurasi Celery, Queue routing, Event tracking |
| Tasks | `fastapi_project/tasks.py` | 2 task: `task_query_sop` (high) & `task_ingest_sop_textile` (low) + graceful shutdown |
| Redis Client | `fastapi_project/services/redis_client.py` | Redis connection, file hash, lock, dedup |
| LLM Service | `fastapi_project/services/llm.py` | 3 metode generate dengan Ollama/Gemini |
| Embedding | `fastapi_project/services/embedding.py` | Wrapper OLLaMA embedding (`nomic-embed-text`, 768d) |
| **Vector Store ABC** | `fastapi_project/services/vector_store.py` | **Abstract base class — interface untuk semua vector DB** |
| **QdrantStore** | `fastapi_project/services/qdrant_store.py` | **Qdrant implementation — production-grade vector DB** |
| **ChromaStore** | `fastapi_project/services/chroma_store.py` | **ChromaDB legacy — backward compat / fallback** |
| **Store Factory** | `fastapi_project/services/store_factory.py` | **Factory pattern — pilih provider via env var** |
| **DualStore** | `fastapi_project/services/dual_store.py` | **Dual-write: Qdrant + ChromaDB paralel** |
| **Migration Script** | `fastapi_project/scripts/migrate_chroma_to_qdrant.py` | **Batch migration ChromaDB → Qdrant** |

### Odoo Addons

| File | Path | Fungsi |
|------|------|--------|
| Textile RAG Controller | `addons/textile_rag/controllers/controllers.py` | Odoo ↔ FastAPI bridge, JSON endpoint |
| Textile RAG Models | `addons/textile_rag/models/models.py` | `TextileSopKnowledge`, `TextileChatSession` |
| MRP AI Expert Controller | `addons/mrp_ai_expert/controllers/controllers.py` | Public endpoint untuk widget chat |
| Chat Widget JS | `addons/textile_rag/static/src/components/chat_dashboard.js` | Odoo chat dashboard component |
| Chat Widget XML | `addons/textile_rag/static/src/components/chat_dashboard.xml` | OWL template |

### Infrastructure

| File | Path | Fungsi |
|------|------|--------|
| Docker Compose | `docker-compose.yaml` | 9 services, network, volumes (termasuk Qdrant) |
| Odoo Config | `config/odoo.conf` | Odoo database & addons config |
| Dockerfile | `fastapi_project/Dockerfile` | Python image dengan dependencies (termasuk qdrant-client) |

---

## Docker Services

| Service | Container Name | Image | Port | Fungsi |
|---------|---------------|-------|------|--------|
| `web-odoo19-ce` | `odoo19_ce` | odoo:19.0 | 8019 | ERP utama |
| `db` | `postgres19` | postgres:16 | 5419 | Database |
| `ai-engine` | `textile_ai_engine` | custom | 8000 | FastAPI RAG |
| `redis` | `textile_redis` | redis:7-alpine | 6379 | Celery broker |
| `ollama` | `ollama_server` | ollama/ollama | 11434 | Local LLM |
| **`qdrant`** | **`textile_qdrant`** | **qdrant/qdrant:v1.9.0** | **6333/6334** | **Vector Database (production)** |
| `celery_worker_high` | `textile_celery_high` | custom | — | Query worker |
| `celery_worker_low` | `textile_celery_low` | custom | — | Ingest worker |
| `flower` | `textile_flower` | mher/flower:2.0 | 5555 | Dashboard |

### Cara Menjalankan

```bash
# Start semua service
docker compose up -d

# Lihat log
docker compose logs -f

# Restart specific service
docker compose restart celery_worker_high

# Stop semua
docker compose down

# Migration data dari ChromaDB ke Qdrant (setelah semua service up)
docker compose exec ai-engine python scripts/migrate_chroma_to_qdrant.py

# Verifikasi hasil migrasi
docker compose exec ai-engine python scripts/migrate_chroma_to_qdrant.py --verify
```

---

## API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/query` | POST | Query RAG (sync, history) |
| `/api/query/ask` | POST | Query RAG (sync, tanpa history) |
| `/api/query/history` | POST | Query dengan session history |
| `/api/query/guards` | POST | Query dengan system guards |
| `/api/ingest` | POST | Upload & proses SOP |
| `/api/sops` | GET | Daftar semua SOP |
| `/api/v1/ingest` | POST | V1 — Upload SOP |
| `/api/v1/query` | POST | V1 — Query RAG |
| `/api/v1/query/async` | POST | V1 — Query async (Celery high priority) |
| `/api/v1/task/{id}` | GET | Poll status task Celery |
| `/api/health` | GET | Health check (termasuk vector store) |
| `/` | GET | Redirect to docs |

---

## Catatan Teknis

### Vector Database Provider

Pilih provider via environment variable `VECTOR_DB_PROVIDER`:

| Provider | Deskripsi | Kapan Digunakan |
|----------|-----------|-----------------|
| `qdrant` | **QdrantStore** — production-grade | Default. Untuk daily operation |
| `chroma` | **ChromaStore** — legacy | Fallback / backward compat |
| `dual` | **DualStore** — Qdrant + ChromaDB | **Phase 1 migrasi:** write ke BOTH, read dari Qdrant |

### Qdrant Configuration

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `QDRANT_HOST` | `qdrant` | Hostname (Docker service name) |
| `QDRANT_PORT` | `6333` | REST API port |
| `QDRANT_GRPC_PORT` | `6334` | gRPC port (optional, faster) |
| `QDRANT_COLLECTION` | `sop_textile` | Collection name |
| `QDRANT_VECTOR_SIZE` | `768` | Vector dimension (nomic-embed-text) |
| `QDRANT_TIMEOUT` | `30` | Connection timeout (seconds) |

### Qdrant Optimization

- **HNSW Index**: `m=32` (more connections = better recall), `ef_construct=200` (higher = more accurate build)
- **Quantization**: Scalar INT8 — hemat memory ~4x, minimal accuracy loss
- **Payload Indexes**: `division`, `sop_code`, `doc_id`, `file_hash` — semua KEYWORD type untuk fast filtering
- **Distance**: COSINE (0-1, higher = more similar) — sama dengan default ChromaDB

### Migration Strategy

```
Phase 1: Dual-Write ──── Write ke Qdrant + ChromaDB, Read dari Qdrant
     ↓
Phase 2: Qdrant Only ─── Hapus ChromaStore dependency, pure Qdrant
     ↓
Phase 3: Qdrant Cluster ─ Multiple nodes, sharding, replication
```

### Environment Variables Penting

| Variable | Value | File |
|----------|-------|------|
| `VECTOR_DB_PROVIDER` | `qdrant` (default) / `chroma` / `dual` | docker-compose.yaml |
| `QDRANT_HOST` | `qdrant` | docker-compose.yaml |
| `QDRANT_PORT` | `6333` | docker-compose.yaml |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | docker-compose.yaml |
| `AI_PROVIDER` | `ollama` | docker-compose.yaml |
| `OLLAMA_HOST` | `http://ollama:11434` | docker-compose.yaml |
| `REDIS_HOST` | `localhost` (dev) / `redis` (docker) | `fastapi_project/services/redis_client.py` |

### Celery Task Routing

```python
task_routes = {
    'tasks.task_query_sop':          {'queue': 'high_priority'},
    'tasks.task_ingest_sop_textile': {'queue': 'low_priority'},
}
```

### Retry Strategy

- **High Priority (Query)**: backoff max 300s (5 menit), max 5 retry
- **Low Priority (Ingest)**: backoff max 600s (10 menit), max 5 retry
- **Jitter**: random delay untuk cegah thundering herd

### Idempotency Flow

```
File masuk → Compute MD5 hash → Cek Redis key "rag_ingest_done:{hash}"
  ├─ Jika sudah ada → ⏭️ SKIP (return success)
  └─ Jika belum ada → SETNX lock "rag_ingest_lock:{hash}"
       ├─ Jika lock gagal (worker lain pegang) → ⏭️ SKIP
       └─ Jika lock berhasil → Proses → Set "rag_ingest_done:{hash}" (expire 7d)
```

### Flower Dashboard

- URL: `http://localhost:5555`
- Login: `admin` / `s3cur3P@ss`

---

## Resume Prompt untuk AI Agent

Di bawah ini adalah **prompt siap pakai** yang bisa Anda copy-paste ke AI agent di device lain agar pembelajaran berlanjut tanpa kehilangan konteks.

---

### 🌟 Opsi 1: Resume Full Konteks — Lanjut Modul 2.2

> Saya adalah Agus Rian Sirojudin. Saya sedang belajar Enterprise Scalability dengan proyek integrasi FastAPI RAG Engine + Odoo 19 ERP untuk pabrik tekstil.
>
> **Base directory proyek:** `/Users/rian/Docker/Odoo19CE`
>
> **Apa yang sudah selesai:**
>
> ### ✅ Modul 1.1 — Foundation & Core Integration (100%)
> - FastAPI + ChromaDB (vector store persistent)
> - Hybrid Search (Vector similarity 70% + BM25 keyword 30%)
> - Ollama LLM integration (nomic-embed-text untuk embedding)
> - Odoo bridge via JSON endpoint (textile_rag & mrp_ai_expert addons)
> - 12+ API endpoints (sync & async)
> - SOP ingestion pipeline (RecursiveCharacterTextSplitter, semantic chunking)
> - Docker compose dengan 8 services
> - Odoo chat dashboard widget (OWL component)
>
> ### ✅ Modul 1.2 — Resiliency, Monitoring & Error Handling (100%)
> - Advanced Task Routing, 2 Worker Terpisah, Exponential Backoff + Jitter
> - Idempotency Layer (MD5 hash → Redis SETNX lock), Redis Lock (1h TTL, 7d expiry)
> - Flower Dashboard (port 5555, auth admin/s3cur3P@ss)
> - Graceful Shutdown (SIGTERM → warm shutdown)
> - Event Tracking (worker_send_task_events, task_track_started)
>
> ### ✅ Modul 2.1 — Migrasi ChromaDB → Qdrant Phase 1 (100%)
> - **Abstract VectorStore ABC** dengan 7 method di `services/vector_store.py`
> - **QdrantStore** — full implementation dengan HNSW (m=32, ef_construct=200), INT8 scalar quantization, payload indexing
> - **ChromaStore** — legacy backward compat
> - **Store Factory** — pilih provider via env `VECTOR_DB_PROVIDER` (qdrant/chroma/dual)
> - **DualStore** — dual-write: Qdrant + ChromaDB paralel
> - **Migration Script** — `scripts/migrate_chroma_to_qdrant.py` (batch 50 docs, --verify, --force, --dry-run)
> - **Docker**: tambah service qdrant (v1.9.0, port 6333/6334)
> - **Qdrant Config**: collection `sop_textile`, vector 768d COSINE, payload indexes
> - **Semua endpoint** di main.py dan ingest_sop.py sudah menggunakan VectorStore interface
>
> **File kunci yang perlu diketahui AI agent:**
> - `docker-compose.yaml` — 9 services (baru: qdrant)
> - `fastapi_project/main.py` — FastAPI app, vector_store = get_vector_store()
> - `fastapi_project/ingest_sop.py` — Chunking + embedding + upsert via factory
> - `fastapi_project/services/vector_store.py` — ABC interface
> - `fastapi_project/services/qdrant_store.py` — Qdrant implementation
> - `fastapi_project/services/chroma_store.py` — ChromaDB legacy
> - `fastapi_project/services/store_factory.py` — Factory pattern
> - `fastapi_project/services/dual_store.py` — Dual-write
> - `fastapi_project/scripts/migrate_chroma_to_qdrant.py` — Migration script
> - `fastapi_project/config.py` — Settings (updated dengan Qdrant config)
> - `fastapi_project/celery_app.py`, `tasks.py`, `services/redis_client.py` — Celery + idempotency
>
> **API endpoints yang sudah ada:**
> - `POST /api/ingest` — Upload + chunk + embed + upsert (sync)
> - `POST /api/query` — Query RAG sinkron dengan BM25 + Vector hybrid
> - `POST /api/query/ask` — Query tanpa history
> - `POST /api/query/history` — Query dengan session history
> - `POST /api/query/guards` — Query dengan guardrail + threshold
> - `POST /api/v1/ingest` — Upload SOP async via Celery
> - `POST /api/v1/query` — Query RAG via ingest_sop.search_relevant_documents
> - `POST /api/v1/query/async` — Query async via Celery high_priority
> - `GET /api/v1/task/{task_id}` — Poll status task Celery
> - `GET /api/sops` — Daftar semua SOP
> - `GET /api/health` — Health check dengan vector store status
>
> **Sekarang saya ingin melanjutkan ke Modul 2.2: Advanced RAG Pipeline & Query Optimization.**
> Topik pertama: Multi-Query Retrieval — generate multiple query variations untuk improve recall. Tolong jelaskan dan bantu implementasi.

---

### ⚡ Opsi 2: Ringkas — Lanjut dari Modul Mana Saja

> Saya sedang belajar Enterprise Scalability. Proyek saya: FastAPI RAG + Odoo 19 ERP untuk pabrik tekstil.
>
> **Progress:**
> - Modul 1.1 Foundation ✅ — FastAPI, ChromaDB, Hybrid Search, Ollama, Odoo bridge, Docker
> - Modul 1.2 Resiliency ✅ — Celery priority queues, exponential backoff, idempotency (Redis lock), Flower monitoring, graceful shutdown
> - **Modul 2.1 Migrasi Qdrant ✅ — VectorStore ABC, QdrantStore, ChromaStore, StoreFactory, DualStore, migration script, Qdrant Docker service**
>
> **Sekarang saya ingin lanjut ke Modul [2.2/3/4]: [sebutkan topik]**  
> Contoh: "lanjut Modul 2.2 — Multi-Query Retrieval dan Reranking Pipeline"
>
> Base directory: `/Users/rian/Docker/Odoo19CE`
>
> File kunci: `docker-compose.yaml`, `fastapi_project/main.py`, `fastapi_project/services/vector_store.py`, `fastapi_project/services/qdrant_store.py`, `fastapi_project/services/store_factory.py`, `fastapi_project/ingest_sop.py`, `fastapi_project/tasks.py`, `fastapi_project/celery_app.py`, `fastapi_project/services/redis_client.py`

---

### 🔍 Opsi 3: Review / Testing Modul 2.1

> Tolong review implementasi Modul 2.1 (Migrasi ChromaDB → Qdrant) saya berikut ini dan bantu testing:
>
> **File kunci yang baru:**
> - `fastapi_project/services/vector_store.py` — Abstract base class
> - `fastapi_project/services/qdrant_store.py` — Qdrant implementation
> - `fastapi_project/services/chroma_store.py` — ChromaDB legacy
> - `fastapi_project/services/store_factory.py` — Factory pattern
> - `fastapi_project/services/dual_store.py` — Dual-write
> - `fastapi_project/scripts/migrate_chroma_to_qdrant.py` — Migration script
>
> **File yang dimodifikasi:**
> - `fastapi_project/main.py` — Ganti ChromaDB langsung dengan `get_vector_store()`
> - `fastapi_project/ingest_sop.py` — Ganti ChromaDB dengan factory + precomputed embeddings
> - `fastapi_project/config.py` — Tambah Qdrant settings
> - `docker-compose.yaml` — Tambah Qdrant service
> - `fastapi_project/Dockerfile` — Tambah qdrant-client
>
> **Yang perlu di-test:**
> 1. Apakah Qdrant service bisa start di Docker?
> 2. Apakah migration script berhasil copy data dari ChromaDB ke Qdrant?
> 3. Apakah query endpoint masih berfungsi dengan Qdrant sebagai backend?
> 4. Apakah dual-write mode berfungsi (write ke Qdrant + ChromaDB)?
>
> Tolong bantu saya test dengan Swagger UI atau curl.

---

> **💡 Tip:** Copy file `LEARNING_PROGRESS_REPORT.md` ini ke device lain bersama seluruh folder proyek. Kemudian berikan prompt dari salah satu opsi di atas ke AI agent untuk melanjutkan pembelajaran persis dari titik terakhir.
