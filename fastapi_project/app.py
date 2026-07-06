import os
import shutil
import chromadb
import ollama
from dotenv import load_dotenv

# Local database path
DB_PATH = "chroma_storage_local"

# 1. HARD RESET DATABASE (Ensures fresh index for local embedding)
if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)

print("[-] Initializing Local ChromaDB on Mac...")
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.create_collection(name="sop_pabrik_tekstil_local")

# 2. READ RAW SOP DATA
path_sop = os.path.join("knowledge_base", "sop_celup_polyester.txt")
try:
    with open(path_sop, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
except FileNotFoundError:
    print(f"[Error]: File {path_sop} does not exist. Please ensure the SOP file is available!")
    exit(1)

# ======================================================================
# LOCAL EMBEDDING FUNCTION VIA OLLAMA (NOMIC EMBED)
# ======================================================================
def get_local_embedding(text: str) -> list[float]:
    """Convert text into a vector using a dedicated embedding model"""
    response = ollama.embeddings(
        model='nomic-embed-text',
        prompt=text
    )
    return response['embedding']
# ======================================================================

print(f"[-] Transforming {len(lines)} documents into vectors via Ollama...")
documents, ids, metadatas, embeddings = [], [], [], []

for index, text in enumerate(lines):
    # Call the new get_local_embedding function
    vector = get_local_embedding(text)

    embeddings.append(vector)
    documents.append(text)
    ids.append(f"id_sop_{index+1}")
    metadatas.append({"source": "sop_celup_polyester.txt", "engine": "nomic-embed"})

# Store pure data and vectors into ChromaDB
collection.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
print(f"[Local Vector Database Built Successfully! (Dimension: {len(embeddings[0])})")

# 3. LOCAL SEMANTIC SEARCH PROCESS
query_user = "What is the safe temperature for synthetic textile?"
print(f"\n[User Question]: '{query_user}'")

print("[-] Converting query to vector via local Ollama...")
query_vector = get_local_embedding(query_user)

print("[-] Computing semantic proximity in local memory...")
result = collection.query(query_embeddings=[query_vector], n_results=1)

best_document = result['documents'][0][0]
vector_distance = result['distances'][0][0]
print(f"[Nearest SOP Found (Distance: {vector_distance:.4f}):\n    \"{best_document}\"")

# 4. ANSWER GENERATION VIA LOCAL OLLAMA QWEN 2.5 CODER 14B
print("\n[-] Requesting local Qwen 2.5 Coder 14B to summarize the answer...")

prompt_rag = f"""
You are a Textile RAG system expert. Answer the user's question tactically, concisely, and professionally
based ONLY on the facts from the provided SOP document. Do not assume anything outside the text!

[SOP FACTORY DOCUMENT]:
{best_document}

[USER QUESTION]:
{query_user}

Your Final Answer (English):
"""

try:
    response_ollama = ollama.generate(model='qwen2.5-coder:14b', prompt=prompt_rag)
    print("\n" + "="*20 + " QWEN 2.5 LOCAL RESPONSE " + "="*20)
    print(response_ollama['response'].strip())
    print("="*64)
except Exception as e:
    print(f"[Ollama Error]: Local computation failed. Detail: {e}")
