import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

# 1. Resolve path according to env or main.py defaults
CHROMA_DATA_PATH = os.getenv("CHROMA_DATA_PATH", "./chroma_db")
print(f"Checking database location at: {os.path.abspath(CHROMA_DATA_PATH)}")

try:
    # 2. Connect to persistent client
    chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)

    # 3. List existing collections in the database
    collections = chroma_client.list_collections()
    print(f"Number of collections found: {len(collections)}")

    for col in collections:
        print(f"\n--- Collection: {col.name} ---")

        # Grab a data sample to inspect its structure
        collection = chroma_client.get_collection(name=col.name)
        total_docs = collection.count()
        print(f"Total documents in collection: {total_docs}")

        if total_docs > 0:
            # Fetch 1 sample document for metadata inspection
            sample = collection.get(limit=1)
            print("Sample Metadata Structure:")
            print(sample.get("metadatas", [{}])[0])
            print("Sample Document Text Excerpt:")
            print(sample.get("documents", [""])[0][:150] + "...")
        else:
            print("This collection is empty. No data has been ingested yet.")

except Exception as e:
    print(f"Failed to read ChromaDB configuration: {str(e)}")
