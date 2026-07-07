# Textile MRP AI Expert: Enterprise RAG System with Hybrid Search

[![Odoo](https://img.shields.io/badge/Odoo-19.0%20CE-purple.svg)](https://www.odoo.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-red.svg)](https://www.trychroma.com/)
[![Celery](https://img.shields.io/badge/Task%20Queue-Celery-green.svg)](https://docs.celeryq.dev/)
[![Flower](https://img.shields.io/badge/Monitoring-Flower-ff69b4.svg)](https://flower.readthedocs.io/)

An enterprise-grade **Retrieval-Augmented Generation (RAG)** AI Assistant integrated directly into **Odoo 19 Manufacturing (MRP)**. Purpose-built for the textile manufacturing industry to help factory operators and Quality Control teams search Standard Operating Procedures (SOP), dyeing regulations, and work instructions instantly and accurately.

---

## 🏗️ System Architecture

The system adopts a **Decoupled Microservices** architecture, separating the core ERP from the AI Engine using a secure Docker internal network.

```text
[ Docker Internal Network - textile-network ]
========================================================================
┌───────────────┐        REST API Request        ┌──────────────────────┐
│   Odoo 19     │ ─────────────────────────────> │   FastAPI AI Engine  │
│ (OWL Frontend)│ <───────────────────────────── │   (textile_ai_engine)│
└───────┬───────┘        JSON API Response       └─────────┬────────────┘
        │                                                    │
        │ PostgreSQL (Port 5419)                              │ Hybrid Search
        v                                                    v
┌───────────────┐                        ┌──────────────────────────────┐
│  PostgreSQL   │                        │ 1. ChromaDB (Dense/Vector)   │
│   (Database)  │                        │ 2. Rank-BM25 (Sparse/Keyword)│
└───────────────┘                        └──────────┬───────────────────┘
                                                      │
                                             ┌────────v──────────┐
                                             │  LLM Service      │
                                             │  ┌──────────────┐ │
                                             │  │  Gemini API  │ │
                                             │  │  (optional)  │ │
                                             │  └──────┬───────┘ │
                                             │         │ fallback │
                                             │  ┌──────v───────┐ │
                                             │  │ Ollama       │ │
                                             │  │ (Docker)     │ │
                                             │  └──────────────┘ │
                                             └───────────────────┘

[ Async Task Processing — Priority Queues ]
              Redis Broker :6379
          ┌──────────────────────┐
          │   ┌──────────────┐   │
          │   │ HIGH PRIORITY│   │
          │   │ Query RAG    │   │
          │   │ conc=4       │   │
          │   │ t-limit=180s │   │
          │   └──────┬───────┘   │
          │          │           │
          │   ┌──────v───────┐   │
          │   │ LOW PRIORITY │   │
          │   │ SOP Ingest   │   │
          │   │ conc=1       │   │
          │   │ t-limit=600s │   │
          │   └──────┬───────┘   │
          └──────────┼───────────┘
                     │
            ┌────────v────────┐
            │  Flower Monitor │
            │  (Dashboard)    │
            │  :5555          │
            └─────────────────┘

[ Redis Idempotency Layer ]
  ┌─────────────┐
  │  rag_ingest │  ── File hash dedup
  │  _done:{md5}│  ── SETNX lock
  │  _lock:{md5}│  ── 7 day expiry
  └─────────────┘
========================================================================
```

## Data Communication Flow

### Ingestion Phase
Admin uploads SOP documents via the Odoo interface. The Odoo controller sends the file to the FastAPI endpoint:

- **Synchronous** (`/api/ingest`): Text is chunked and embedded into **ChromaDB** (vector) and indexed with **Rank-BM25** (keyword). Returns result immediately.
- **Asynchronous** (`/api/v1/ingest`): Dispatched to **Celery Worker LOW PRIORITY** queue via Redis. The API responds `202 Accepted` immediately. The worker processes chunking + embedding in background with full **idempotency protection** (MD5 hash → Redis lock → skip duplicate).

### Query Phase
1. Operator asks a question via the Odoo chatbox (OWL UI)
2. Odoo forwards to FastAPI via `/api/query` (sync) or `/api/v1/query/async` (async via Celery HIGH PRIORITY)
3. FastAPI executes **Hybrid Search**: Vector similarity (70%) + BM25 keyword (30%)
4. Retrieved context is sent to LLM for answer generation
5. **Fallback**: If Gemini API is unreachable, automatically falls back to local **Ollama (qwen2.5-coder:14b)** — ensuring factory operations are never interrupted

### Retry & Resilience
- **Exponential backoff + jitter**: Failed tasks retry with increasing delay (max 5 retries)
- **Graceful shutdown**: Workers complete in-flight tasks before exiting during container restarts
- **Time limits**: Tasks exceeding 180s (high) or 600s (low) are automatically terminated

---

## 🌟 Key Features

### Core RAG
- **Hybrid Search Accuracy:** Combines Dense Retrieval (semantic meaning) + Sparse Retrieval (exact SOP/code matching via BM25) to minimize AI hallucinations
- **Resilient AI Pipeline:** Automatic fallback from cloud LLM (Gemini) to local LLM (Ollama)
- **Multi-turn Chat History:** Isolated session-based conversation history per session ID
- **Guardrail Protection:** Input limits, forbidden patterns, vector distance thresholds (< 0.80)

### Async Task Processing (Celery)
- **Priority Task Routing:** Two isolated queues — `high_priority` for real-time queries, `low_priority` for background ingest
- **Dedicated Workers:** `celery_worker_high` (concurrency=4) for responsive queries, `celery_worker_low` (concurrency=1) for batch ingest
- **Exponential Backoff + Jitter:** Failed tasks retry with randomized delay to prevent thundering herd
- **Time Limits:** Hard/soft time limits prevent task hang (180s query, 600s ingest)

### Idempotency & Data Safety
- **MD5 Deduplication:** File content fingerprint prevents duplicate processing even on retry
- **Redis Distributed Lock:** SETNX-based lock prevents concurrent processing across workers
- **7-Day Expiry:** Processed files tracked for 7 days to avoid re-processing monthly SOP updates
- **Safety Net:** Graceful fallback if Redis is temporarily unavailable

### Visual Monitoring
- **Flower Dashboard:** Real-time task lifecycle monitoring (received → started → success/failure)
- **Worker Health:** CPU utilization, queue depth, task throughput per worker
- **Manual Intervention:** Retry failed tasks or revoke stuck tasks from the UI
- **Persistent History:** Task history persisted across container restarts

---

## 🛠️ Tech Stack

* **ERP Framework:** Odoo 19.0 Community Edition (Python, OWL Javascript Framework)
* **AI Core Backend:** FastAPI (Python 3.11)
* **Vector Database:** ChromaDB (single-node, persistent)
* **Lexical Search Engine:** Rank-BM25 (keyword + code matching)
* **LLM Providers:** Google Gemini API (cloud) + Ollama (local, Docker-based)
* **Task Queue:** Celery with Redis broker (2 queues: high/low priority)
* **Idempotency Layer:** Redis SETNX distributed lock + MD5 content hashing
* **Monitoring:** Flower Dashboard (real-time Celery monitoring)
* **Database:** PostgreSQL 16
* **Orchestration:** Docker & Docker Compose (8 services)

---

## 📁 Project Structure

```text
.
├── docker-compose.yaml            # Global orchestration (8 services)
├── LEARNING_PROGRESS_REPORT.md    # Learning progress & resume prompts
├── addons/
│   ├── mrp_ai_expert/             #   - MRP AI Expert integration
│   └── textile_rag/               #   - Textile RAG frontend (OWL widget)
├── fastapi_project/               # AI Engine source code (FastAPI)
│   ├── main.py                    #   - FastAPI app (12+ endpoints)
│   ├── celery_app.py              #   - Celery config + queue routing
│   ├── tasks.py                   #   - Async tasks (query_sop, ingest_sop)
│   ├── config.py                  #   - Application settings
│   ├── schemas.py                 #   - Pydantic models
│   ├── ingest_sop.py              #   - ChromaDB ingestion + file hash
│   ├── dockerfile                 #   - Python 3.11 container image
│   ├── services/
│   │   ├── embedding.py           #   - Embedding service (Ollama)
│   │   ├── llm.py                 #   - LLM service (Gemini + Ollama)
│   │   └── redis_client.py        #   - Redis lock & idempotency helpers
│   └── knowledge_base/            #   - Raw SOP text files
├── config/
│   └── odoo.conf                  # Odoo configuration file
└── ollama_data/                   # Ollama model storage (auto-created)
```

---

## 🚀 Installation & Usage Guide

### 1. Prerequisites

Make sure your system has:

* Docker Engine (Linux) or Docker Desktop (Mac/Windows)
* Git
* At least 16GB RAM (for Ollama LLM container)

### 2. Clone Repository

```bash
git clone https://github.com/rian/odoo19-textile-rag.git
cd odoo19-textile-rag
```

### 3. Environment Configuration

```bash
# (Optional) Set your Gemini API key in docker-compose.yaml
# for cloud LLM fallback. Look for: GEMINI_API_KEY=
```

### 4. Start All Services

Build images and start all 8 containers:

```bash
docker compose up -d --build
```

### 5. Pull the LLM Model

After containers are running:

```bash
docker exec ollama_server ollama pull qwen2.5-coder:14b
```

### 6. Access the Services

| Service | URL | Auth |
|---------|-----|------|
| **Odoo 19 ERP** | `http://localhost:8019` | — |
| **FastAPI Swagger Docs** | `http://localhost:8000/docs` | — |
| **Flower Dashboard** | `http://localhost:5555` | `admin` / `s3cur3P@ss` |
| **Redis** (internal) | `redis://redis:6379/0` | — |
| **Ollama API** (internal) | `http://ollama:11434` | — |

---

## 🔌 API Endpoint Reference

### Core RAG Endpoints (Synchronous)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query` | Query RAG with hybrid search + structured context |
| `POST` | `/api/query/ask` | Simple single-document query with distance guard |
| `POST` | `/api/query/history` | History-aware multi-turn query |
| `POST` | `/api/query/guards` | Query with full guardrail protection |
| `POST` | `/api/ingest` | Upload & ingest SOP document synchronously |

### V1 Endpoints (Async-ready)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/ingest` | Upload SOP — processed asynchronously via Celery **low_priority** queue |
| `POST` | `/api/v1/query` | RAG pipeline: retrieval → distance filter → LLM generation (sync) |
| `POST` | `/api/v1/query/async` | Query RAG — dispatched to Celery **high_priority** queue, returns `task_id` |
| `GET` | `/api/v1/task/{task_id}` | Poll status of any Celery task (PENDING → STARTED → SUCCESS/FAILURE) |

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sops` | List all registered SOPs in the system |
| `GET` | `/` | Redirect to Swagger docs |

### Example: Async Query (via Celery High Priority)

```bash
# Step 1 — Dispatch query to high_priority queue
curl -s -X POST "http://localhost:8000/api/v1/query/async" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "question=Bagaimana cara setting suhu dyeing polyester?" \
  -d "division=Dyeing"

# Response: {"task_id": "uuid-here", "status": "PENDING", "poll_url": "/api/v1/task/uuid-here"}

# Step 2 — Poll for result
curl -s "http://localhost:8000/api/v1/task/<TASK_ID>"
```

### Example: Async Ingest (via Celery Low Priority)

```bash
curl -s -X POST "http://localhost:8000/api/v1/ingest" \
  -F "file=@fastapi_project/knowledge_base/sop_celup_polyester.txt"
```

### Example: Idempotency in Action

Upload the same file twice:

```bash
# First upload — processes normally
curl -s -X POST "http://localhost:8000/api/v1/ingest" -F "file=@SOP.txt"
# Response: 202 Accepted → worker processes → SUCCESS

# Second upload (same file) — skips with IDEMPOTENCY
curl -s -X POST "http://localhost:8000/api/v1/ingest" -F "file=@SOP.txt"
# Response: 202 Accepted → worker detects duplicates → SKIPPED
```

---

## 🐳 Docker Services Overview

| Service | Image | Container Name | Port(s) | Queue | Concurrency | Time Limit |
|---------|-------|----------------|---------|-------|-------------|------------|
| `web-odoo19-ce` | `odoo:19.0` | `odoo19_ce` | `8019:8069` | — | — | — |
| `db` | `postgres:16` | `postgres19` | `5419:5432` | — | — | — |
| `ai-engine` | Custom | `textile_ai_engine` | `8000:8000` | — | — | — |
| `redis` | `redis:7-alpine` | `textile_redis` | `6379:6379` | — | — | — |
| `ollama` | `ollama/ollama` | `ollama_server` | `11434:11434` | — | — | — |
| `celery_worker_high` | Custom | `textile_celery_high` | — | `high_priority` | 4 | 180s |
| `celery_worker_low` | Custom | `textile_celery_low` | — | `low_priority` | 1 | 600s |
| `flower` | `mher/flower:2.0` | `textile_flower` | `5555:5555` | — | — | — |

All services are connected to the `textile-network` bridge for internal DNS resolution.

---

## 📝 Recent Updates (Modul 1.2 — Resiliency, Monitoring & Error Handling)

### Tahap 1 — Advanced Task Routing
- **Priority Queues:** Introduced `high_priority` (real-time queries) and `low_priority` (background ingest) queues via Celery + kombu `Queue`
- **Dedicated Workers:** Split into `celery_worker_high` (concurrency=4, max-tasks=100) and `celery_worker_low` (concurrency=1, max-tasks=10)
- **Asynchronous Query Endpoints:** Added `POST /api/v1/query/async` (dispatches to Celery) and `GET /api/v1/task/{id}` (polling)

### Tahap 2 — Retry & Idempotency
- **Exponential Backoff + Jitter:** All tasks auto-retry with randomized exponential delay (`max_retries=5`, `retry_backoff_max=300-600s`)
- **Redis Idempotency Layer:** MD5 file hashing → Redis SETNX lock → `is_file_already_processed` → automatic skip on duplicates
- **Lock Management:** `acquire_process_lock` (1h TTL), `release_process_lock`, `mark_file_as_processed` (7d expiry)
- **Safety Net:** Graceful fallback proceeds without lock if Redis is unavailable

### Tahap 3 — Visual Monitoring & Graceful Shutdown
- **Flower Dashboard:** Real-time Celery monitoring at `localhost:5555` (auth: `admin`/`s3cur3P@ss`)
- **Time Limits:** Hard/soft time limits prevent task hang (180s query, 600s ingest)
- **Event Tracking:** Full Celery event stream enabled for complete task lifecycle visibility
- **Graceful Shutdown:** SIGTERM/SIGINT handlers allow workers to complete in-progress tasks before exiting during container restarts

---

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your improvements.

---

Developed with ❤️ by **Rian**
