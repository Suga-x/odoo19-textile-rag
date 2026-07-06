# Textile MRP AI Expert: Enterprise RAG System with Hybrid Search

[![Odoo](https://img.shields.io/badge/Odoo-19.0%20CE-purple.svg)](https://www.odoo.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-red.svg)](https://www.trychroma.com/)
[![Celery](https://img.shields.io/badge/Task%20Queue-Celery-green.svg)](https://docs.celeryq.dev/)

An enterprise-grade **Retrieval-Augmented Generation (RAG)** AI Assistant integrated directly into **Odoo 19 Manufacturing (MRP)**. This system is purpose-built for the textile manufacturing industry to help factory operators and Quality Control teams search Standard Operating Procedures (SOP), dyeing regulations, and work instructions instantly and accurately.

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

[ Background Processing ]
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│  Redis   │<───>│ Celery Worker│<───>│ Async SOP Ingest│
│ (Broker) │     │ (textile_)   │     └─────────────────┘
└──────────┘     └──────────────┘
========================================================================
```

## Data Communication Flow

* **Ingestion Phase:** Admin uploads SOP documents via the Odoo interface. The Odoo controller sends the file to the FastAPI `/api/ingest` endpoint. Text is chunked and embedded into **ChromaDB** (as vector representations) and indexed with **Rank-BM25** (for exact keyword search).

* **Background Ingestion (Async):** For larger documents, the `/api/v1/ingest` endpoint dispatches processing to a **Celery Worker** via Redis, allowing the API to respond immediately while ingestion happens in the background.

* **Query Phase:** An operator asks a machine issue or procedure question via the Odoo chatbox (OWL UI). Odoo forwards the message to FastAPI via the `/api/query` endpoint.

* **Retrieval (Hybrid Search):** FastAPI executes a **Hybrid Search** combining semantic search results (ChromaDB) and exact lexical/document code search (BM25) to retrieve the most relevant document context.

* **Generation & Fallback:** The document context is sent to the LLM. If the cloud **Gemini API** is unreachable, the system automatically falls back to the local **Ollama (qwen2.5-coder:14b)** running as a Docker container — ensuring factory operations are never interrupted.

* **History-Aware Queries:** The `/api/query/history` endpoint maintains session-based conversation history for contextual multi-turn dialogue.

* **Guardrails:** The `/api/query/guards` endpoint enforces input validation, forbidden keyword filtering, and distance threshold checks before any LLM call.

---

## 🌟 Key Features

* **Hybrid Search Accuracy:** Combines Dense Retrieval (semantic meaning) and Sparse Retrieval (exact SOP/code matching via BM25) to minimize AI hallucinations on factory technical data.
* **Resilient AI Pipeline:** Automatic fallback from cloud LLM (Gemini) to local LLM (Ollama) during internet outages in factory areas.
* **Isolated Session Chat History:** Conversation history is fully isolated per session ID, maintaining relevant context during analysis sessions.
* **Async Document Ingestion:** Large SOP files are processed in the background via Celery workers, keeping the API responsive.
* **Guardrail Protection:** Multi-layer safety checks including character limits, forbidden patterns, and vector distance thresholds prevent misuse.
* **Fully Dockerized Ecosystem:** All components (Odoo, PostgreSQL, FastAPI, ChromaDB, Redis, Ollama) spin up instantly on-premise or in the cloud with a single Docker Compose command.

---

## 🛠️ Tech Stack

* **ERP Framework:** Odoo 19.0 Community Edition (Python, OWL Javascript Framework)
* **AI Core Backend:** FastAPI (Python 3.11)
* **Vector Database:** ChromaDB
* **Lexical Search Engine:** Rank-BM25
* **LLM Providers:** Google Gemini API (cloud) + Ollama (local, Docker-based)
* **Task Queue:** Celery with Redis broker
* **Database:** PostgreSQL 16
* **Infrastructure:** Docker & Docker Compose

---

## 📁 Project Structure

```text
.
├── docker-compose.yaml        # Global container orchestration (6 services)
├── addons/                    # Odoo custom modules
│   ├── mrp_ai_expert/         #   - MRP AI Expert integration
│   └── textile_rag/           #   - Textile RAG frontend (OWL)
├── fastapi_project/           # AI Engine source code (FastAPI)
│   ├── main.py                #   - FastAPI app with all endpoints
│   ├── celery_app.py          #   - Celery application config
│   ├── tasks.py               #   - Async task definitions
│   ├── config.py              #   - Application settings
│   ├── schemas.py             #   - Pydantic request/response models
│   ├── llm_router.py          #   - LLM routing from context list
│   ├── ingest_sop.py          #   - ChromaDB ingestion & search
│   ├── dockerfile             #   - Python 3.11 container image
│   ├── services/
│   │   ├── embedding.py       #   - Embedding service (Ollama)
│   │   └── llm.py             #   - LLM service (Gemini + Ollama fallback)
│   └── W1_Chunking/           #   - Chunking experiments
│       ├── ingest_sop.py
│       └── test_chunking.py
├── config/
│   └── odoo.conf              # Odoo configuration file
└── knowledge_base/            # Raw SOP text files
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

Copy the provided configuration and adjust as needed:

```bash
# (Optional) Set your Gemini API key in docker-compose.yaml
# if you want to use Gemini instead of local Ollama
# Look for: GEMINI_API_KEY=AIzaSyYourRealGeminiKeyHere
```

### 4. Start All Services

Build images and start all containers:

```bash
docker compose up -d --build
```

### 5. Pull the LLM Model

After the containers are running, pull the local Qwen model into the Ollama container:

```bash
docker exec ollama_server ollama pull qwen2.5-coder:14b
```

### 6. Access the Services

| Service | URL |
|---------|-----|
| **Odoo 19 ERP** | `http://localhost:8019` |
| **FastAPI Swagger Docs** | `http://localhost:8000/docs` |
| **Redis** (internal) | `redis://redis:6379/0` |
| **Ollama API** (internal) | `http://ollama:11434` |

---

## 🔌 API Endpoint Reference

### Core RAG Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query` | Query RAG with hybrid search + structured context |
| `POST` | `/api/query/ask` | Simple single-document query with distance guard |
| `POST` | `/api/query/history` | History-aware multi-turn query |
| `POST` | `/api/query/guards` | Query with full guardrail protection (input filter + distance threshold) |
| `POST` | `/api/ingest` | Upload & ingest SOP document synchronously |

### Background Processing Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/ingest` | Upload SOP — processed asynchronously via Celery worker |
| `POST` | `/api/v1/query` | RAG pipeline: retrieval → distance filter (≤0.80) → LLM generation |

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sops` | List all registered SOPs in the system |
| `GET` | `/api/health` | Health check |

### Example: Query with Guardrails

```bash
curl -X POST "http://localhost:8000/api/query/guards" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the target moisture content tolerance?", "division": "Finishing"}'
```

### Example: Async Ingest via Celery

```bash
curl -X POST "http://localhost:8000/api/v1/ingest" \
  -F "file=@SOP_DYEING.txt"
```

---

## 🐳 Docker Services Overview

| Service | Image | Container Name | Port(s) |
|---------|-------|----------------|---------|
| `web-odoo19-ce` | `odoo:19.0` | `odoo19_ce` | `8019:8069` |
| `db` | `postgres:16` | `postgres19` | `5419:5432` |
| `ai-engine` | Custom (`./fastapi_project`) | `textile_ai_engine` | `8000:8000` |
| `redis` | `redis:7-alpine` | `textile_redis` | `6379:6379` |
| `ollama` | `ollama/ollama:latest` | `ollama_server` | `11434:11434` |
| `celery_worker` | Custom (`./fastapi_project`) | `textile_celery_worker` | — |

All services are connected to the `textile-network` bridge for internal DNS resolution.

---

## 📝 Recent Updates

- **Async Ingestion:** Added Celery worker + Redis broker for background document processing (`/api/v1/ingest`)
- **Ollama as Docker Service:** Ollama LLM now runs as a container on the internal network instead of requiring a host installation
- **LLM Fallback:** Native `ollama.generate()` used for local fallback, bypassing LiteLLM HTTP routing issues in Docker
- **New Query Pipeline:** `/api/v1/query` implements full RAG pipeline with ChromaDB retrieval → distance filtering (≤0.80) → LLM generation
- **Code Refactoring:** All identifiers and comments translated from Indonesian to English for international standards
- **Multi-layer Guardrails:** Input validation, forbidden keyword detection, and distance threshold checks before LLM invocation

---

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your improvements.

---

Developed with ❤️ by **Rian**
