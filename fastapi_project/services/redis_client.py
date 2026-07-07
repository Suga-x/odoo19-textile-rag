# fastapi_project/services/redis_client.py
import os
import hashlib
import redis

# Redis connection — single source of truth
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # Di Docker = "redis"
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Lock expiry: 7 hari (604800 detik) — SOP jarang berubah
LOCK_EXPIRE_SECONDS = 604800


def get_redis_client():
    """
    Membuat koneksi Redis.
    Gunakan fungsi ini daripada global variable agar connection lazy-loaded.
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,  # Return string, bukan bytes
        socket_connect_timeout=3,
        socket_timeout=3
    )


def compute_file_hash(file_path: str) -> str:
    """
    Menghitung MD5 hash dari isi file.
    Hash ini digunakan sebagai fingerprint unik untuk idempotency.

    Args:
        file_path: Path ke file SOP

    Returns:
        MD5 hex digest (32 karakter)
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        # Baca file dalam chunk 4KB — aman untuk file besar
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def is_file_already_processed(file_hash: str, redis_client=None) -> bool:
    """
    Cek apakah file dengan hash tertentu sudah pernah diproses.
    Menggunakan key: "rag_ingest_done:{file_hash}"

    Returns:
        True jika sudah pernah diproses, False jika belum
    """
    if redis_client is None:
        redis_client = get_redis_client()

    key = f"rag_ingest_done:{file_hash}"
    return redis_client.exists(key) == 1


def mark_file_as_processed(file_hash: str, redis_client=None):
    """
    Tandai bahwa file dengan hash tertentu sudah selesai diproses.
    Key akan expire otomatis setelah LOCK_EXPIRE_SECONDS (7 hari).

    Args:
        file_hash: MD5 hash dari file
        redis_client: Opsional, Redis client instance
    """
    if redis_client is None:
        redis_client = get_redis_client()

    key = f"rag_ingest_done:{file_hash}"
    redis_client.setex(key, LOCK_EXPIRE_SECONDS, "done")
    print(f"[IDEMPOTENCY] File hash {file_hash[:8]}... marked as processed (expire 7d).")


def acquire_process_lock(file_hash: str, redis_client=None) -> bool:
    """
    Mengambil lock pemrosesan file.
    Mencegah 2 worker memproses file yang SAMA secara bersamaan.

    Cara kerja:
    - SETNX (SET if Not eXists): return 1 jika key belum ada, 0 jika sudah ada
    - Key: "rag_ingest_lock:{file_hash}"
    - Expire: 1 jam (3600 detik) — antisipasi worker crash

    Args:
        file_hash: MD5 hash dari file
        redis_client: Opsional, Redis client instance

    Returns:
        True jika lock berhasil diambil, False jika sudah diambil worker lain
    """
    if redis_client is None:
        redis_client = get_redis_client()

    key = f"rag_ingest_lock:{file_hash}"
    # SETNX: hanya set jika key belum ada
    acquired = redis_client.setnx(key, "processing")

    if acquired:
        # Set expiry — antisipasi worker crash sebelum sempat selesai
        redis_client.expire(key, 3600)  # 1 jam
        print(f"[IDEMPOTENCY] Lock acquired for hash {file_hash[:8]}... (expire 1h).")
        return True
    else:
        # Cek TTL — kalau worker sebelumnya crash, lock mungkin masih stuck
        ttl = redis_client.ttl(key)
        print(f"[IDEMPOTENCY] Lock already held for hash {file_hash[:8]}... (TTL: {ttl}s).")
        return False


def release_process_lock(file_hash: str, redis_client=None):
    """
    Melepas lock pemrosesan setelah selesai.
    Biasanya tidak perlu karena expire otomatis, tapi untuk jaga-jaga.

    Args:
        file_hash: MD5 hash dari file
        redis_client: Opsional, Redis client instance
    """
    if redis_client is None:
        redis_client = get_redis_client()

    key = f"rag_ingest_lock:{file_hash}"
    redis_client.delete(key)
    print(f"[IDEMPOTENCY] Lock released for hash {file_hash[:8]}...")
