"""
Azure AI Search — Index Setup (run once)
==========================================
Creates the search index with:
  - Vector field (for semantic search)
  - Text fields (for BM25 keyword search)
  - Filterable fields (for metadata filtering)
  - Semantic configuration (for reranking — if tier supports it)

Run: python -m src.indexing.search_index_setup

LAYMAN:
    This is like designing an empty filing system:
    "I want to search by meaning, by exact words, and filter by client"
    After this runs, the system is READY but EMPTY.
    Next step: fill it with your 89 chunks.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from config.settings import get_settings

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
)
from azure.core.credentials import AzureKeyCredential

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_index():
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("Azure AI Search — Index Setup")
    logger.info("=" * 60)
    logger.info(f"Endpoint: {settings.azure_search_endpoint}")
    logger.info(f"Index name: {settings.azure_search_index_name}")

    # ── Connect to Azure AI Search ──
    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )

    # ── Define fields ──
    # Each field = one "column" in your search index
    #
    # LAYMAN:
    #   Think of this like designing a spreadsheet:
    #   | id | content | content_vector | client | source_file | slide | type | title |
    #
    #   Some columns are "searchable" (you can search inside them)
    #   Some columns are "filterable" (you can filter like a dropdown)
    #   The vector column is special — it holds the 1536 numbers for meaning search

    fields = [
        # ── Primary key — unique ID for each chunk ──
        # Like a barcode on each product
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,                   # This is the unique identifier
            filterable=True,
        ),

        # ── Content — the actual chunk text ──
        # "searchable" means BM25 keyword search works on this field
        # This is the BIG difference from ChromaDB:
        #   ChromaDB: content is stored but NOT keyword-searchable
        #   Azure AI Search: content is BOTH keyword-searchable AND vector-searchable
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True,            # BM25 keyword search enabled
        ),

        # ── Content Vector — the 1536 embedding numbers ──
        # This enables semantic (meaning) search — same as ChromaDB
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,   # Must match text-embedding-3-small
            vector_search_profile_name="my-vector-profile",
        ),

        # ── Client — which client this chunk belongs to ──
        # "filterable" = can use in filter: client eq 'DataStories'
        # "facetable" = can get counts: DataStories=20, TechNova=17, etc.
        SimpleField(
            name="client",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),

        # ── Source file — which PPT this came from ──
        # For citations: [Source: blueprint.pptx, Slide 9]
        SimpleField(
            name="source_file",
            type=SearchFieldDataType.String,
            filterable=True,
        ),

        # ── Slide number — which slide(s) ──
        # Can be "9" (single) or "4-5" (merged)
        SimpleField(
            name="slide_number",
            type=SearchFieldDataType.String,
            filterable=True,
        ),

        # ── Section type — what kind of architecture content ──
        # filterable for comparison queries:
        #   section_type eq 'current_architecture'
        #   section_type eq 'proposed_architecture'
        SimpleField(
            name="section_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),

        # ── Title — slide title ──
        # Searchable so BM25 can match on titles too
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
            searchable=True,
        ),

        # ── Chunk index — position within the document ──
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),

        # ── File type — .pptx, .pdf, .docx ──
        SimpleField(
            name="file_type",
            type=SearchFieldDataType.String,
            filterable=True,
        ),

        # ── Ingested at — when this chunk was indexed ──
        # Sortable so you can get "latest ingested" chunks
        SimpleField(
            name="ingested_at",
            type=SearchFieldDataType.String,
            filterable=True,
            sortable=True,
        ),
    ]

    # ── Vector Search Configuration ──
    # HNSW = Hierarchical Navigable Small World
    # It's the algorithm that makes vector search FAST
    #
    # LAYMAN:
    #   Imagine 89 points on a map. To find the closest one to your query,
    #   you COULD check all 89 (slow). HNSW builds a shortcut graph
    #   so you only check ~10-15 points and still find the closest one.
    #   For 89 chunks it doesn't matter, but for 1 million chunks it's essential.

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-algo",
                # Default parameters are fine for our data size
                # For millions of vectors, you'd tune these
            ),
        ],
        profiles=[
            VectorSearchProfile(
                name="my-vector-profile",
                algorithm_configuration_name="hnsw-algo",
            ),
        ],
    )

    # ── Semantic Configuration (for reranking) ──
    # This tells the reranker WHICH fields to focus on
    # contentFields = main text to analyze
    # titleField = title for additional context
    #
    # NOTE: Semantic reranker requires Basic tier or higher.
    # On Free tier, this config is ignored (no error, just unused).
    # When you upgrade to Basic, it automatically activates!

    semantic_config = SemanticConfiguration(
        name="my-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="content")],
            title_field=SemanticField(field_name="title"),
        ),
    )

    # ── Create the Index ──
    index = SearchIndex(
        name=settings.azure_search_index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )

    # create_or_update = idempotent (safe to run multiple times)
    result = client.create_or_update_index(index)

    logger.info(f"\n✅ Index '{result.name}' created successfully!")
    logger.info(f"   Fields: {len(result.fields)}")
    logger.info(f"   Vector search: enabled (HNSW)")
    logger.info(f"   Semantic config: configured (active on Basic+ tier)")

    # ── Verify by listing fields ──
    logger.info(f"\n📋 Index fields:")
    for field in result.fields:
        attrs = []
        if getattr(field, 'searchable', False):
            attrs.append("searchable")
        if getattr(field, 'filterable', False):
            attrs.append("filterable")
        if getattr(field, 'facetable', False):
            attrs.append("facetable")
        if getattr(field, 'sortable', False):
            attrs.append("sortable")
        if getattr(field, 'key', False):
            attrs.append("KEY")

        # Check if it's a vector field
        is_vector = hasattr(field, 'vector_search_dimensions') and field.vector_search_dimensions
        if is_vector:
            attrs.append(f"vector({field.vector_search_dimensions}d)")

        attrs_str = ", ".join(attrs) if attrs else ""
        logger.info(f"   {field.name:<20} {str(field.type):<40} [{attrs_str}]")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Index is EMPTY and READY for data.")
    logger.info(f"Next step: Run the Phase 2 indexer to populate it.")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    create_index()