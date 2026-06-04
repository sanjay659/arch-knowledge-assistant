"""
Query Pipeline — End-to-end question answering orchestrator
=============================================================

WHAT THIS MODULE DOES:
    Provides ONE method: ask(question) → answer

    Internally orchestrates:
        question → intent detection → client detection
        → retrieval → generation → response

    This is the SINGLE ENTRY POINT for all Q&A operations.
    The API calls this. The UI calls this. Tests call this.

WHY A PIPELINE?
    Without pipeline:
        Every caller (API, UI, CLI) repeats:
            retriever = KnowledgeRetriever(...)
            intent = retriever.detect_query_intent(query)
            if intent == "comparison":
                results = retriever.retrieve_for_comparison(...)
                answer = generator.generate_comparison(...)
            else:
                results = retriever.retrieve(...)
                answer = generator.generate(...)
            # update history...
            # build response...

        → Duplicated logic in 3+ places
        → Bug in one place? Fix in 3 places.

    With pipeline:
        response = pipeline.ask("How is DataStories hosted?")
        print(response.answer)

        → One place for all logic
        → One place to fix bugs
        → One place to add features (caching, logging, metrics)

RAG CONCEPT — Conversation Memory:
    Users ask follow-up questions:
        Q1: "How is DataStories hosted?"
        Q2: "What about the security aspects?"

    Q2 is a FOLLOW-UP — "the" refers to DataStories implicitly.
    Without conversation history, Q2 would search all clients.

    We keep a sliding window of last 5 Q&A pairs in memory.
    The LLM sees these in the prompt and understands context.

    LIMITATION: Memory is in-memory (lost on restart).
    Phase 2: Store in Redis or Azure Cosmos DB for persistence.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.retrieval.retriever import KnowledgeRetriever
from src.generation.generator import AnswerGenerator

logger = logging.getLogger(__name__)


@dataclass
class QueryResponse:
    """
    Complete response to a user query.

    Contains everything the API/UI needs:
        answer:           The text to display
        sources:          Source citations for verification
        retrieval_count:  How many chunks were used
        intent:           What the system understood
        client_detected:  Which client was identified
        tokens_used:      For cost tracking
        processing_time:  For latency monitoring
    """
    answer: str
    sources: List[Dict[str, str]]
    retrieval_count: int
    intent: str
    client_detected: Optional[str]
    tokens_used: Dict[str, int]
    processing_time: float


class QueryPipeline:
    """
    Orchestrates the full question-answering flow.

    Usage:
        pipeline = QueryPipeline()
        response = pipeline.ask("How is DataStories hosted?")
        print(response.answer)

        # Follow-up (uses conversation history):
        response2 = pipeline.ask("What about security?")

        # New topic (clear history):
        pipeline.clear_history()
        response3 = pipeline.ask("Explain MediFlow architecture")
    """

    def __init__(self):
        """
        Initialize retriever and generator from settings.

        All configuration comes from .env via settings.
        No hardcoded values here.
        """
        from config.settings import get_settings
        settings = get_settings()

        # Knowledge retriever — finds relevant chunks
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

        # Answer generator — creates answers from chunks
        self.generator = AnswerGenerator(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_api_key=settings.azure_openai_api_key,
            azure_api_version=settings.azure_openai_api_version,
            chat_deployment=settings.azure_openai_chat_model,
        )

        # Conversation memory — sliding window of recent Q&A pairs
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 5  # Keep last 5 Q&A pairs

        logger.info("QueryPipeline initialized")

    def ask(
        self,
        question: str,
        client_filter: Optional[str] = None,
    ) -> QueryResponse:
        """
        Process a user question and return a complete response.

        THE QUERY FLOW:
            1. Detect query intent (comparison? explanation? specific?)
            2. Detect client from query text (or use provided filter)
            3. Route to appropriate retrieval strategy
            4. Generate answer with citations
            5. Update conversation history
            6. Return structured response

        Args:
            question: Natural language question
            client_filter: Optional explicit client filter
                          (overrides auto-detection)

        Returns:
            QueryResponse with answer, sources, metadata
        """
        start_time = time.time()

        logger.info(f"\n{'─' * 50}")
        logger.info(f"QUERY: {question}")
        logger.info(f"{'─' * 50}")

        # ── Step 1: Detect query intent ──
        intent = self.retriever.detect_query_intent(question)

        # ── Step 2: Detect or use client filter ──
        if client_filter is None:
            client_detected = self.retriever.detect_client(question)
        else:
            client_detected = client_filter

        logger.info(f"  Intent: {intent} | Client: {client_detected or 'all'}")

        # ── Step 3 & 4: Route based on intent ──
        if intent == "comparison":
            # COMPARISON: Two separate retrievals → comparison generation
            comparison_results = self.retriever.retrieve_for_comparison(
                query=question,
                client_filter=client_detected,
            )
            current_chunks = comparison_results["current"]
            proposed_chunks = comparison_results["proposed"]
            all_chunks = current_chunks + proposed_chunks
            retrieval_count = len(all_chunks)

            logger.info(
                f"  Retrieved: {len(current_chunks)} current, "
                f"{len(proposed_chunks)} proposed"
            )

            # Generate comparison answer
            generated = self.generator.generate_comparison(
                query=question,
                current_chunks=current_chunks,
                proposed_chunks=proposed_chunks,
                conversation_history=self.conversation_history,
            )
        else:
            # ALL OTHER INTENTS: Standard retrieval → standard generation
            chunks = self.retriever.retrieve(
                query=question,
                client_filter=client_detected,
            )
            retrieval_count = len(chunks)

            logger.info(f"  Retrieved: {retrieval_count} chunks")

            # Generate answer
            generated = self.generator.generate(
                query=question,
                retrieval_results=chunks,
                conversation_history=self.conversation_history,
            )

        # ── Step 5: Update conversation history ──
        self._update_history(question, generated.answer)

        # ── Step 6: Build response ──
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

        logger.info(
            f"  Done: {generated.tokens_used.get('total', 0)} tokens, "
            f"{processing_time:.2f}s"
        )

        return response

    def _update_history(self, question: str, answer: str):
        """
        Add latest Q&A pair to conversation history.

        Uses a SLIDING WINDOW to keep only the last N turns.
        This prevents:
        1. Context growing too large (token cost)
        2. Old context confusing the LLM
        3. Memory usage growing unbounded

        PYTHON CONCEPT — Sliding window:
            Keep only the last max_history * 2 messages (Q+A pairs).
            When we exceed the limit, slice off the oldest messages.

            C# equivalent:
                if (history.Count > maxMessages)
                    history = history.Skip(history.Count - maxMessages).ToList();
        """
        self.conversation_history.append(
            {"role": "user", "content": question}
        )
        self.conversation_history.append(
            {"role": "assistant", "content": answer}
        )

        # Keep only last N pairs (N * 2 messages)
        max_messages = self.max_history * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def clear_history(self):
        """Clear conversation history. Useful when starting a new topic."""
        self.conversation_history = []
        logger.info("Conversation history cleared")


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("Query Pipeline — Interactive Test")
    print("=" * 60)

    pipeline = QueryPipeline()

    # ── Pre-defined test questions ──
    test_questions = [
        ("How is DataStories currently hosted?", None),
        ("What about the security standards?", None),  # Follow-up!
        ("Explain MediFlow architecture", None),
        ("What is the budget for TechNova?", None),
        ("Compare current vs proposed for RetailEdge", None),
    ]

    for question, client in test_questions:
        print(f"\n{'━' * 60}")
        print(f"❓ {question}")
        if client:
            print(f"   (filter: {client})")
        print(f"{'━' * 60}")

        response = pipeline.ask(question, client_filter=client)

        # Show answer (first 500 chars)
        answer_preview = response.answer[:500]
        if len(response.answer) > 500:
            answer_preview += "\n... (truncated)"
        print(f"\n📝 {answer_preview}")

        # Show metadata
        print(f"\n  Intent:    {response.intent}")
        print(f"  Client:    {response.client_detected or 'all'}")
        print(f"  Chunks:    {response.retrieval_count}")
        print(f"  Tokens:    {response.tokens_used.get('total', 0)}")
        print(f"  Time:      {response.processing_time:.2f}s")
        print(f"  Sources:   {len(response.sources)}")
        for s in response.sources[:3]:
            print(f"    📄 {s['file']} | Slide {s['slide']}")

        # Clear history after comparison to start fresh
        if response.intent == "comparison":
            pipeline.clear_history()

    # ── Total cost summary ──
    print(f"\n{'=' * 60}")
    print(f"✅ Pipeline test complete!")
    print(f"{'=' * 60}")