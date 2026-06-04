"""
Query Pipeline V2 — Uses feature flags to choose Phase 1 or Phase 2 retriever
===============================================================================

LAYMAN:
    Same ask() method, same interface.
    But if USE_AZURE_SEARCH=true in .env, uses hybrid search.
    If false, uses ChromaDB (Phase 1 behavior).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from src.pipeline.response_cache import ResponseCache
from config.settings import get_settings
from src.generation.generator import AnswerGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class QueryResponse:
    answer: str
    sources: List[Dict[str, str]]
    retrieval_count: int
    intent: str
    client_detected: Optional[str]
    tokens_used: Dict[str, int]
    processing_time: float


class QueryPipelineV2:
    """
    Feature-flag-aware query pipeline.
    
    USE_AZURE_SEARCH=true  → AzureSearchRetriever (hybrid search)
    USE_AZURE_SEARCH=false → KnowledgeRetriever (ChromaDB)
    """

    def __init__(self):
        settings = get_settings()

        # Retriever — Phase 1 or Phase 2 based on flag
        if settings.use_azure_search:
            from src.retrieval.azure_search_retriever import AzureSearchRetriever
            self.retriever = AzureSearchRetriever()
            logger.info("🔍 Retriever: Azure AI Search — Hybrid (Phase 2)")
        else:
            from src.retrieval.retriever import KnowledgeRetriever
            self.retriever = KnowledgeRetriever(
                chromadb_path=str(settings.chromadb_dir),
                collection_name="arch_knowledge",
                top_k=settings.retrieval_top_k,
                min_relevance=settings.retrieval_min_relevance,
                azure_endpoint=settings.azure_openai_endpoint,
                azure_api_key=settings.azure_openai_api_key,
                azure_api_version=settings.azure_openai_api_version,
                embedding_deployment=settings.azure_openai_embedding_model,
            )
            logger.info("🔍 Retriever: ChromaDB — Semantic only (Phase 1)")

        # Generator — same for both phases
        self.generator = AnswerGenerator(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_api_key=settings.azure_openai_api_key,
            azure_api_version=settings.azure_openai_api_version,
            chat_deployment=settings.azure_openai_chat_model,
        )

        # Conversation memory
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 5
        # Response cache — avoid repeated LLM calls
        self.cache = ResponseCache(ttl_seconds=3600, max_entries=200)
        logger.info("QueryPipelineV2 initialized")

    def ask(self, question: str, client_filter: Optional[str] = None) -> QueryResponse:
        start_time = time.time()

        logger.info(f"\n{'─' * 50}")
        logger.info(f"QUERY: {question}")

        # ── Check cache first ──
        cached = self.cache.get(question, client_filter)
        if cached:
            return QueryResponse(**cached)

        # Detect intent and client
        intent = self.retriever.detect_query_intent(question)
        if client_filter is None:
            client_detected = self.retriever.detect_client(question)
        else:
            client_detected = client_filter

        logger.info(f"  Intent: {intent} | Client: {client_detected or 'all'}")

        # Route based on intent
        if intent == "comparison":
            comparison = self.retriever.retrieve_for_comparison(
                query=question, client_filter=client_detected,
            )
            current_chunks = comparison["current"]
            proposed_chunks = comparison["proposed"]
            retrieval_count = len(current_chunks) + len(proposed_chunks)

            generated = self.generator.generate_comparison(
                query=question,
                current_chunks=current_chunks,
                proposed_chunks=proposed_chunks,
                conversation_history=self.conversation_history,
            )
        else:
            chunks = self.retriever.retrieve(
                query=question, client_filter=client_detected,
            )
            retrieval_count = len(chunks)

            generated = self.generator.generate(
                query=question,
                retrieval_results=chunks,
                conversation_history=self.conversation_history,
            )

        # Update history
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": generated.answer})
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-(self.max_history * 2):]

        processing_time = time.time() - start_time

        response = QueryResponse(
            answer=generated.answer,
            sources=generated.sources,
            retrieval_count=retrieval_count,
            intent=intent,
            client_detected=client_detected,
            tokens_used=generated.tokens_used,
            processing_time=processing_time,
        )

        # ── Store in cache ──
        self.cache.set(question, {
            "answer": response.answer,
            "sources": response.sources,
            "retrieval_count": response.retrieval_count,
            "intent": response.intent,
            "client_detected": response.client_detected,
            "tokens_used": response.tokens_used,
            "processing_time": response.processing_time,
        }, client_filter)

        logger.info(f"  Done: {generated.tokens_used.get('total', 0)} tokens, {processing_time:.2f}s")

        return response
    
    def clear_history(self):
        self.conversation_history = []


# ── Standalone Testing ──
if __name__ == "__main__":
    print("=" * 60)
    print("Query Pipeline V2 — End-to-End Test")
    print("=" * 60)

    pipeline = QueryPipelineV2()

    test_questions = [
        "How is DataStories currently hosted?",
        "What is the budget for TechNova?",
        "Compare current vs proposed for RetailEdge",
    ]

    for q in test_questions:
        print(f"\n{'━' * 60}")
        print(f"❓ {q}")
        print(f"{'━' * 60}")

        response = pipeline.ask(q)

        preview = response.answer[:400]
        if len(response.answer) > 400:
            preview += "\n... (truncated)"
        print(f"\n📝 {preview}")
        print(f"\n  Intent:  {response.intent}")
        print(f"  Client:  {response.client_detected or 'all'}")
        print(f"  Chunks:  {response.retrieval_count}")
        print(f"  Tokens:  {response.tokens_used.get('total', 0)}")
        print(f"  Time:    {response.processing_time:.2f}s")

        pipeline.clear_history()

    print(f"\n{'=' * 60}")
    print("✅ Pipeline V2 test complete!")