"""
Azure AI Search Retriever — Hybrid Search (Vector + Keyword)
==============================================================

WHAT CHANGED FROM PHASE 1:
    Phase 1 (retriever.py + ChromaDB):
        query → embed → vector similarity only → results
        
    Phase 2 (this file + Azure AI Search):
        query → embed → vector similarity  ─┐
        query →        BM25 keyword match  ─┤→ Reciprocal Rank Fusion → results
                                            ─┘

LAYMAN:
    Phase 1: Search by MEANING only
        "hosting setup" finds "infrastructure deployment" ✅
        "port 443" might NOT find the exact slide with "443" ❌
    
    Phase 2: Search by MEANING + EXACT WORDS
        "hosting setup" finds "infrastructure deployment" ✅ (vector)
        "port 443" ALSO finds slides containing literal "443" ✅ (keyword)
        Results that match BOTH rank highest (fusion)

WHAT IS RECIPROCAL RANK FUSION (RRF)?
    Two search engines each produce a ranked list.
    RRF combines them by looking at RANK POSITION:
    
    Vector results:   #1 Slide 10,  #2 Slide 4,  #3 Slide 9
    Keyword results:  #1 Slide 10,  #2 Slide 20, #3 Slide 4
    
    RRF score for Slide 10: 1/1 + 1/1 = 2.0 (top in BOTH → strongest)
    RRF score for Slide 4:  1/2 + 1/3 = 0.83 (good in both)
    RRF score for Slide 9:  1/3 + 0   = 0.33 (only in vector)
    RRF score for Slide 20: 0   + 1/2 = 0.50 (only in keyword)
    
    Final ranking: Slide 10, Slide 4, Slide 20, Slide 9
    
    Documents found by BOTH methods rank highest.
    This is why hybrid > either method alone.

Run: python -m src.retrieval.azure_search_retriever
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

from config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Same interface as Phase 1 — rest of pipeline doesn't change."""
    content: str
    metadata: Dict[str, Any]
    relevance_score: float


