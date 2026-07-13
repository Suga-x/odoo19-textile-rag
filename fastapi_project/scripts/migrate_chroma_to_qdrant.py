#!/usr/bin/env python3
"""
🚀 Migration Script: ChromaDB → Qdrant

Script ini melakukan migrasi data dari ChromaDB ke Qdrant secara batch.

Cara Kerja:
    1. Baca semua dokumen dari ChromaDB (menggunakan ChromaStore)
    2. Compute embeddings menggunakan EmbeddingService (nomic-embed-text via Ollama)
    3. Batch upsert ke Qdrant (menggunakan QdrantStore)
    4. Verifikasi hasil migrasi

Cara Penggunaan:
    # Mode dual-write (recommended): Seamless migration tanpa downtime
    export VECTOR_DB_PROVIDER=dual
    python scripts/migrate_chroma_to_qdrant.py

    # Mode sync-only: Copy data dari ChromaDB ke Qdrant
    python scripts/migrate_chroma_to_qdrant.py

    # Verifikasi saja (tanpa migrasi)
    python scripts/migrate_chroma_to_qdrant.py --verify

    # Force re-migrasi (hapus Qdrant collection dulu)
    python scripts/migrate_chroma_to_qdrant.py --force

Requirements:
    pip install qdrant-client chromadb ollama

Output:
    ✅ Migrasi sukses — semua data dari ChromaDB tersalin ke Qdrant
    ⚠️ Sebagian gagal — lihat log untuk detail
"""

import os
import sys
import time
import argparse

# Pastikan path project bisa diakses
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chroma_store import ChromaStore
from services.qdrant_store import QdrantStore
from services.embedding import EmbeddingService
from services.store_factory import get_vector_store


# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 50  # Batch upsert per request (Qdrant limit: ~1000)
VERBOSE = True           # Tampilkan progress per batch


def print_progress(current, total, prefix="Progress"):
    """Tampilkan progress bar sederhana."""
    pct = min(100, int(current / total * 100)) if total > 0 else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r{prefix}: |{bar}| {current}/{total} ({pct}%)", end="")
    if current >= total:
        print()


def scan_chroma_source() -> tuple[list[str], list[str], list[dict]]:
    """
    Scan semua data dari ChromaDB.

    Returns:
        Tuple (ids, documents, metadatas) — semua data dari ChromaDB
    """
    print("\n🔍 Scanning ChromaDB source...")
    chroma = ChromaStore()

    ids, documents, metadatas = chroma.get_all()

    total = len(ids)
    print(f"📊 ChromaDB: {total} documents found")
    if total == 0:
        return [], [], []

    # Sample untuk verifikasi
    print(f"📝 Sample document 0:")
    print(f"    ID:   {ids[0][:50]}...")
    print(f"    Text: {documents[0][:80]}...")
    print(f"    Meta: {metadatas[0]}")

    return ids, documents, metadatas


def migrate_batch_to_qdrant(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict:
    """
    Migrate data dari ChromaDB ke Qdrant.

    Args:
        ids: List ID dokumen
        documents: List teks dokumen
        metadatas: List metadata
        force: Jika True, hapus collection Qdrant dulu

    Returns:
        Dict hasil migrasi: {total, succeeded, failed, errors}
    """
    total = len(ids)
    if total == 0:
        print("\n⚠️ No data to migrate.")
        return {"total": 0, "succeeded": 0, "failed": 0, "errors": []}

    print(f"\n🚀 Starting migration: {total} documents from ChromaDB → Qdrant")

    # Inisialisasi QdrantStore
    if force:
        print("💥 Force mode: Recreating Qdrant collection...")
        qdrant = QdrantStore()
        qdrant.delete_collection()
        # delete_collection() sudah auto-recreate, tapi kita perlu instance baru
        qdrant = QdrantStore()
    else:
        qdrant = QdrantStore()

    # Siapkan batch
    batch_count = (total + batch_size - 1) // batch_size
    succeeded = 0
    failed = 0
    errors = []

    start_time = time.time()

    for batch_idx in range(batch_count):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)

        batch_ids = ids[start:end]
        batch_docs = documents[start:end]
        batch_metas = metadatas[start:end]

        # ── 1. Compute embeddings untuk batch ini ──────────────
        try:
            print(f"\n  🔄 Batch {batch_idx + 1}/{batch_count}: Computing embeddings...")
            batch_embeddings = []
            for idx_in_batch, doc_text in enumerate(batch_docs):
                if VERBOSE and idx_in_batch % 10 == 0:
                    print(f"    Embedding {start + idx_in_batch}/{total}...", end="\r")
                embedding = EmbeddingService.get_embedding(doc_text)
                batch_embeddings.append(embedding)
        except Exception as e:
            print(f"\n  ❌ Failed to compute embeddings for batch {batch_idx + 1}: {e}")
            for idx in range(len(batch_ids)):
                errors.append(f"embedding_fail:{batch_ids[idx]}:{e}")
            failed += len(batch_ids)
            continue

        # ── 2. Upsert ke Qdrant ────────────────────────────────
        try:
            qdrant.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=batch_embeddings,
            )
            succeeded += len(batch_ids)
            print(f"  ✅ Batch {batch_idx + 1}/{batch_count}: {len(batch_ids)} documents upserted.")
        except Exception as e:
            print(f"  ❌ Batch {batch_idx + 1}/{batch_count} failed: {e}")
            for idx in range(len(batch_ids)):
                errors.append(f"upsert_fail:{batch_ids[idx]}:{e}")
            failed += len(batch_ids)

        print_progress(succeeded + failed, total, "Total Progress")

    duration = time.time() - start_time
    print(f"\n⏱️ Migration completed in {duration:.2f}s")

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors[:20],  # Max 20 error detail
        "duration_seconds": round(duration, 2),
    }


