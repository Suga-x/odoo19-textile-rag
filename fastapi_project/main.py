import os
import traceback
from fastapi import FastAPI, UploadFile, File, Form, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from config import settings
from schemas import QueryRequest, QueryResponse
from services.embedding import EmbeddingService
from services.llm import LLMService
from services.store_factory import get_vector_store, health_check_vector_store
from pydantic import BaseModel
from typing import Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from tasks import task_ingest_sop_textile, task_query_sop
from ingest_sop import search_relevant_documents

# Initialize vector store via factory (Qdrant/Chroma/Dual based on VECTOR_DB_PROVIDER)
vector_store = get_vector_store()


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
    Dynamically fetch corpus from vector store for BM25,
    then merge with Vector Search.
    """
    try:
        filter_metadata = {"division": division} if division else {}

        # 1. Fetch documents from vector store dynamically
        all_ids, corpus_texts, metadatas = vector_store.get_all(filter_metadata=filter_metadata)

        # Compute query embedding first so dimensions are consistent (768)
        query_embedding = EmbeddingService.get_embedding(question)

        # Anticipate empty vector store
        if not corpus_texts:
            print(" [HYBRID] Vector store corpus is empty. Falling back to Vector Search only.")
            vector_results = vector_store.query(query_embedding=query_embedding, n_results=1)
            return vector_results[0]['document'] if vector_results else "SOP not found."

        # 2. INITIALIZE BM25 LIVE BASED ON DB CONTENT
        tokenized_corpus = [doc.lower().split(" ") for doc in corpus_texts]
        bm25 = BM25Okapi(tokenized_corpus)

        # 3. RUN KEYWORD SEARCH (BM25)
        tokenized_query = question.lower().split(" ")
        bm25_best_docs = bm25.get_top_n(tokenized_query, corpus_texts, n=1)
        keyword_result = bm25_best_docs[0] if bm25_best_docs else ""

        # 4. RUN VECTOR SEARCH (Qdrant/Chroma)
        vector_results = vector_store.query(
            query_embedding=query_embedding,
            n_results=1,
            filter_metadata=filter_metadata
        )
        vector_result = vector_results[0]['document'] if vector_results else ""

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

        print(" [RETRIEVER] Vector path: Using semantic proximity.")
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

    # 2. Search SOP documents from vector store
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

        # LAYER 2: VECTOR DATABASE PROCESSING WITH SAFE-GUARD
        try:
            query_embedding = EmbeddingService.get_embedding(clean_question)
        except Exception as embed_err:
            print(f" Failed to compute query embedding: {str(embed_err)}")
            raise HTTPException(status_code=500, detail="Failed to interpret question intent.")

        search_filter = {}
        if request.division:
            search_filter = {"division": request.division}

        results = vector_store.query(
            query_embedding=query_embedding,
            n_results=3,
            filter_metadata=search_filter
        )

        retrieved_documents = [r['document'] for r in results]
        retrieved_metadatas = [r['metadata'] for r in results]
        retrieved_scores = [r.get('score', 0.0) for r in results]

        # LAYER 3: SCORE THRESHOLD GUARDRAIL (Relevance Check)
        # Qdrant uses COSINE similarity (0-1, higher = more similar)
        # If score is below 0.3, the vector store has no matching SOP data
        if not retrieved_documents or (len(retrieved_scores) > 0 and retrieved_scores[0] < 0.3):
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

        # 2. Perform retrieval to vector store
        result = vector_store.query(query_embedding=query_vector, n_results=1)

        if not result or not result[0]['document']:
            raise HTTPException(status_code=404, detail="Relevant Textile SOP not found.")

        best_document = result[0]['document']
        vector_score = result[0].get('score', 0.0)
        THRESHOLD_LIMIT = 0.3  # Qdrant COSINE: higher is more similar, below 0.3 = irrelevant

        if vector_score < THRESHOLD_LIMIT:
            return QueryResponse(
                question=request.question,
                retrieved_sop="DOCUMENT BELOW SAFETY THRESHOLD",
                vector_distance=vector_score,
                ai_answer="Sorry, your question cannot be answered because the topic is outside the scope of the official Factory SOP documents."
            )

        # 4. If guard passes, send to LLM Service for answer synthesis
        ai_answer = LLMService.generate_rag_answer(request.question, best_document)

        return QueryResponse(
            question=request.question,
            retrieved_sop=best_document,
            vector_distance=vector_score,
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

        # 3. Fetch 3 nearest chunks from vector store with metadata
        results = vector_store.query(
            query_embedding=query_embedding,
            n_results=3,
            filter_metadata=search_filter
        )

        retrieved_documents = [r['document'] for r in results]
        retrieved_metadatas = [r['metadata'] for r in results]

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

        # 5. Inject directly into vector store in real-time
        vector_store.upsert(
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
    RAG Endpoint: Search for relevant SOP chunks in vector store (Retrieval),
    filter by score threshold, then pass to LLM for answer generation.
    """
    try:
        if not query.strip():
            raise HTTPException(status_code=400, detail="Search query cannot be empty.")

        # 1. RETRIEVAL: Fetch data from vector store
        search_results = search_relevant_documents(query_text=query, division_filter=division)

        if "error" in search_results:
            raise HTTPException(status_code=500, detail=search_results["error"])

        # 2. FILTERING: Apply relative score threshold (pick top 3 closest)
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


@app.post("/api/v1/query/async", tags=["Core RAG Engine V1"])
async def query_rag_async(question: str, division: str = None, session_id: str = None):
    """
    🟢 HIGH PRIORITY QUEUE — Query RAG secara asinkron via Celery.
    
    Endpoint ini dispatch task ke 'high_priority' queue agar diproses
    oleh worker khusus real-time. Cocok untuk request dari operator pabrik
    yang membutuhkan respons cepat.

    Returns:
        HTTP 202 Accepted dengan task_id untuk polling status.
    """
    try:
        if not question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty.")

        # Dispatch ke Celery high_priority queue
        task = task_query_sop.delay(
            question=question,
            division=division,
            session_id=session_id
        )

        return JSONResponse(
            status_code=202,
            content={
                "message": "Query is being processed in the high-priority queue.",
                "task_id": str(task.id),
                "queue": "high_priority",
                "poll_url": f"/api/v1/task/{task.id}"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch query: {str(e)}")


@app.get("/api/v1/task/{task_id}", tags=["Core RAG Engine V1"])
async def get_task_result(task_id: str):
    """
    Polling endpoint untuk mengecek hasil task Celery.
    Dipanggil setelah /api/v1/query/async untuk mengambil hasil query.
    """
    from celery.result import AsyncResult
    from celery_app import celery_app

    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.pending:
        return {
            "status": "pending",
            "message": "Task is still being processed in the queue."
        }
    elif task_result.failed():
        return {
            "status": "failed",
            "message": str(task_result.info) if task_result.info else "Task failed without details."
        }
    elif task_result.successful():
        return {
            "status": "success",
            "result": task_result.result
        }

    return {
        "status": "unknown",
        "message": "Task status could not be determined."
    }


@app.get("/api/sops", status_code=status.HTTP_200_OK, tags=["Administrative Engine"])
async def get_registered_sops_list():
    try:
        # Fetch all documents from vector store
        all_ids, all_documents, all_metadatas = vector_store.get_all()

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
    health_status = health_check_vector_store(vector_store)
    return {
        "status": "healthy",
        "vector_store": health_status
    }


@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/docs")
