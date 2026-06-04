"""
FastAPI Application — REST API for Architecture Knowledge Assistant
=====================================================================

ENDPOINTS:
    GET  /health   → Is the API running?
    POST /ingest   → Trigger document ingestion
    POST /query    → Ask a question, get an answer
    GET  /stats    → Index statistics
    GET  /clients  → List available clients

RUNNING:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI App ──
app = FastAPI(
    title="Architecture Knowledge Assistant",
    description="RAG-powered API for querying architecture documentation.",
    version="1.0.0",
)

# ── CORS (allow Streamlit on port 8501 to call this API) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Your question")
    client: Optional[str] = Field(None, description="Optional client filter")


class QueryResponseModel(BaseModel):
    answer: str
    sources: list
    retrieval_count: int
    intent: str
    client_detected: Optional[str]
    tokens_used: dict
    processing_time: float


class IngestResponseModel(BaseModel):
    files_processed: int
    files_skipped: int
    chunks_created: int
    errors: list
    processing_time: float
    details: list


class StatsResponseModel(BaseModel):
    total_chunks: int
    unique_clients: int
    unique_files: int
    clients: list
    files: list
    section_types: list


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


# ── Lazy Pipeline Initialization ──
# We don't create pipelines at import time because:
# 1. .env might not be configured yet
# 2. ChromaDB might not have data yet
# 3. Faster startup for health checks

_query_pipeline = None


def _get_query_pipeline():
    global _query_pipeline
    if _query_pipeline is None:
        from src.pipeline.query_pipeline import QueryPipeline
        _query_pipeline = QueryPipeline()
    return _query_pipeline


# ── Endpoints ──

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check — always returns healthy if API is running."""
    return HealthResponse(
        status="healthy",
        service="Architecture Knowledge Assistant",
        version="1.0.0",
    )


@app.post("/ingest", response_model=IngestResponseModel)
async def ingest_documents():
    """
    Trigger full document ingestion.
    Scans documents folder, extracts, chunks, and indexes everything.
    Idempotent — safe to run multiple times.
    """
    try:
        from src.pipeline.ingest_pipeline import IngestionPipeline
        pipeline = IngestionPipeline()
        report = pipeline.run()

        return IngestResponseModel(
            files_processed=report.files_processed,
            files_skipped=report.files_skipped,
            chunks_created=report.chunks_created,
            errors=report.errors,
            processing_time=report.processing_time,
            details=report.details,
        )
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponseModel)
async def query_documents(request: QueryRequest):
    """
    Ask a question about architecture documents.
    Auto-detects client and intent from the question.
    """
    try:
        pipeline = _get_query_pipeline()
        response = pipeline.ask(
            question=request.question,
            client_filter=request.client,
        )

        return QueryResponseModel(
            answer=response.answer,
            sources=response.sources,
            retrieval_count=response.retrieval_count,
            intent=response.intent,
            client_detected=response.client_detected,
            tokens_used=response.tokens_used,
            processing_time=response.processing_time,
        )
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=StatsResponseModel)
async def get_stats():
    """Get statistics about indexed documents."""
    try:
        from config.settings import get_settings
        from src.indexing.indexer import VectorIndexer
        settings = get_settings()

        indexer = VectorIndexer(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_api_key=settings.azure_openai_api_key,
            azure_api_version=settings.azure_openai_api_version,
            embedding_deployment=settings.azure_openai_embedding_model,
            chromadb_path=str(settings.chromadb_dir),
            collection_name="arch_knowledge",
        )
        stats = indexer.get_stats()
        return StatsResponseModel(**stats)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clients", response_model=list)
async def get_clients():
    """List all available clients from folder structure."""
    try:
        from config.settings import get_settings
        from src.ingestion.scanner import DocumentScanner
        settings = get_settings()

        scanner = DocumentScanner(str(settings.documents_dir))
        return scanner.get_clients()
    except Exception as e:
        logger.error(f"Clients error: {e}")
        raise HTTPException(status_code=500, detail=str(e))