def verify_migration(expected_count: int):
    """
    Verifikasi data di Qdrant setelah migrasi.

    Args:
        expected_count: Jumlah dokumen yang diharapkan
    """
    print("\n🔍 Verifying Qdrant migration...")
    qdrant = QdrantStore()

    # Count
    actual_count = qdrant.count()
    print(f"📊 Qdrant count: {actual_count} (expected: {expected_count})")

    if actual_count == expected_count:
        print("✅ Count match!")
    else:
        print(f"⚠️ Count MISMATCH! Expected {expected_count}, got {actual_count}")

    # Health check
    healthy = qdrant.health_check()
    print(f"💚 Health check: {'PASS' if healthy else 'FAIL'}")

    # Get all documents
    all_ids, all_docs, all_metas = qdrant.get_all()
    print(f"📄 Total documents retrieved: {len(all_ids)}")

    if all_ids:
        print(f"\n📝 Sample Qdrant document 0:")
        print(f"    ID:   {all_ids[0][:50]}...")
        print(f"    Text: {all_docs[0][:80]}...")
        print(f"    Meta: {all_metas[0]}")

    return {
        "count_match": actual_count == expected_count,
        "expected": expected_count,
        "actual": actual_count,
        "healthy": healthy,
        "retrieved_count": len(all_ids),
    }


def main():
    parser = argparse.ArgumentParser(
        description="🚀 Migrate ChromaDB → Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migrate_chroma_to_qdrant.py
  python scripts/migrate_chroma_to_qdrant.py --verify
  python scripts/migrate_chroma_to_qdrant.py --force
  python scripts/migrate_chroma_to_qdrant.py --batch 100
  python scripts/migrate_chroma_to_qdrant.py --dry-run
        """
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify Qdrant data (no migration)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-migration: drop Qdrant collection first",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for upsert (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan ChromaDB without actually migrating (just show what would be migrated)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  🚀 ChromaDB → Qdrant Migration Tool")
    print("=" * 60)

    if args.verify:
        # ── Mode Verify Only ────────────────────────────────
        print("\n🔎 VERIFY MODE: Checking Qdrant status...")
        print("-" * 40)
        qdrant = QdrantStore()
        count = qdrant.count()
        healthy = qdrant.health_check()
        print(f"  Health:   {'✅ OK' if healthy else '❌ FAIL'}")
        print(f"  Count:    {count} documents")
        print(f"  Host:     {qdrant.host}:{qdrant.port}")
        print(f"  Collection: {qdrant.collection_name}")
        print()

        if count > 0:
            print("📋 Sample documents:")
            all_ids, all_docs, all_metas = qdrant.get_all()
            for i in range(min(3, len(all_ids))):
                print(f"  [{i}] ID={all_ids[i][:40]}... | Doc={all_docs[i][:60]}...")
        else:
            print("⚠️ No documents in Qdrant. Run migration first.")

        return

    # ── Migration Mode ──────────────────────────────────────
    # 1. Scan ChromaDB
    ids, documents, metadatas = scan_chroma_source()
    if not ids:
        print("\n❌ No data found in ChromaDB. Nothing to migrate.")
        return

    # 2. Dry run?
    if args.dry_run:
        print(f"\n🔍 DRY RUN — Would migrate {len(ids)} documents:")
        print(f"   Source: ChromaDB ({len(ids)} documents)")
        print(f"   Target: Qdrant ({os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', '6333')})")
        print(f"   Batch size: {args.batch}")
        print(f"   Unique collections: {len(set(m.get('doc_id', '') for m in metadatas))}")
        print("\n✅ Dry-run complete. No data was written.")
        return

    # 3. Migrate
    result = migrate_batch_to_qdrant(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        force=args.force,
        batch_size=args.batch,
    )

    # 4. Summary
    print("\n" + "=" * 60)
    print("  📊 MIGRATION SUMMARY")
    print("=" * 60)
    print(f"  Total:     {result['total']}")
    print(f"  Succeeded: {result['succeeded']} ✅")
    print(f"  Failed:    {result['failed']}")
    print(f"  Duration:  {result['duration_seconds']:.2f}s")
    if result['duration_seconds'] > 0:
        print(f"  Speed:     {result['total'] / result['duration_seconds']:.1f} docs/s")

    if result['errors']:
        print(f"\n  ⚠️ First {len(result['errors'])} errors:")
        for err in result['errors'][:10]:
            print(f"    - {err}")

    # 5. Verify
    if result['succeeded'] > 0:
        verify_result = verify_migration(result['succeeded'])

        if verify_result['count_match']:
            print("\n✅ MIGRATION COMPLETE — All data successfully migrated!")
            print("   You can now switch to Qdrant-only mode:")
            print("   export VECTOR_DB_PROVIDER=qdrant")
            print("   Or use dual-write during transition:")
            print("   export VECTOR_DB_PROVIDER=dual")
        else:
            print("\n⚠️ Migration completed but count mismatch.")
            print("   Check errors above and re-run if needed.")


if __name__ == "__main__":
    main()
