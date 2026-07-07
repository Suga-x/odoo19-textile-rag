import os
from celery import Celery
from kombu import Queue

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "textile_rag_tasks",
    broker=BROKER_URL,
    backend=BROKER_URL
)

# ====================================================================
# 🎯 ADVANCED TASK ROUTING — Priority Queues
# ====================================================================
# high_priority: Real-time operator queries (Harus cepat, < 200ms)
# low_priority:  Batch ingest SOP bulanan (Best-effort, menit-jam)
# ====================================================================
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jakarta",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    # Routing tasks ke queue masing-masing berdasarkan nama task
    task_routes={
        'tasks.task_query_sop':           {'queue': 'high_priority'},
        'tasks.task_ingest_sop_textile':  {'queue': 'low_priority'},
    },
    # Definisi queue dengan routing key untuk Redis
    task_queues=(
        Queue('high_priority', routing_key='high.#'),
        Queue('low_priority',  routing_key='low.#'),
    ),
)

# ====================================================================
# 📊 MONITORING & EVENT TRACKING — Untuk Flower Dashboard
# ====================================================================
# Konfigurasi ini WAJIB agar Flower bisa memonitor task secara real-time:
#
# worker_send_task_events=True   → Kirim semua event task ke Flower
# task_send_sent_event=True      → Kirim event "task-sent" saat task dikirim
# task_track_started=True        → Flower bisa lihat status "started"
# result_expires=3600            → Hasil task disimpan 1 jam di Redis
# ====================================================================
celery_app.conf.update(
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_track_started=True,
    result_expires=3600,
)