class AzureSearchRetriever:
    """
    Phase 2 retriever — Hybrid search with Azure AI Search.
    
    SAME INTERFACE as Phase 1 KnowledgeRetriever:
        retrieve(query, client_filter, section_type_filter) → List[RetrievalResult]
        detect_client(query) → Optional[str]
        detect_query_intent(query) → str
        retrieve_for_comparison(query, client_filter) → Dict
    
    The query pipeline doesn't need to know which retriever it's using.
    This is the power of modular design.
    """

    def __init__(self):
        settings = get_settings()

        # Azure AI Search client
        self.search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )

        # Azure OpenAI client (for embedding queries — SAME model as indexing)
        self.openai_client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.embedding_model = settings.azure_openai_embedding_model

        self.top_k = settings.retrieval_top_k
        self.min_relevance = settings.retrieval_min_relevance

        # Get known clients for auto-detection
        self._known_clients = self._load_known_clients()

        logger.info(
            f"AzureSearchRetriever initialized.\n"
            f"  Index: {settings.azure_search_index_name}\n"
            f"  Known clients: {self._known_clients}\n"
            f"  top_k: {self.top_k}, min_relevance: {self.min_relevance}"
        )

    def _load_known_clients(self) -> List[str]:
        """Load client names from the index using facets."""
        try:
            results = self.search_client.search(
                search_text="*",
                facets=["client"],
                top=0,
            )
            facets = results.get_facets()
            if "client" in facets:
                return [f["value"] for f in facets["client"]]
            return []
        except Exception as e:
            logger.warning(f"Could not load clients: {e}")
            return []

    def _embed_query(self, query: str) -> List[float]:
        """Embed query with Azure OpenAI — SAME model as indexing."""
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=[query],
        )
        return response.data[0].embedding

    # ──────────────────────────────────────────────────────────
    # Client Detection (same logic as Phase 1)
    # ──────────────────────────────────────────────────────────

    def detect_client(self, query: str) -> Optional[str]:
        """Detect client name from query text."""
        query_lower = query.lower()
        for client in self._known_clients:
            if client.lower() in query_lower:
                logger.info(f"  Client detected: {client}")
                return client
        logger.info("  No specific client detected")
        return None

    # ──────────────────────────────────────────────────────────
    # Intent Detection (same logic as Phase 1)
    # ──────────────────────────────────────────────────────────

    def detect_query_intent(self, query: str) -> str:
        """Detect query intent — same as Phase 1."""
        query_lower = query.lower()

        for kw in ["compare", "vs", "versus", "difference", "what changed"]:
            if kw in query_lower:
                logger.info(f"  Intent: comparison (matched: \"{kw}\")")
                return "comparison"

        for kw in ["explain", "describe", "overview", "how does", "how is",
                    "what is the", "architecture", "walk me through"]:
            if kw in query_lower:
                logger.info(f"  Intent: explanation (matched: \"{kw}\")")
                return "explanation"

        for kw in ["gateway", "database", "auth", "ssl", "port",
                    "firewall", "vpc", "load balancer", "api", "vpn"]:
            if kw in query_lower:
                logger.info(f"  Intent: specific_component (matched: \"{kw}\")")
                return "specific_component"

        for kw in ["list", "which clients", "how many", "all clients", "show me all"]:
            if kw in query_lower:
                logger.info(f"  Intent: listing (matched: \"{kw}\")")
                return "listing"

        logger.info("  Intent: general")
        return "general"

    # ──────────────────────────────────────────────────────────
    # MAIN RETRIEVAL — Hybrid Search (THE BIG CHANGE)
    # ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        client_filter: Optional[str] = None,
        section_type_filter: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        Hybrid search: Vector + BM25 Keyword + Metadata Filter.
        
        THIS IS THE KEY DIFFERENCE FROM PHASE 1:
        
        Phase 1:
            collection.query(query_embeddings=[vector], n_results=8)
            → Vector similarity ONLY
        
        Phase 2:
            search_client.search(
                search_text=query,           ← BM25 keyword (NEW!)
                vector_queries=[vector],      ← Vector similarity (same)
                filter="client eq '...'"      ← Metadata filter (BETTER!)
            )
            → Both combined via Reciprocal Rank Fusion
        """
        k = top_k or self.top_k

        # Auto-detect client if not provided
        if client_filter is None:
            client_filter = self.detect_client(query)

        # Build OData filter
        filter_expr = self._build_filter(client_filter, section_type_filter)

        logger.info(
            f"  Hybrid search for: \"{query[:80]}...\"\n"
            f"  Filter: {filter_expr or 'none'}"
        )

        try:
            # ── Embed the query (same as Phase 1) ──
            query_vector = self._embed_query(query)

            # ── Build vector query ──
            # VectorizedQuery tells Azure AI Search:
            # "Here's my query as 1536 numbers. Find the closest chunks."
            #
            # k_nearest_neighbors=50: Get top 50 by vector similarity
            # These 50 candidates will be fused with BM25 results
            # Then the top 'k' are returned
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=50,
                fields="content_vector",
            )

            # ── Execute HYBRID search ──
            # THE MAGIC LINE — one API call does THREE things:
            #   1. search_text=query  → BM25 keyword search on 'content' and 'title'
            #   2. vector_queries     → Vector similarity search on 'content_vector'
            #   3. filter             → Metadata filtering (client, section_type)
            #
            # Azure AI Search automatically:
            #   - Runs both searches in parallel
            #   - Combines results using Reciprocal Rank Fusion (RRF)
            #   - Applies the metadata filter
            #   - Returns top-k results with combined scores

            results = self.search_client.search(
                search_text=query,                  # ← BM25 keyword search
                vector_queries=[vector_query],       # ← Vector similarity search
                filter=filter_expr,                  # ← Metadata filter
                top=k,                               # ← How many results
                select=[                             # ← Which fields to return
                    "id", "content", "client", "source_file",
                    "slide_number", "section_type", "title",
                    "chunk_index", "file_type",
                ],
            )

            # ── Process results ──
            retrieval_results = []
            for result in results:
                # Azure AI Search provides @search.score
                # This is the FUSED score from RRF (combines vector + keyword)
                score = result.get("@search.score", 0)

                # Normalize score to 0-1 range for compatibility with Phase 1
                # Azure search scores vary by query; we normalize roughly
                # RRF scores are typically in range 0.01-0.05 for hybrid
                # We scale to make them comparable to Phase 1 cosine similarity
                normalized_score = min(1.0, score * 15)  # Rough normalization

                if normalized_score >= self.min_relevance:
                    retrieval_results.append(RetrievalResult(
                        content=result.get("content", ""),
                        metadata={
                            "client": result.get("client", ""),
                            "source_file": result.get("source_file", ""),
                            "slide_number": result.get("slide_number", ""),
                            "section_type": result.get("section_type", ""),
                            "title": result.get("title", ""),
                            "chunk_index": result.get("chunk_index", 0),
                            "file_type": result.get("file_type", ""),
                        },
                        relevance_score=round(normalized_score, 4),
                    ))

            logger.info(f"  Retrieved {len(retrieval_results)} chunks (hybrid search)")

            return retrieval_results

        except Exception as e:
            logger.error(f"  Hybrid search error: {e}")
            return []

    # ──────────────────────────────────────────────────────────
    # Comparison Retrieval (same pattern as Phase 1)
    # ──────────────────────────────────────────────────────────

    def retrieve_for_comparison(
        self,
        query: str,
        client_filter: Optional[str] = None,
    ) -> Dict[str, List[RetrievalResult]]:
        """Two separate hybrid searches: current + proposed."""
        if client_filter is None:
            client_filter = self.detect_client(query)

        logger.info(f"  Comparison retrieval for: {client_filter or 'all'}")

        half_k = max(4, self.top_k // 2)

        current = self.retrieve(
            query=query,
            client_filter=client_filter,
            section_type_filter="current_architecture",
            top_k=half_k,
        )

        proposed = self.retrieve(
            query=query,
            client_filter=client_filter,
            section_type_filter="proposed_architecture",
            top_k=half_k,
        )

        logger.info(f"  Comparison: {len(current)} current, {len(proposed)} proposed")

        return {"current": current, "proposed": proposed}

    # ──────────────────────────────────────────────────────────
    # OData Filter Builder
    # ──────────────────────────────────────────────────────────

    def _build_filter(
        self,
        client: Optional[str],
        section_type: Optional[str],
    ) -> Optional[str]:
        """
        Build OData filter expression.
        
        LAYMAN:
            Phase 1 (ChromaDB): {"client": "DataStories"}
            Phase 2 (Azure):    "client eq 'DataStories'"
        
        OData supports MUCH richer filters:
            "client eq 'DataStories' and section_type eq 'budget'"
            "chunk_index ge 5 and chunk_index le 10"
            "search.in(client, 'DataStories,TechNova')"
        """
        conditions = []
        if client:
            conditions.append(f"client eq '{client}'")
        if section_type:
            conditions.append(f"section_type eq '{section_type}'")

        if conditions:
            return " and ".join(conditions)
        return None


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Azure AI Search Retriever — Hybrid Search Test")
    print("=" * 60)

    retriever = AzureSearchRetriever()

    # ── Test queries — same as Phase 1 for comparison ──
    test_queries = [
        "How is DataStories hosted?",
        "Explain MediFlow architecture",
        "What is the budget for TechNova?",
        "Compare current vs proposed for RetailEdge",
        "Which clients use AWS?",
        "What are the security standards for DataStories?",
        "port 443",                           # ← NEW: exact keyword test
        "account number 556008695729",         # ← NEW: exact number test
    ]

    for query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"❓ {query}")
        print(f"{'─' * 60}")

        intent = retriever.detect_query_intent(query)
        print(f"  Intent: {intent}")

        if intent == "comparison":
            results = retriever.retrieve_for_comparison(query)
            print(f"\n  📋 CURRENT ({len(results['current'])} chunks):")
            for r in results["current"][:3]:
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"{r.metadata.get('client', '?')}"
                )
                print(f"    → {r.content[:80]}...")
            print(f"\n  📋 PROPOSED ({len(results['proposed'])} chunks):")
            for r in results["proposed"][:3]:
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"{r.metadata.get('client', '?')}"
                )
                print(f"    → {r.content[:80]}...")
        else:
            results = retriever.retrieve(query)
            print(f"\n  📋 Results ({len(results)} chunks):")
            for r in results[:5]:
                print(
                    f"    Score: {r.relevance_score:.4f} | "
                    f"Slide {r.metadata.get('slide_number', '?')} | "
                    f"Type: {r.metadata.get('section_type', '?')} | "
                    f"{r.metadata.get('client', '?')}"
                )
                print(f"    → {r.content[:80]}...")

    print(f"\n{'=' * 60}")
    print("✅ Hybrid search test complete!")
    print(f"{'=' * 60}")