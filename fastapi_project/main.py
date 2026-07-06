import os
import chromadb
import traceback
from chromadb.utils import embedding_functions
from fastapi import FastAPI, UploadFile, File, Form, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from config import settings
from schemas import QueryRequest, QueryResponse
from services.embedding import EmbeddingService
from services.llm import LLMService
from pydantic import BaseModel
from typing import Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from tasks import task_ingest_sop_textile
from ingest_sop import search_relevant_documents

chroma_client = chromadb.PersistentClient(path=settings.DB_PATH)
collection = chroma_client.get_or_create_collection(name=settings.COLLECTION_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="100% Local Textile RAG System with Clean Architecture"
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploaded_files")
os.makedirs(UPLOAD_DIR, exist_ok=True)

chat_sessions: Dict[str, list[Dict[str, str]]] = {}


class QueryRequest(BaseModel):
    question: str
    division: str | None = None
    session_id: str | None = None


def get_hybrid_search(question: str, division: Optional[str] = None) -> str:
    """
    Dynamically fetch corpus from ChromaDB for BM25,
    then merge with Vector Search.
    """
    try:
        filter_metadata = {"division": division} if division else {}

        # 1. Fetch documents from ChromaDB dynamically
        all_docs = collection.get(where=filter_metadata)

        corpus_texts = all_docs.get('documents', [])
        metadatas = all_docs.get('metadatas', [])

        # Compute query embedding first so dimensions are consistent (768)
        query_embedding = EmbeddingService.get_embedding(question)

        # Anticipate empty ChromaDB
        if not corpus_texts:
            print(" [HYBRID] ChromaDB corpus is empty. Falling back to Vector Search only.")
            vector_results = collection.query(query_embeddings=[query_embedding], n_results=1)
            return vector_results['documents'][0][0] if vector_results['documents'] else "SOP not found."

        # 2. INITIALIZE BM25 LIVE BASED ON DB CONTENT
        tokenized_corpus = [doc.lower().split(" ") for doc in corpus_texts]
        bm25 = BM25Okapi(tokenized_corpus)

        # 3. RUN KEYWORD SEARCH (BM25)
        tokenized_query = question.lower().split(" ")
        bm25_best_docs = bm25.get_top_n(tokenized_query, corpus_texts, n=1)
        keyword_result = bm25_best_docs[0] if bm25_best_docs else ""

        # 4. RUN VECTOR SEARCH (CHROMADB)
        vector_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=1,
            where=filter_metadata
        )
        vector_result = vector_results['documents'][0][0] if vector_results['documents'] else ""

        # 5. RERANKING / MERGE STRATEGY
        has_exact_code = False
        if metadatas:
            for meta in metadatas:
                doc_code = meta.get("sop_code", "")
                if doc_code and doc_code.upper() in question.upper():
                    has_exact_code = True
                    break

        if has_exact_code and keyword_result:
            print(" [RETRIEVER] BM25 path: Successfully matched exact keyword code.")
            return keyword_result

        print(" [RETRIEVER] Vector path: Using ChromaDB semantic proximity.")
        return vector_result if vector_result else keyword_result

    except Exception as e:
        print(f" [HYBRID ERROR] Hybrid search failed: {str(e)}")
        return "Failed to process SOP document search."


@app.post("/api/query/history", tags=["Core RAG Engine"])
async def query_rag_engine_history(payload: QueryRequest):
    question = payload.question
    session_id = payload.session_id
    division = payload.division

    # 1. Get or create history for this session_id
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    current_history = chat_sessions[session_id]

    # 2. Search SOP documents from ChromaDB
    retrieved_docs = get_hybrid_search(question=question, division=division)

    # 3. Call dynamic LiteLLM service with chat history
    ai_response = LLMService.generate_rag_answer_history(
        question=question,
        retrieved_sop=retrieved_docs,
        history=current_history
    )

    # 4. SAVE NEW CONVERSATION INTO SESSION HISTORY
    chat_sessions[session_id].append({"role": "Operator", "content": question})
    chat_sessions[session_id].append({"role": "AI", "content": ai_response})

    return {
        "status": "success",
        "answer": ai_response
    }


