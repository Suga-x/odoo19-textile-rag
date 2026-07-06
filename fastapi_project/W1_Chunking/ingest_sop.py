import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Initialize Local ChromaDB Client
# (Adjust the directory path if you use a different persistent storage)
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Create or retrieve the existing collection
collection = chroma_client.get_or_create_collection(name="textile_sop")

# 2. Raw Master SOP Data with Metadata
raw_documents = [
    {
        "text": "SOP-03: To prevent polyester fabric from excessive shrinkage above 2%, the operator must set the stenter machine oven temperature between 180°C and 190°C. The fabric draw duration inside the oven must be consistently maintained between 30 to 45 seconds only.",
        "metadata": {"sop_code": "SOP-03", "division": "Finishing", "topic": "Stenter"}
    },
    {
        "text": "SOP-09: If damage to greige makloon fabric caused by the jet dyeing machine bursting or jamming exceeds 10 percent of the total order volume, the makloon factory is required to provide compensation equal to the value of the damaged raw greige fabric to the customer.",
        "metadata": {"sop_code": "SOP-09", "division": "Dyeing", "topic": "Compensation"}
    }
]

# 3. Smart LangChain Splitter Configuration
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=250,      # Smaller size for denser chunks per paragraph
    chunk_overlap=40,     # Context bridge between chunks
)

# 4. Execute Chunking and Data Packaging
final_documents = []
final_metadatas = []
final_ids = []

for index, doc in enumerate(raw_documents):
    # Split raw text into smaller parts
    chunks = text_splitter.split_text(doc["text"])

    for chunk_index, chunk_text in enumerate(chunks):
        final_documents.append(chunk_text)

        # Attach original metadata to each chunk
        final_metadatas.append(doc["metadata"])

        # Create unique chunk ID (e.g., SOP-03_chunk_0)
        sop_code = doc["metadata"]["sop_code"]
        final_ids.append(f"{sop_code}_chunk_{chunk_index}")

# 5. Inject Clean Data into ChromaDB
collection.upsert(
    ids=final_ids,
    documents=final_documents,
    metadatas=final_metadatas
)

print("DATA INGESTION SUCCESSFUL!")
print(f"Successfully processed and stored {len(final_ids)} smart chunks into ChromaDB.")
for idx, cid in enumerate(final_ids):
    print(f" -> Created ID: {cid} | Division: {final_metadatas[idx]['division']}")
