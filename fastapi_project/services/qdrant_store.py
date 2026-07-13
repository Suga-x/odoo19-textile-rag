# fastapi_project/services/qdrant_store.py
"""
Qdrant Vector Store Implementation.

Mengimplementasikan VectorStore interface untuk Qdrant.
Menggantikan ChromaDB sebagai production-grade vector database.

Fitur:
    - Collection management (create/recreate/delete)
    - Upsert dokumen dengan vector embedding + payload
    - Semantic search dengan payload filtering
    - Scroll API untuk listing memory-efficient
    - Payload indexing untuk filter cepat
    - Health check dengan retry
    - Dual-write ready (Phase 1 migration)

Dependencies:
    pip install qdrant-client
"""

import os
import time
import uuid
from typing import Optional

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

# Local
from .vector_store import VectorStore


# Default settings — bisa di-override via env vars
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")         # Di Docker = "qdrant"
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))         # REST API port
QDRANT_GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT", 6334))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sop_textile")
QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", 768))  # nomic-embed-text dimension
QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", 30))     # connection timeout


class QdrantStore(VectorStore):
    """
    Qdrant implementation dari VectorStore interface.

    Contoh penggunaan:
        store = QdrantStore()
        store.upsert(ids, documents, metadatas, embeddings)
        results = store.query(query_embedding, n_results=3, filter_metadata={"division": "Dyeing"})
    """

    def __init__(
        self,
        host: str = QDRANT_HOST,
        port: int = QDRANT_PORT,
        collection_name: str = QDRANT_COLLECTION,
        vector_size: int = QDRANT_VECTOR_SIZE,
        prefer_grpc: bool = False,
    ):
        """
        Inisialisasi Qdrant client.

        Args:
            host: Qdrant service hostname
            port: Qdrant REST API port (default: 6333)
            collection_name: Nama collection di Qdrant
            vector_size: Dimensi vector embedding (nomic-embed-text = 768)
            prefer_grpc: Gunakan gRPC instead of REST (lebih cepat)
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.vector_size = vector_size

        # Qdrant client connection — dengan timeout
        self.client = QdrantClient(
            host=host,
            port=port,
            grpc_port=QDRANT_GRPC_PORT,
            prefer_grpc=prefer_grpc,
            timeout=QDRANT_TIMEOUT,
        )

        # Auto-create collection jika belum ada
        self._ensure_collection()

        # Buat payload index untuk field yang sering difilter
        self._ensure_payload_indexes()

        print(f"[QDRANT] ✅ Connected to Qdrant at {host}:{port}, collection='{collection_name}'")

    # ------------------------------------------------------------------
    # PRIVATE: Collection & Index Management
    # ------------------------------------------------------------------

    def _ensure_collection(self):
        """
        Buat collection jika belum ada.
        Aman dipanggil berulang kali (idempotent).
        """
        collections = self.client.get_collections().collections
        existing_names = [c.name for c in collections]

        if self.collection_name not in existing_names:
            print(f"[QDRANT] Creating collection '{self.collection_name}' (size={self.vector_size})...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=self.vector_size,
                    distance=qdrant_models.Distance.COSINE,
                    # COSINE distance = normalized L2
                    # Sama dengan default ChromaDB
                ),
                # Optimization: HNSW config
                hnsw_config=qdrant_models.HnswConfigDiff(
                    m=32,               # More connections = better recall
                    ef_construct=200,   # Higher = more accurate but slower build
                    full_scan_threshold=10000,
                ),
                # Optimization: Scalar quantization untuk hemat memory
                quantization_config=qdrant_models.ScalarQuantization(
                    scalar=qdrant_models.ScalarQuantizationConfig(
                        type=qdrant_models.ScalarType.INT8,
                        always_ram=True,
                    ),
                ),
            )
            print(f"[QDRANT] ✅ Collection '{self.collection_name}' created successfully.")
        else:
            print(f"[QDRANT] Collection '{self.collection_name}' already exists.")

    def _ensure_payload_indexes(self):
        """
        Buat index untuk field payload yang sering difilter.

        Indexed fields:
            - division: keyword (filter pencarian per divisi)
            - sop_code: keyword (lookup SOP code)
            - doc_id:   keyword (grouping dokumen)
            - file_hash: keyword (idempotency)
        """
        index_configs = {
            "division": qdrant_models.PayloadSchemaType.KEYWORD,
            "sop_code": qdrant_models.PayloadSchemaType.KEYWORD,
            "doc_id": qdrant_models.PayloadSchemaType.KEYWORD,
            "file_hash": qdrant_models.PayloadSchemaType.KEYWORD,
        }

        for field, schema_type in index_configs.items():
            try:
                print(f"[QDRANT] Creating payload index on '{field}'...")
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_type=schema_type,
                )
            except Exception as e:
                # Index mungkin sudah ada — skip
                print(f"[QDRANT] Payload index '{field}' already exists or error: {e}")

        print(f"[QDRANT] ✅ Payload indexes created.")

    # ------------------------------------------------------------------
    # PUBLIC: VectorStore Interface Implementation
    # ------------------------------------------------------------------

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> bool:
        """
        Upsert dokumen ke Qdrant.

        Args:
            ids: List unique ID untuk setiap chunk
            documents: List teks chunk
            metadatas: List metadata dict
            embeddings: WAJIB — Qdrant tidak auto-compute embedding

        Returns:
            True jika sukses

        Raises:
            ValueError: Jika embeddings tidak disediakan
            ConnectionError: Jika Qdrant tidak reachable
        """
        if not embeddings or len(embeddings) == 0:
            raise ValueError(
                "[QDRANT] embeddings WAJIB disediakan. "
                "Gunakan EmbeddingService.get_embedding() sebelum upsert."
            )

        if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
            raise ValueError(
                f"[QDRANT] Mismatch input lengths: "
                f"ids={len(ids)}, docs={len(documents)}, "
                f"metas={len(metadatas)}, embeddings={len(embeddings)}"
            )

        # Konversi ke Qdrant PointStruct
        points = []
        for i in range(len(ids)):
            # Pastikan content ada di payload untuk retrieval nanti
            payload = dict(metadatas[i])
            payload["content"] = documents[i]  # Teks asli disimpan di payload

            # Gunakan deterministic integer ID dari hash string ID
            point_id = self._string_to_uuid(ids[i])

            points.append(
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=embeddings[i],  # Wajib: precomputed embedding
                    payload=payload,
                )
            )

        # Upsert ke Qdrant
        try:
            response = self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return response.status == qdrant_models.UpdateStatus.COMPLETED

        except Exception as e:
            print(f"[QDRANT] ❌ Upsert failed: {e}")
            raise ConnectionError(f"Failed to upsert to Qdrant: {e}")

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        Cari dokumen terdekat berdasarkan query embedding.

        Args:
            query_embedding: Vector embedding dari pertanyaan
            n_results: Jumlah hasil yang diminta
            filter_metadata: Optional filter dict
                           Contoh: {"division": "Dyeing"}
                           Untuk multi-filter: {"division": "Dyeing", "sop_code": "SOP-DYE-001"}

        Returns:
            List of dict dengan keys:
                id: str — ID chunk
                document: str — teks chunk
                metadata: dict — metadata chunk
                score: float — cosine similarity score (0-1, higher = more similar)
        """
        # Build Qdrant filter dari dict metadata
        qdrant_filter = None
        if filter_metadata and len(filter_metadata) > 0:
            must_conditions = []
            for key, value in filter_metadata.items():
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    )
                )
            qdrant_filter = qdrant_models.Filter(must=must_conditions)

        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=qdrant_filter,
                limit=n_results,
                with_payload=True,
                with_vectors=False,  # Tidak perlu return vector — hemat bandwidth
                score_threshold=0.0,  # Tidak ada minimum score
            )

            # Format hasil ke format standar
            formatted = []
            for point in results:
                payload = point.payload or {}
                content = payload.pop("content", "")  # Ambil content dari payload

                formatted.append({
                    "id": str(point.id),
                    "document": content,
                    "metadata": payload,  # Sisa payload setelah content di-pop
                    "score": point.score,
                })

            return formatted

        except Exception as e:
            print(f"[QDRANT] ❌ Query failed: {e}")
            raise ConnectionError(f"Failed to query Qdrant: {e}")

    def get_all(
        self,
        filter_metadata: Optional[dict] = None,
    ) -> tuple[list[str], list[str], list[dict]]:
        """
        Fetch semua dokumen — memory-efficient menggunakan Scroll API.

        Args:
            filter_metadata: Optional filter dict

        Returns:
            Tuple (ids, documents, metadatas)
        """
        all_ids = []
        all_documents = []
        all_metadatas = []

        # Build Qdrant filter
        qdrant_filter = None
        if filter_metadata and len(filter_metadata) > 0:
            must_conditions = []
            for key, value in filter_metadata.items():
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    )
                )
            qdrant_filter = qdrant_models.Filter(must=must_conditions)

        try:
            # Scroll API — pagination, tidak load semua ke memory
            next_page_token = None
            while True:
                records, next_page_token = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=qdrant_filter,
                    limit=500,  # 500 records per page
                    offset=next_page_token,
                    with_payload=True,
                    with_vectors=False,  # Tidak perlu vector
                )

                if not records:
                    break

                for point in records:
                    payload = point.payload or {}
                    content = payload.pop("content", "")

                    all_ids.append(str(point.id))
                    all_documents.append(content)
                    all_metadatas.append(payload)

                if not next_page_token:
                    break

            return all_ids, all_documents, all_metadatas

        except Exception as e:
            print(f"[QDRANT] ❌ get_all failed: {e}")
            raise ConnectionError(f"Failed to get_all from Qdrant: {e}")

    def delete(self, ids: list[str]) -> bool:
        """
        Hapus dokumen berdasarkan IDs.

        Args:
            ids: List ID string yang akan dihapus

        Returns:
            True jika sukses
        """
        try:
            point_ids = [self._string_to_uuid(pid) for pid in ids]
            response = self.client.delete(
                collection_name=self.collection_name,
                points_selector=qdrant_models.PointIdsList(
                    points=point_ids,
                ),
            )
            return response.status == qdrant_models.UpdateStatus.COMPLETED

        except Exception as e:
            print(f"[QDRANT] ❌ Delete failed: {e}")
            return False

    def count(self) -> int:
        """
        Hitung total dokumen di collection.

        Returns:
            Jumlah total dokumen
        """
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return collection_info.points_count or 0
        except Exception as e:
            print(f"[QDRANT] ❌ Count failed: {e}")
            return 0

    def health_check(self) -> bool:
        """
        Cek koneksi ke Qdrant.

        Returns:
            True jika terkoneksi
        """
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def delete_collection(self) -> bool:
        """
        Hapus seluruh collection — untuk reset testing.

        Returns:
            True jika sukses
        """
        try:
            self.client.delete_collection(self.collection_name)
            print(f"[QDRANT] 🗑️ Collection '{self.collection_name}' deleted.")
            # Re-create agar siap digunakan lagi
            self._ensure_collection()
            self._ensure_payload_indexes()
            return True
        except Exception as e:
            print(f"[QDRANT] ❌ delete_collection failed: {e}")
            return False

    # ------------------------------------------------------------------
    # PRIVATE: Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _string_to_uuid(string_id: str) -> str:
        """
        Konversi string ID ke UUID deterministik.
        Qdrant membutuhkan UUID atau integer untuk point ID.

        Args:
            string_id: e.g., "SOP-DYE-001_chunk_3"

        Returns:
            UUID string deterministik
        """
        # Gunakan UUID namespace-based (UUID v3/v5)
        # Konsisten: ID string yang sama → UUID yang sama
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, string_id))