@app.post("/api/query/guards", status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def query_rag_system_guards(request: QueryRequest):
    try:
        # LAYER 1: PRE-FILTER GUARDRAIL (Input Cleaning)
        clean_question = request.question.strip()

        # Limit character length to prevent text overload attacks (max 300 chars)
        if len(clean_question) > 300:
            return {
                "status": "rejected",
                "answer": "<b>System Warning:</b> Question is too long (Maximum 300 characters). Please shorten your question.",
                "chunks_used": 0
            }

        # Block dangerous regex/special characters
        forbidden_chars = ["#", "DROP TABLE", "SELECT", "INSERT", "DELETE", "html", "<script>"]
        if any(keyword in clean_question.upper() for keyword in forbidden_chars):
            return {
                "status": "rejected",
                "answer": "<b>System Warning:</b> Your question contains forbidden symbols or database instructions.",
                "chunks_used": 0
            }

        # LAYER 2: DATABASE PROCESSING (CHROMADB) WITH SAFE-GUARD
        try:
            query_embedding = EmbeddingService.get_embedding(clean_question)
        except Exception as embed_err:
            print(f" Failed to compute query embedding: {str(embed_err)}")
            raise HTTPException(status_code=500, detail="Failed to interpret question intent.")

        search_filter = {}
        if request.division:
            search_filter = {"division": request.division}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            where=search_filter
        )

        retrieved_documents = results.get("documents", [[]])[0]
        retrieved_metadatas = results.get("metadatas", [[]])[0]
        retrieved_distances = results.get("distances", [[]])[0]

        # LAYER 3: DISTANCE THRESHOLD GUARDRAIL (Relevance Check)
        # If vector distance is above 1.2, the database has no matching SOP data
        if not retrieved_documents or (len(retrieved_distances) > 0 and retrieved_distances[0] > 1.2):
            return {
                "status": "out_of_scope",
                "answer": "<b>Factory AI System:</b> Sorry, information about this topic is not covered in the official SOP documents for your division.",
                "chunks_used": 0
            }

        # CONTEXT STRUCTURING XML (Runs if all guardrails pass)
        context_blocks = []
        for index, (doc_text, metadata) in enumerate(zip(retrieved_documents, retrieved_metadatas)):
            sop_code = metadata.get("sop_code", "UNKNOWN")
            division = metadata.get("division", "UNKNOWN")

            block = (
                f"<Reference_SOP_Document index='{index+1}'>\n"
                f"  <SOP_Code>{sop_code}</SOP_Code>\n"
                f"  <Related_Division>{division}</Related_Division>\n"
                f"  <Work_Instruction_Content>\n{doc_text}\n  </Work_Instruction_Content>\n"
                f"</Reference_SOP_Document>"
            )
            context_blocks.append(block)

        context_sop = "\n\n".join(context_blocks)

        # EXECUTE GENERATION (With internal LLMService protection)
        ai_response_html = LLMService.generate_rag_answer(
            question=clean_question,
            retrieved_sop=context_sop
        )

        # Clean leftover newlines for compact HTML
        ai_response_html = ai_response_html.replace("\n", "").strip()

        return {
            "status": "success",
            "answer": ai_response_html,
            "chunks_used": len(retrieved_documents)
        }

    except Exception as fatal_err:
        # Final Safety Net: If any strange scenario slips through, don't throw HTTP 500 to Odoo
        print(f" CRITICAL ERROR ON QUERY: {str(fatal_err)}")
        return {
            "status": "system_error",
            "answer": "<b>Internal System Error:</b> An issue occurred while processing the answer. Please try again later or contact IT.",
            "chunks_used": 0
        }


