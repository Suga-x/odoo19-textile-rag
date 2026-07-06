# fastapi_project/ingest_sop.py
import os
import re
import chromadb
from chromadb.utils import embedding_functions

def extract_and_embed_document(file_path, metadata_input=None):
    print(f"\n[RAG Engine] Reading physical file from path: {file_path}")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at location: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        text_content = f.read()

    # 1. SEMANTIC CHUNKING STRATEGY (Split by Division Sections)
    # Split document based on '---' markers or DIVISION keywords
    sections = re.split(r'-{3,}', text_content)
    chunks = []
    metadatas = []

    # Extract main document header if present
    doc_id_match = re.search(r'ID_DOKUMEN:\s*(\S+)', text_content)
    doc_id = doc_id_match.group(1) if doc_id_match else "SOP-GENERIC"

    for idx, section in enumerate(sections):
        cleaned_section = section.strip()
        if not cleaned_section or "DOKUMEN STANDARD OPERATING" in cleaned_section:
            continue

        
        division = "General"
        if "DYEING" in cleaned_section.upper():
            division = "Dyeing"
        elif "FINISHING" in cleaned_section.upper():
            division = "Finishing"
        elif "LAB-WARNA" in cleaned_section.upper() or "LABORATORIUM" in cleaned_section.upper():
            division = "Lab-Warna"
        elif "IOT" in cleaned_section.upper():
            division = "IoT-Engineering"
        elif "MAINTENANCE" in cleaned_section.upper():
            division = "Maintenance"

        chunks.append(cleaned_section)
        metadatas.append({
            "doc_id": doc_id,
            "chunk_index": idx,
            "division": division,
            "industry": metadata_input.get("industry", "textile") if metadata_input else "textile"
        })

    if not chunks:
        print("[RAG Engine] Warning: No valid chunks were extracted.")
        return False

    # 2. INITIALIZE CHROMADB (Using Persistent Client so data persists)
    # Data directory will be stored at /app/chroma_data_storage inside the container
    db_path = os.path.join(os.path.dirname(__file__), "chroma_db_storage")
    chroma_client = chromadb.PersistentClient(path=db_path)

    # Use ChromaDB's built-in embedding model (all-MiniLM-L6-v2) - lightweight & fast
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()

    collection = chroma_client.get_or_create_collection(
        name="textile_sop_collection",
        embedding_function=embedding_fn
    )

    # 3. UPSERT DATA INTO VECTOR DATABASE
    # Create unique ID for each chunk
    ids = [f"{doc_id}_chunk_{m['chunk_index']}" for m in metadatas]

    collection.upsert(
        documents=chunks,
        metadatas=metadatas,
        ids=ids
    )

    print("DATA INGESTION SUCCESSFUL!")
    print(f"Successfully processed and stored {len(chunks)} smart chunks into ChromaDB.")
    for idx, m in enumerate(metadatas):
        print(f"  -> Created ID: {ids[idx]} | Division: {m['division']}")

    return True


def search_relevant_documents(query_text, division_filter=None, n_results=5):
    """
    Perform similarity search on ChromaDB based on user query.
    Can be filtered by division (Dyeing/Finishing) to narrow context.
    """
    import os
    db_path = os.path.join(os.path.dirname(__file__), "chroma_db_storage")

    if not os.path.exists(db_path):
        return {"error": "Vector database has not been built. Please ingest documents first."}

    chroma_client = chromadb.PersistentClient(path=db_path)
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()

    collection = chroma_client.get_collection(
        name="textile_sop_collection",
        embedding_function=embedding_fn
    )

    # Build metadata filter if division_filter parameter is provided
    where_clause = {}
    if division_filter:
        where_clause = {"division": division_filter}

    # Perform vector similarity search (Cosine/L2 distance)
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where=where_clause if where_clause else None
    )

    # Format results for easy consumption by API endpoints
    formatted_results = []
    if results and results['documents']:
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "id": results['ids'][0][i],
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i] if 'distances' in results else None
            })

    return formatted_results


# Auto-trigger if script is run directly via CLI/Subprocess
if __name__ == "__main__":
    import sys
    target_file = sys.argv[1] if len(sys.argv) > 1 else None

    # If no argument, look for default file for internal testing
    if not target_file:
        uploaded_dir = os.path.join(os.path.dirname(__file__), "uploaded_files")
        if os.path.exists(uploaded_dir):
            files = [os.path.join(uploaded_dir, f) for f in os.listdir(uploaded_dir) if f.endswith('.txt')]
            if files:
                target_file = files[0]  # Pick the first file in the upload folder

    if target_file:
        extract_and_embed_document(target_file, {"industry": "textile-dyeing"})
    else:
        print("[RAG Engine] Ready. No files have been provided yet.")
