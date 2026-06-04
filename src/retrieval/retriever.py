"""
Knowledge Retriever — Finds relevant chunks for user questions
================================================================

WHAT THIS MODULE DOES:
    Takes a question → Returns the most relevant chunks from ChromaDB.

    This is the CORE of RAG. If the retriever finds the wrong chunks,
    the LLM generates a wrong answer — no matter how powerful the model.

RAG CONCEPT — Why not just pass everything to the LLM?
    You COULD send all 89 chunks to GPT-4.1 (it has 1M token context).
    But:
    1. COST: 89 chunks × 300 tokens = 26,700 tokens per query
       vs 8 chunks × 300 tokens = 2,400 tokens per query (11x cheaper)

    2. ACCURACY: LLMs get CONFUSED by too much irrelevant context.
       "Lost in the middle" problem — models pay less attention to
       content in the middle of long contexts.

    3. SCALE: 89 chunks is fine, but what about 10,000 chunks
       across 50 clients? Can't fit in any context window.

    The retriever solves all three: find ONLY what's relevant.

RAG CONCEPT — Two types of filtering:
    1. METADATA FILTERING (exact match):
       "Only show me DataStories chunks" → filter: {client: "DataStories"}
       This is like a SQL WHERE clause. Fast, precise, binary.

    2. SEMANTIC SEARCH (meaning match):
       "hosting setup" finds "infrastructure deployment"
       This uses vector similarity. Fuzzy, intelligent, scored.

    We use BOTH together:
       First filter by client (metadata) → then rank by meaning (semantic)
       This is why metadata tagging in the chunker was so important.

PHASE 2 MIGRATION NOTE:
    Replace ChromaDB queries with Azure AI Search:
    - Adds HYBRID search (vector + keyword/BM25)
    - Adds semantic RERANKING (re-scores results with a cross-encoder)
    - Same metadata filtering concept, different API
    - Change only THIS module — rest of pipeline stays same
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import chromadb

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """
    A single retrieved chunk with its relevance score.

    WHY include relevance_score?
        1. The generator can mention confidence: "Based on highly relevant sources..."
        2. Debugging: "Why did this irrelevant chunk appear?" → check its score
        3. Threshold filtering: drop chunks below MIN_RELEVANCE
        4. Evaluation: measure retrieval quality over time
    """
    content: str                    # The chunk text
    metadata: Dict[str, Any]        # client, source_file, slide_number, etc.
    relevance_score: float          # 0.0 to 1.0 (higher = more relevant)


class KnowledgeRetriever:
    """
    Retrieves relevant document chunks for user queries.

    THE RETRIEVAL PIPELINE:
        Question
            ↓
        detect_client() → auto-detect which client
            ↓
        detect_query_intent() → comparison? explanation? specific?
            ↓
        retrieve() → semantic search + metadata filter
            ↓
        Filtered, scored results
    """

    def __init__(
        self,
        chromadb_path: str,
        collection_name: str = "arch_knowledge",
        top_k: int = 8,
        min_relevance: float = 0.35,
        azure_endpoint: str = "",
        azure_api_key: str = "",
        azure_api_version: str = "2024-12-01-preview",
        embedding_deployment: str = "text-embedding-3-small",
    ):
        """
        Args:
            chromadb_path: Path to ChromaDB storage
            collection_name: Which collection to search
            top_k: Max chunks to retrieve per query
            min_relevance: Minimum similarity score (0-1)
            azure_endpoint: Azure OpenAI endpoint (for query embedding)
            azure_api_key: Azure OpenAI API key
            azure_api_version: API version
            embedding_deployment: Embedding model deployment name
        """
        from openai import AzureOpenAI

        self.chroma_client = chromadb.PersistentClient(path=chromadb_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.top_k = top_k
        self.min_relevance = min_relevance

        # Azure OpenAI client for embedding QUERIES
        # MUST use the SAME model that was used for indexing
        # Otherwise: dimension mismatch (1536 vs 384)
        self.openai_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
        )
        self.embedding_deployment = embedding_deployment

        logger.info(
            f"KnowledgeRetriever initialized. "
            f"Collection: {collection_name}, "
            f"Chunks available: {self.collection.count()}, "
            f"top_k: {top_k}, min_relevance: {min_relevance}"
        )

    def _embed_query(self, query: str) -> List[float]:
        """
        Embed the query using Azure OpenAI (same model as indexing).

        WHY NOT let ChromaDB embed?
            ChromaDB's default model (all-MiniLM-L6-v2) produces 384-dim vectors.
            Our indexed chunks use Azure OpenAI which produces 1536-dim vectors.
            You CANNOT compare 384-dim vs 1536-dim — hence the error.

            RULE: Always embed queries with the SAME model used for indexing.
        """
        response = self.openai_client.embeddings.create(
            model=self.embedding_deployment,
            input=[query],
        )
        return response.data[0].embedding
    # ──────────────────────────────────────────────────────────
    # Client Detection
    # ──────────────────────────────────────────────────────────

    def detect_client(self, query: str) -> Optional[str]:
        """
        Detect which client the query is asking about.

        STRATEGY:
            1. Get all known client names from the collection
            2. Check if any client name appears in the query
            3. Return the match or None

        EXAMPLES:
            "Explain DataStories architecture"  → "DataStories"
            "How is MediFlow hosted?"           → "MediFlow"
            "What are the security standards?"   → None (no client mentioned)

        WHY AUTO-DETECT?
            Users naturally say "Explain DataStories architecture"
            rather than selecting a client from a dropdown first.
            Auto-detection makes the system feel conversational.

        LIMITATION:
            Simple substring matching. Could fail with:
            - Partial matches: "Data" matching "DataStories"
            - Ambiguous names: client named "The" would match everything
            In Phase 2, use NER or fuzzy matching for robustness.
        """
        # Get known clients from indexed metadata
        all_data = self.collection.get(include=["metadatas"])
        known_clients = set()
        if all_data and all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                if meta and "client" in meta:
                    known_clients.add(meta["client"])

        query_lower = query.lower()

        for client in known_clients:
            if client.lower() in query_lower:
                logger.info(f"  Client detected: {client}")
                return client

        logger.info("  No specific client detected")
        return None

    # ──────────────────────────────────────────────────────────
    # Query Intent Detection
    # ──────────────────────────────────────────────────────────

    def detect_query_intent(self, query: str) -> str:
        """
        Detect what TYPE of question the user is asking.

        WHY THIS MATTERS:
            Different intents need different retrieval strategies:

            "Compare current vs proposed"
                → Need TWO separate retrievals (current + proposed)
                → Use retrieve_for_comparison()

            "Explain the architecture"
                → Need broad retrieval across multiple slides
                → Use standard retrieve() with high top_k

            "What port does the gateway use?"
                → Need precise, specific retrieval
                → Use standard retrieve() with low top_k

            "Which clients use AWS?"
                → Need cross-client search (no client filter)
                → Use standard retrieve() without client filter

        FUTURE ENHANCEMENT (multi-model routing):
            This intent also determines which LLM model to use:
            - comparison → GPT-4.1 Full (complex reasoning)
            - explanation → GPT-4.1 Mini (good enough, cheaper)
            - specific → GPT-4.1 Mini (focused lookup)

        Returns:
            One of: "comparison", "explanation", "specific_component",
                    "listing", "general"
        """
        query_lower = query.lower()

        # ── Comparison intent ──
        comparison_keywords = [
            "compare", "vs", "versus", "difference", "differ",
            "current vs proposed", "old vs new", "before and after",
            "current and proposed", "what changed", "what improvements",
        ]
        for kw in comparison_keywords:
            if kw in query_lower:
                logger.info(f"  Intent: comparison (matched: \"{kw}\")")
                return "comparison"

        # ── Explanation intent ──
        explanation_keywords = [
            "explain", "describe", "overview", "walk me through",
            "tell me about", "how does", "how is", "what is the",
            "architecture",
        ]
        for kw in explanation_keywords:
            if kw in query_lower:
                logger.info(f"  Intent: explanation (matched: \"{kw}\")")
                return "explanation"

        # ── Specific component intent ──
        specific_keywords = [
            "gateway", "database", "auth", "ssl", "port",
            "firewall", "vpc", "subnet", "load balancer",
            "api", "endpoint", "certificate", "dns", "vpn",
        ]
        for kw in specific_keywords:
            if kw in query_lower:
                logger.info(f"  Intent: specific_component (matched: \"{kw}\")")
                return "specific_component"

        # ── Listing intent ──
        listing_keywords = [
            "list", "which clients", "how many", "all clients",
            "show me all", "what clients", "enumerate",
        ]
        for kw in listing_keywords:
            if kw in query_lower:
                logger.info(f"  Intent: listing (matched: \"{kw}\")")
                return "listing"

        logger.info("  Intent: general")
        return "general"

    # ──────────────────────────────────────────────────────────
    # Main Retrieval
    # ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        client_filter: Optional[str] = None,
        section_type_filter: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        Retrieve relevant chunks for a query.

        THE RETRIEVAL FLOW:
            1. Auto-detect client from query (if not provided)
            2. Build metadata filter
            3. Query ChromaDB (semantic search + filter)
            4. Convert distances → similarity scores
            5. Apply minimum relevance threshold
            6. Return sorted results

        PYTHON CONCEPT — Optional parameters:
            client_filter: Optional[str] = None
            This means: "you CAN pass a client, but you don't have to."
            If None → auto-detect from query text.
            If provided → use that exact client.

            C# equivalent:
                public List<Result> Retrieve(string query, string? clientFilter = null)

        Args:
            query: User's question
            client_filter: Optional explicit client (overrides auto-detect)
            section_type_filter: Optional section type filter
            top_k: Override default top_k for this query

        Returns:
            List of RetrievalResult, sorted by relevance (highest first)
        """
        k = top_k or self.top_k

        # Auto-detect client if not provided
        if client_filter is None:
            client_filter = self.detect_client(query)

        # Build ChromaDB filter
        where_filter = self._build_where_filter(client_filter, section_type_filter)

        logger.info(
            f"  Retrieving top-{k} for: \"{query[:80]}...\"\n"
            f"  Filters: client={client_filter}, section_type={section_type_filter}"
        )

        try:
            # Check if collection has data
            if self.collection.count() == 0:
                logger.warning("  Collection is empty — no chunks to search")
                return []

            # ── Query ChromaDB ──
            # ChromaDB does TWO things in one call:
            # 1. Embeds your query text (calls the same embedding model)
            #    Wait — actually ChromaDB uses its OWN default embedding.
            #    We're passing query_texts, so ChromaDB embeds it internally.
            #
            # 2. Finds the closest vectors using HNSW algorithm
            #    HNSW = Hierarchical Navigable Small World
            #    It's an approximate nearest neighbor algorithm.
            #    Very fast even with millions of vectors.
            # Embed query with Azure OpenAI (SAME model as indexing)
            query_embedding = self._embed_query(query)

            query_params = {
                "query_embeddings": [query_embedding],   # ✅ Our own 1536-dim vector
                "n_results": min(k, self.collection.count()),
                "include": ["documents", "metadatas", "distances"],
            }

            if where_filter:
                query_params["where"] = where_filter

            results = self.collection.query(**query_params)

        except Exception as e:
            logger.error(f"  ChromaDB query error: {e}")
            return []

        # ── Process results ──
        retrieval_results = []

        if results and results["documents"] and results["documents"][0]:
            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)
            distances = results["distances"][0] if results["distances"] else [1.0] * len(documents)

            for doc, meta, dist in zip(documents, metadatas, distances):
                # ── Convert distance to similarity ──
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # We want similarity: 1 = identical, 0 = unrelated
                #
                # Formula: similarity = 1 - (distance / 2)
                # But in practice, cosine distances for text are usually 0-1
                # So simpler: similarity = 1 - distance (clamped to 0-1)
                similarity = max(0.0, min(1.0, 1.0 - dist))

                # Apply minimum relevance threshold
                if similarity >= self.min_relevance:
                    retrieval_results.append(RetrievalResult(
                        content=doc,
                        metadata=meta or {},
                        relevance_score=round(similarity, 4),
                    ))
                else:
                    logger.debug(
                        f"  Dropped chunk (score {similarity:.4f} "
                        f"< threshold {self.min_relevance})"
                    )

        logger.info(
            f"  Retrieved {len(retrieval_results)} chunks "
            f"above threshold {self.min_relevance}"
        )

        return retrieval_results

    # ──────────────────────────────────────────────────────────
    # Comparison Retrieval (special)
    # ──────────────────────────────────────────────────────────

    def retrieve_for_comparison(
        self,
        query: str,
        client_filter: Optional[str] = None,
    ) -> Dict[str, List[RetrievalResult]]:
        """
        Special retrieval for comparison queries.

        WHY A SEPARATE METHOD?
            "Compare current vs proposed for DataStories"

            Single retrieval → mixed results (some current, some proposed)
            LLM gets confused → messy comparison

            Two targeted retrievals:
                1. section_type="current_architecture" → current chunks
                2. section_type="proposed_architecture" → proposed chunks
            LLM gets clean, separated context → structured comparison

        Returns:
            {"current": [...], "proposed": [...]}
        """
        if client_filter is None:
            client_filter = self.detect_client(query)

        logger.info(f"  Comparison retrieval for: {client_filter or 'all clients'}")

        # Retrieve half from each section type
        half_k = max(4, self.top_k // 2)

        current_results = self.retrieve(
            query=query,
            client_filter=client_filter,
            section_type_filter="current_architecture",
            top_k=half_k,
        )

        proposed_results = self.retrieve(
            query=query,
            client_filter=client_filter,
            section_type_filter="proposed_architecture",
            top_k=half_k,
        )

        logger.info(
            f"  Comparison results: "
            f"{len(current_results)} current, "
            f"{len(proposed_results)} proposed"
        )

        return {
            "current": current_results,
            "proposed": proposed_results,
        }

    # ──────────────────────────────────────────────────────────
    # Filter Building
    # ──────────────────────────────────────────────────────────

    def _build_where_filter(
        self,
        client: Optional[str],
        section_type: Optional[str],
    ) -> Optional[Dict]:
        """
        Build ChromaDB metadata filter.

        ChromaDB filter syntax:
            No filter:      None
            Single:         {"client": "DataStories"}
            AND:            {"$and": [{"client": "DataStories"}, {"section_type": "hosting"}]}

        C# equivalent (Azure AI Search):
            searchOptions.Filter = "client eq 'DataStories' and section_type eq 'hosting'";
        """
        conditions = []

        if client:
            conditions.append({"client": client})
        if section_type:
            conditions.append({"section_type": section_type})

        if len(conditions) == 0:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    from config.settings import get_settings
    settings = get_settings()

    print("=" * 60)
    print("Knowledge Retriever — Standalone Test")
    print("=" * 60)

    retriever = KnowledgeRetriever(
        chromadb_path=str(settings.chromadb_dir),
        collection_name="arch_knowledge",
        top_k=settings.retrieval_top_k,
        min_relevance=settings.retrieval_min_relevance,
        azure_endpoint=settings.azure_openai_endpoint,
        azure_api_key=settings.azure_openai_api_key,
        azure_api_version=settings.azure_openai_api_version,
        embedding_deployment=settings.azure_openai_embedding_model,
    )

    # ── Test queries ──
    test_queries = [
        "How is DataStories hosted?",
        "Explain MediFlow architecture",
        "What is the budget for TechNova?",
        "Compare current vs proposed for RetailEdge",
        "Which clients use AWS?",
        "What are the security standards for DataStories?",
    ]

    for query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"❓ {query}")
        print(f"{'─' * 60}")

        # Detect intent
        intent = retriever.detect_query_intent(query)
        print(f"  Intent: {intent}")

        # Retrieve
        if intent == "comparison":
            results = retriever.retrieve_for_comparison(query)
            print(f"\n  📋 CURRENT ({len(results['current'])} chunks):")
            for r in results["current"][:3]:
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"{r.metadata.get('client', '?')} | "
                    f"{r.content[:80]}..."
                )
            print(f"\n  📋 PROPOSED ({len(results['proposed'])} chunks):")
            for r in results["proposed"][:3]:
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"{r.metadata.get('client', '?')} | "
                    f"{r.content[:80]}..."
                )
        else:
            results = retriever.retrieve(query)
            print(f"\n  📋 Results ({len(results)} chunks):")
            for r in results[:5]:  # Show top 5
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"Type: {r.metadata.get('section_type', '?')} | "
                    f"{r.metadata.get('client', '?')}"
                )
                preview = r.content[:100].replace('\n', ' ')
                print(f"    → {preview}...")

    print(f"\n{'=' * 60}")
    print("✅ Retriever test complete!")
    print(f"{'=' * 60}")