@app.post("/api/query/ask", response_model=QueryResponse, status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def ask_sop(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # 1. Get vector representation of the question (consistent with EmbeddingService)
        query_vector = EmbeddingService.get_embedding(request.question)

        # 2. Perform retrieval to ChromaDB
        result = collection.query(query_embeddings=[query_vector], n_results=1)

        if not result['documents'] or not result['documents'][0]:
            raise HTTPException(status_code=404, detail="Relevant Textile SOP not found.")

        best_document = result['documents'][0][0]
        vector_distance = result['distances'][0][0]
        THRESHOLD_LIMIT = 260.0

        if vector_distance > THRESHOLD_LIMIT:
            return QueryResponse(
                question=request.question,
                retrieved_sop="DOCUMENT BELOW SAFETY THRESHOLD",
                vector_distance=vector_distance,
                ai_answer="Sorry, your question cannot be answered because the topic is outside the scope of the official Factory SOP documents."
            )

        # 4. If guard passes, send to LLM Service for answer synthesis
        ai_answer = LLMService.generate_rag_answer(request.question, best_document)

        return QueryResponse(
            question=request.question,
            retrieved_sop=best_document,
            vector_distance=vector_distance,
            ai_answer=ai_answer
        )

    except RuntimeError as service_error:
        raise HTTPException(status_code=502, detail=str(service_error))
    except Exception as general_error:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(general_error)}")


@app.post("/api/query", status_code=status.HTTP_200_OK, tags=["Core RAG Engine"])
async def query_rag_system(request: QueryRequest):
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty.")

        # 1. Compute embedding from operator question
        query_embedding = EmbeddingService.get_embedding(request.question)

        # 2. Optional filter by operator division
        search_filter = {}
        if request.division:
            search_filter = {"division": request.division}

        # 3. Fetch 3 nearest chunks from ChromaDB with metadata
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            where=search_filter
        )

        retrieved_documents = results.get("documents", [[]])[0]
        retrieved_metadatas = results.get("metadatas", [[]])[0]

        # 4. CONTEXT STRUCTURING TECHNIQUE (Convert to structured XML format)
        context_blocks = []

        if not retrieved_documents:
            context_sop = "WARNING: No official SOP documents found in the database for this question."
        else:
            for index, (doc_text, metadata) in enumerate(zip(retrieved_documents, retrieved_metadatas)):
                sop_code = metadata.get("sop_code", "UNKNOWN")
                division = metadata.get("division", "UNKNOWN")

                # Wrap text with structured tags for instant LLM comprehension
                block = (
                    f"<Reference_SOP_Document index='{index+1}'>\n"
                    f"  <SOP_Code>{sop_code}</SOP_Code>\n"
                    f"  <Related_Division>{division}</Related_Division>\n"
                    f"  <Work_Instruction_Content>\n{doc_text}\n  </Work_Instruction_Content>\n"
                    f"</Reference_SOP_Document>"
                )
                context_blocks.append(block)

            # Combine all blocks into a single large string
            context_sop = "\n\n".join(context_blocks)

        # 5. Send structured context to LLM Service
        ai_response_html = LLMService.generate_rag_answer(
            question=request.question,
            retrieved_sop=context_sop
        )

        return {
            "status": "success",
            "question": request.question,
            "answer": ai_response_html,
            "chunks_used": len(retrieved_documents)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process RAG: {str(e)}")


@app.post("/api/ingest", status_code=status.HTTP_201_CREATED, tags=["Core RAG Engine"])
async def ingest_document_file(sop_code: str = Form(...), division: str = Form(...), file: UploadFile = File(...)):
    try:
        # 1. Read uploaded file content
        file_content = await file.read()

        # 2. Extract text (example for clean .txt files)
        # To support PDF in the future, use 'pypdf' library here
        raw_text = file_content.decode("utf-8")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            add_start_index=True,
        )
        # 3. Run Smart LangChain Chunking
        chunks = text_splitter.split_text(raw_text)

        if not chunks:
            raise HTTPException(status_code=400, detail="File is empty or could not be extracted.")

        final_documents = []
        final_metadatas = []
        final_ids = []

        # 4. Use your Embedding Service to process each chunk
        for chunk_index, chunk_text in enumerate(chunks):
            final_documents.append(chunk_text)
            final_metadatas.append({
                "sop_code": sop_code,
                "division": division
            })
            final_ids.append(f"{sop_code}_chunk_{chunk_index}")
        final_embeddings = [EmbeddingService.get_embedding(text) for text in final_documents]

        # 5. Inject directly into ChromaDB in real-time
        collection.upsert(
            ids=final_ids,
            documents=final_documents,
            metadatas=final_metadatas,
            embeddings=final_embeddings
        )

        return {
            "status": "success",
            "message": f"Successfully processed SOP {sop_code}. {len(final_ids)} new chunks stored."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


@app.post("/api/v1/ingest", tags=["Core RAG Engine V1"])
async def ingest_sop_endpoint(file: UploadFile = File(...)):
    try:
        # 1. Validate file format
        if not file.filename.endswith('.txt'):
            raise HTTPException(status_code=400, detail="Only plain text (.txt) files are supported.")

        file_path = os.path.join(UPLOAD_DIR, file.filename)

        # 2. Safely save the physical file
        contents = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(contents)

        # Pure primitive-typed metadata (safe for Celery JSON serialization)
        metadata = {
            "source_file": str(file.filename),
            "industry": "textile-dyeing"
        }

        # 3. Dispatch to Celery Worker
        task = task_ingest_sop_textile.delay(file_path, metadata)

        return JSONResponse(
            status_code=202,
            content={
                "message": "SOP document received and is being processed in the background.",
                "task_id": str(task.id),
                "registration_status": "Queued/Processing"
            }
        )
    except Exception as e:
        # Print original error details to Docker terminal logs for debugging
        print("=== CRITICAL API ERROR ===")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to register task: {str(e)}"}
        )


