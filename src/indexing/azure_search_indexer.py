"""
Azure AI Search Indexer — Embeds and stores chunks in Azure AI Search
======================================================================

WHAT CHANGED FROM PHASE 1:
    Phase 1 (indexer.py):
        chunks → embed with Azure OpenAI → store in ChromaDB (local)
    
    Phase 2 (this file):
        chunks → embed with Azure OpenAI → store in Azure AI Search (cloud)
    
    The embedding step is IDENTICAL.
    Only the storage destination changes.

WHAT YOU GET BY SWITCHING:
    ChromaDB stores: vector + text + metadata
    Azure AI Search stores: vector + text + metadata
        + text is now BM25-searchable (keyword search!)
        + metadata supports OData filter expressions
        + semantic reranker available (Basic+ tier)

LAYMAN:
    Phase 1: Put labeled index cards into a personal filing cabinet
    Phase 2: Put the same labeled cards into a professional library system
             that can search by meaning AND by exact words

Run: python -m src.indexing.azure_search_indexer
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hashlib
import logging
import time
from typing import List, Dict, Any

from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import IndexingResult
from azure.core.credentials import AzureKeyCredential

from config.settings import get_settings
from src.ingestion.chunker import DocumentChunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class AzureSearchIndexer:
    """
    Phase 2 indexer — stores chunks in Azure AI Search.
    
    Same interface as Phase 1 VectorIndexer:
        index_chunks(chunks) → embeds + stores
        delete_by_source(file) → removes old chunks
        get_stats() → returns index statistics
    
    This means the ingestion pipeline can switch between
    Phase 1 and Phase 2 indexer without any other changes.
    """

    def __init__(self):
        """
        Initialize Azure OpenAI (for embeddings) and Azure AI Search (for storage).
        
        LAYMAN:
            Two connections:
            1. Azure OpenAI = the translator (converts text → numbers)
            2. Azure AI Search = the library (stores and searches those numbers)
        """
        settings = get_settings()

        # Azure OpenAI — for generating embeddings (SAME as Phase 1)
        self.openai_client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.embedding_model = settings.azure_openai_embedding_model

        # Azure AI Search — for storing and searching (NEW in Phase 2)
        self.search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )
        self.index_name = settings.azure_search_index_name

        logger.info(
            f"AzureSearchIndexer initialized.\n"
            f"  Search: {settings.azure_search_endpoint}\n"
            f"  Index: {self.index_name}\n"
            f"  Embedding: {self.embedding_model}"
        )

    def _generate_chunk_id(self, chunk: DocumentChunk) -> str:
        """
        Same deterministic ID as Phase 1.
        Same file + same position = same ID = idempotent upsert.
        """
        id_string = (
            f"{chunk.metadata['client']}"
            f"_{chunk.metadata['source_file']}"
            f"_{chunk.metadata['chunk_index']}"
        )
        return hashlib.md5(id_string.encode()).hexdigest()

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings — IDENTICAL to Phase 1.
        Same model, same dimensions, same API call.
        """
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def index_chunks(
        self,
        chunks: List[DocumentChunk],
        batch_size: int = 16,
    ) -> Dict[str, Any]:
        """
        Embed chunks and upload to Azure AI Search.
        
        THE KEY DIFFERENCE FROM PHASE 1:
        
        Phase 1 (ChromaDB):
            collection.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metas)
        
        Phase 2 (Azure AI Search):
            search_client.upload_documents(documents=[
                {"id": id, "content": text, "content_vector": vector, "client": "DataStories", ...}
            ])
        
        Same data, different API. But now the 'content' field is
        automatically BM25-indexed for keyword search!
        
        LAYMAN:
            Phase 1: Put cards in filing cabinet (only meaning-searchable)
            Phase 2: Put cards in library catalog (meaning + word searchable)
        """
        if not chunks:
            logger.warning("No chunks to index")
            return {"chunks_indexed": 0, "errors": 0}

        logger.info(f"Indexing {len(chunks)} chunks into Azure AI Search...")

        total_indexed = 0
        total_errors = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(chunks) + batch_size - 1) // batch_size

            logger.info(f"  Batch {batch_num}/{total_batches}: {len(batch)} chunks")

            try:
                # Step 1: Generate embeddings (same as Phase 1)
                texts = [c.content for c in batch]
                embeddings = self._embed_batch(texts)

                # Step 2: Build documents for Azure AI Search
                # This is where Phase 2 differs — we build a FLAT document
                # with all fields, instead of separate embeddings + metadatas
                documents = []
                for chunk, embedding in zip(batch, embeddings):
                    doc = {
                        "id": self._generate_chunk_id(chunk),
                        "content": chunk.content,
                        "content_vector": embedding,
                        "client": chunk.metadata.get("client", ""),
                        "source_file": chunk.metadata.get("source_file", ""),
                        "slide_number": chunk.metadata.get("slide_number", ""),
                        "section_type": chunk.metadata.get("section_type", ""),
                        "title": chunk.metadata.get("title", ""),
                        "chunk_index": chunk.metadata.get("chunk_index", 0),
                        "file_type": chunk.metadata.get("file_type", ""),
                        "ingested_at": chunk.metadata.get("ingested_at", ""),
                    }
                    documents.append(doc)

                # Step 3: Upload to Azure AI Search
                # upload_documents = upsert behavior (insert or replace)
                # This is like ChromaDB's upsert — idempotent!
                result = self.search_client.upload_documents(documents=documents)

                # Check results
                succeeded = sum(1 for r in result if r.succeeded)
                failed = sum(1 for r in result if not r.succeeded)

                total_indexed += succeeded
                total_errors += failed

                if failed > 0:
                    for r in result:
                        if not r.succeeded:
                            logger.error(f"    Failed: {r.key} — {r.error_message}")

                logger.info(f"  Batch {batch_num} ✅ ({succeeded} indexed, {failed} errors)")

                # Rate limiting between batches
                if i + batch_size < len(chunks):
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"  Batch {batch_num} ❌: {e}")
                total_errors += len(batch)

        # Get final document count
        doc_count = self._get_document_count()

        result = {
            "chunks_indexed": total_indexed,
            "errors": total_errors,
            "total_in_index": doc_count,
        }

        logger.info(
            f"Indexing complete: {total_indexed} indexed, "
            f"{total_errors} errors, {doc_count} total in index"
        )

        return result

    def delete_by_source(self, source_file: str) -> int:
        """
        Delete all chunks from a specific source file.
        Same purpose as Phase 1 — for re-indexing updated documents.
        
        LAYMAN:
            "Remove all cards from the library that came from blueprint.pptx"
            Then we'll add the updated cards.
        """
        try:
            # Search for all documents with this source_file
            results = self.search_client.search(
                search_text="*",
                filter=f"source_file eq '{source_file}'",
                select=["id"],
                top=1000,
            )

            ids_to_delete = [{"id": doc["id"]} for doc in results]

            if ids_to_delete:
                self.search_client.delete_documents(documents=ids_to_delete)
                logger.info(f"Deleted {len(ids_to_delete)} chunks for: {source_file}")
                return len(ids_to_delete)
            else:
                logger.info(f"No chunks found for: {source_file}")
                return 0

        except Exception as e:
            logger.error(f"Error deleting chunks for {source_file}: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        try:
            # Get facets for client and section_type
            results = self.search_client.search(
                search_text="*",
                facets=["client", "section_type"],
                top=0,
                include_total_count=True,
            )

            doc_count = results.get_count() or 0

            clients = []
            section_types = []

            facets = results.get_facets()
            if "client" in facets:
                clients = [f["value"] for f in facets["client"]]
            if "section_type" in facets:
                section_types = [f["value"] for f in facets["section_type"]]

            # Get unique files separately (not facetable, so query distinct values)
            file_results = self.search_client.search(
                search_text="*",
                select=["source_file"],
                top=1000,
            )
            files = sorted(set(doc["source_file"] for doc in file_results if doc.get("source_file")))

            return {
                "total_chunks": doc_count,
                "unique_clients": len(clients),
                "unique_files": len(files),
                "clients": sorted(clients),
                "files": files,
                "section_types": sorted(section_types),
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "total_chunks": 0,
                "unique_clients": 0,
                "unique_files": 0,
                "clients": [],
                "files": [],
                "section_types": [],
            }

    def _get_document_count(self) -> int:
        """Get total document count in the index."""
        try:
            results = self.search_client.search(
                search_text="*",
                top=0,
                include_total_count=True,
            )
            return results.get_count() or 0
        except Exception:
            return 0


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    from src.ingestion.scanner import DocumentScanner
    from src.ingestion.extractor import TextExtractor
    from src.ingestion.chunker import DocumentChunker

    settings = get_settings()

    print("=" * 60)
    print("Azure AI Search Indexer — Standalone Test")
    print("=" * 60)

    # ── Step 1: Scan + Extract + Chunk (same as Phase 1) ──
    print("\n📁 Scanning documents...")
    scanner = DocumentScanner(str(settings.documents_dir))
    documents = scanner.scan()

    if not documents:
        print("❌ No documents found!")
        sys.exit(1)

    extractor = TextExtractor()
    chunker = DocumentChunker(
        min_length=settings.min_chunk_length,
        max_length=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )

    all_chunks = []
    for doc in documents:
        slides = extractor.extract(doc.file_path)
        chunks = chunker.chunk_document(
            slides=slides,
            client_name=doc.client_name,
            source_file=doc.file_name,
            file_type=doc.file_type,
        )
        all_chunks.extend(chunks)

    print(f"\n📦 Total chunks to index: {len(all_chunks)}")

    # ── Step 2: Index into Azure AI Search ──
    print("\n🔌 Connecting to Azure AI Search...")
    indexer = AzureSearchIndexer()

    print("\n⚡ Embedding and indexing chunks...")
    result = indexer.index_chunks(all_chunks)

    print(f"\n{'=' * 60}")
    print(f"INDEXING RESULTS:")
    print(f"  Chunks indexed:     {result['chunks_indexed']}")
    print(f"  Errors:             {result['errors']}")
    print(f"  Total in index:     {result['total_in_index']}")
    print(f"{'=' * 60}")

    # ── Step 3: Show stats ──
    print("\n⏳ Waiting 3 seconds for index to update...")
    time.sleep(3)

    stats = indexer.get_stats()
    print(f"\n📊 Index Statistics:")
    print(f"  Total chunks:    {stats['total_chunks']}")
    print(f"  Clients:         {stats['clients']}")
    print(f"  Files:           {stats['unique_files']}")
    print(f"  Section types:   {stats['section_types']}")
    print(f"{'=' * 60}")