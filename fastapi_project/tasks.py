# fastapi_project/tasks.py
import time
from celery_app import celery_app

# Import from the same folder (no W1_Chunking prefix)
try:
    from ingest_sop import extract_and_embed_document
except ImportError:
    # Fallback if ingest_sop.py runs procedurally
    extract_and_embed_document = None

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10
)
def task_ingest_sop_textile(self, file_path: str, metadata: dict):
    print(f"[Celery Worker] Starting async document processing for file: {file_path}")
    start_time = time.time()

    # IF THE INGEST LOGIC IS WRAPPED IN A FUNCTION
    if extract_and_embed_document:
        try:
            result = extract_and_embed_document(file_path, metadata)
            duration = time.time() - start_time
            print(f"[Celery Worker] Successfully completed RAG ingest in {duration:.2f} seconds.")
            return {"status": "SUCCESS", "file": file_path}
        except Exception as exc:
            print(f"[Celery Worker] Failed to process document due to: {exc}. Retrying...")
            raise self.retry(exc=exc)

    # IF THE INGEST LOGIC IS A PROCEDURAL SCRIPT (RUNS DIRECTLY)
    else:
        import subprocess
        import os

        script_path = os.path.join(os.path.dirname(__file__), "ingest_sop.py")
        try:
            result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                check=True
            )
            duration = time.time() - start_time
            print(f"[Celery Worker] Script output:\n{result.stdout}")
            print(f"[Celery Worker] Successfully executed ingest script in {duration:.2f} seconds.")
            return {"status": "SUCCESS", "file": file_path}
        except subprocess.CalledProcessError as err:
            print(f"[Celery Worker] Script failed. Error:\n{err.stderr}")
            raise self.retry(exc=err)