@app.post("/api/v1/query", tags=["Core RAG Engine V1"])
async def query_rag_endpoint(query: str, division: str = None):
    """
    RAG Endpoint: Search for relevant SOP chunks in ChromaDB (Retrieval),
    filter by distance threshold, then pass to LLM for answer generation.
    """
    try:
        if not query.strip():
            raise HTTPException(status_code=400, detail="Search query cannot be empty.")

        # 1. RETRIEVAL: Fetch data from ChromaDB
        search_results = search_relevant_documents(query_text=query, division_filter=division)

        if "error" in search_results:
            raise HTTPException(status_code=500, detail=search_results["error"])

        # 2. FILTERING: Apply relative distance threshold (pick top 3 closest)
        # ChromaDB uses L2 distance by default (all-MiniLM-L6-v2, 384-dim).
        # We pick the top 3 results; they are already sorted by distance ascending.
        valid_contexts = search_results[:3]

        # 3. GENERATION: Send to LLM if valid context passed the filter
        if not valid_contexts:
            ai_answer = (
                "Sorry, no sufficiently relevant SOP document information is available "
                "in the database to answer your question."
            )
        else:
            ai_answer = LLMService.generate_from_context_list(
                query=query, context_list=valid_contexts
            )

        return JSONResponse(
            status_code=200,
            content={
                "query": query,
                "division_filter": division if division else "All Divisions",
                "ai_answer": ai_answer,
                "total_context_used": len(valid_contexts),
                "source_documents": [doc["id"] for doc in valid_contexts]
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process RAG pipeline: {str(e)}")

@app.get("/api/sops", status_code=status.HTTP_200_OK, tags=["Administrative Engine"])
async def get_registered_sops_list():
    try:
        # 1. EXPLICITLY INITIALIZE INSTANCE TO SYNC WITH INGEST_SOP.PY
        db_path = os.path.join(os.path.dirname(__file__), "chroma_db_storage")
        chroma_client = chromadb.PersistentClient(path=db_path)
        embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        # Ensure collection name matches the one in ingest_sop.py
        target_collection = chroma_client.get_or_create_collection(
            name="textile_sop_collection",
            embedding_function=embedding_fn
        )

        # Fetch data from the correct collection
        db_content = target_collection.get(include=["metadatas", "documents"])
        all_metadatas = db_content.get("metadatas", [])
        all_documents = db_content.get("documents", [])

        if not all_metadatas:
            return {
                "status": "success",
                "message": "No SOP documents are registered in the system yet.",
                "total_sops": 0,
                "sops": []
            }

        # 2. Deduplicate (using adaptive code)
        unique_sops = {}
        for i, meta in enumerate(all_metadatas):
            if meta:
                code = meta.get("sop_code") or meta.get("doc_id")
                if not code:
                    continue

                doc_text = all_documents[i] if i < len(all_documents) else ""

                if code not in unique_sops:
                    unique_sops[code] = {
                        "sop_code": code,
                        "division": meta.get("division") or meta.get("divisi") or "UNKNOWN",
                        "content": ""
                    }
                if doc_text:
                    unique_sops[code]["content"] += doc_text.strip() + "\n\n"

        # 3. Clean trailing newlines
        for sop in unique_sops.values():
            sop_content = sop["content"].strip()
            sop["content"] = sop_content

        # 4. Convert to clean JSON array format
        sops_list = list(unique_sops.values())

        return {
            "status": "success",
            "total_sops": len(sops_list),
            "sops": sops_list
        }

    except Exception as e:
        print(f" [ERROR] Failed to fetch SOP list: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch SOP list from database: {str(e)}"
        )


@app.get("/api/health", tags=["System Utility"])
async def health_check():
    return {"status": "healthy"}


@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/docs")
