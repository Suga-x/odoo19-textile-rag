
# Textile MRP AI Expert: Enterprise RAG System with Hybrid Search

[![Odoo](https://img.shields.io/badge/Odoo-19.0%20CE-purple.svg)](https://www.odoo.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-red.svg)](https://www.trychroma.com/)

Sistem AI Assistant berbasis **Retrieval-Augmented Generation (RAG)** skala *enterprise* yang diintegrasikan langsung ke dalam modul **Odoo 19 Manufacturing (MRP)**. Sistem ini dirancang khusus untuk industri manufaktur tekstil guna membantu operator pabrik dan tim *Quality Control* (QC) melakukan pencarian Standar Operasional Prosedur (SOP), regulasi celup, dan instruksi kerja secara instan dan akurat.

---

## 🏗️ Arsitektur Sistem (System Architecture)

Sistem ini mengadopsi arsitektur *Decoupled Microservices* yang memisahkan core ERP dengan AI Engine menggunakan jaringan internal Docker yang aman.

```text
[ Docker Internal Network ]
========================================================================
┌───────────────┐        REST API Request        ┌─────────────────┐
│   Odoo 19     │ ─────────────────────────────> │ FastAPI Server  │
│ (OWL Frontend)│ <───────────────────────────── │   (AI Engine)   │
└───────┬───────┘        JSON API Response       └────────┬────────┘
        │                                                 │
        │ PostgreSQL (Port 5432)                          │ Hybrid Search
        v                                                 v
┌───────────────┐                        ┌─────────────────────────────────┐
│  PostgreSQL   │                        │ 1. ChromaDB (Dense/Vector Vector)│
│   (Database)  │                        │ 2. Rank-BM25 (Sparse/Keywords)  │
└───────────────┘                        └────────────────┬────────────────┘
                                                          │
                                                          │ LiteLLM Router
                                                          v
                                         ┌─────────────────────────────────┐
                                         │     Resilient Provider Flow     │
                                         │ ┌──────────────┐   ┌──────────┐ │
                                         │ │  Gemini API  │──>│  Ollama  │ │
                                         │ │   (Cloud)    │   │ (Local)  │ │
                                         │ └──────────────┘   └──────────┘ │
                                         └─────────────────────────────────┘
========================================================================

```

## Alur Kerja Komunikasi Data:

* **Ingestion Phase:** Admin mengunggah dokumen SOP tekstil melalui antarmuka Odoo. Controller Odoo mengirimkan file berkas ke endpoint `/api/ingest` milik FastAPI. Teks kemudian dipotong (*chunking*) dan ditanamkan ke **ChromaDB** (sebagai representasi vektor) serta diindeks menggunakan **Rank-BM25** (untuk pencarian kata kunci eksak).

* **Query Phase:** Operator menanyakan keluhan mesin atau prosedur via chatbox Odoo (OWL UI). Odoo meneruskan pesan tersebut ke FastAPI lewat endpoint `/api/query`.

* **Retrieval (Hybrid Search):** FastAPI mengeksekusi *Hybrid Search* dengan menggabungkan hasil pencarian semantik (ChromaDB) dan pencarian leksikal/kode dokumen eksak (BM25) untuk mendapatkan konteks dokumen yang paling relevan.


* **Generation & Fallback:** Konteks dokumen dikirim ke LLM melalui LiteLLM. Jika koneksi cloud **Gemini API** terputus, sistem otomatis mengalihkan beban (*resilient fallback*) ke model lokal **Ollama (Qwen2.5-Coder)** sehingga operasional pabrik tidak terganggu.

---

## 🌟 Fitur Utama

* **Hybrid Search Accuracy:** Menggabungkan pencarian makna teks (*Dense Retrieval*) dan pencarian kode instruksi/SOP eksak (*Sparse Retrieval - BM25*) untuk meminimalisir halusinasi AI pada data teknis pabrik.
* **Resilient AI Pipeline:** Mekanisme *fallback* otomatis dari model komersial Cloud (Gemini) ke model lokal (Ollama) saat terjadi gangguan internet di area pabrik.
* **Isolated Session Chat History:** Riwayat percakapan diisolasi penuh berbasis ID Dokumen/ID Operator Odoo, memastikan konteks obrolan tetap relevan selama sesi analisis berlangsung.
* **Fully Dockerized Ecosystem:** Seluruh komponen (Odoo, DB, FastAPI, Vector Store) dapat dinyalakan secara instan di server lokal pabrik (*on-premise*) maupun *cloud* hanya dengan satu perintah Docker Compose.

---

## 🛠️ Teknologi yang Digunakan (Tech Stack)

* **ERP Framework:** Odoo 19.0 Community Edition (Python, OWL Javascript Framework)
* **AI Core Backend:** FastAPI (Python 3.11)
* **Vector Database:** ChromaDB
* **Lexical Search Engine:** Rank-BM25
* **LLM Gateway:** LiteLLM (Google Gemini & Ollama Router)
* **Database Utama:** PostgreSQL 16
* **Infrastruktur:** Docker & Docker Compose

---

## 🚀 Panduan Instalasi & Penggunaan

### 1. Prasyarat

Pastikan komputer Anda sudah terpasang:

* Docker Desktop (untuk Mac/Windows) atau Docker Engine (untuk Linux)
* Git

### 2. Klon Repositori

```bash
git clone [https://github.com/rian/odoo19-textile-rag.git](https://github.com/rian/odoo19-textile-rag.git)
cd odoo19-textile-rag

```

### 3. Struktur Direktori Proyek

```text
.
├── docker-compose.yaml     # Orkestrasi container global
├── addons/                 # Custom module Odoo (mrp_ai_expert & textile_rag)
├── fastapi_project/        # Source code AI Engine FastAPI
│   ├── main.py
│   ├── Dockerfile
│   └── services/
└── config/                 # Berkas konfigurasi Odoo

```

### 4. Menyalakan Ekosistem Aplikasi

Jalankan perintah di bawah ini pada root direktori untuk membangun *image* dan menyalakan seluruh container secara terpusat:

```bash
docker-compose up --build

```

Setelah proses selesai, layanan dapat diakses di alamat berikut:

* **Odoo 19 ERP:** `http://localhost:8019`
* **FastAPI Swagger Docs:** `http://localhost:8000/docs`

---

## 📊 Integrasi API Endpoint Utama (FastAPI)

AI Engine menyediakan endpoint krusial yang dikonsumsi oleh Odoo Controller:

* `POST /api/ingest` : Menerima unggahan dokumen dari Odoo untuk diproses ke dalam Vector Store.
* `POST /api/query` : Menerima pertanyaan dari operator, mengeksekusi *Hybrid Search*, dan mengembalikan jawaban LLM.
* `GET /api/query/history` : Mengambil riwayat percakapan berdasarkan token sesi aktif.

---

Developed with ❤️ by **Rian**
