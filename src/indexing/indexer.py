"""
Vector Indexer — Embeds and stores chunks in ChromaDB
======================================================

WHAT THIS MODULE DOES:
    Takes DocumentChunks → Embeds them → Stores in ChromaDB.

    After this step, your data is SEARCHABLE by meaning.

RAG CONCEPT — Why Embeddings?
    Traditional search: keyword matching
        Query: "hosting setup" → finds documents with exact words "hosting" and "setup"
        MISSES: "infrastructure deployment" (same meaning, different words)

    Semantic search: meaning matching
        Query: "hosting setup" → embedding → [0.12, -0.34, 0.56, ...]
        Finds: "infrastructure deployment" → [0.11, -0.33, 0.55, ...]
        These vectors are CLOSE → match found! ✅

    This is the core superpower of RAG over traditional search.

RAG CONCEPT — Why Batch Embedding?
    Azure OpenAI has rate limits (tokens per minute).
    If you send 68 chunks one by one:
        68 API calls × network latency = slow + risk of rate limiting

    If you batch 16 chunks per call:
        5 API calls × network latency = fast + safe
        (68 / 16 = 4.25, rounded up to 5 batches)

RAG CONCEPT — Idempotent Indexing:
    Running ingestion TWICE should NOT create duplicates.
    We achieve this with:
    1. Deterministic chunk IDs (same content → same ID)
    2. ChromaDB upsert (insert-or-update, not insert-and-duplicate)

    This means: update a PPT, re-run ingestion → old chunks replaced.

PHASE 2 MIGRATION NOTE:
    Replace ChromaDB with Azure AI Search:
    - Same concept: embed → store → search
    - Azure AI Search adds: hybrid search (vector + keyword), semantic ranking
    - Change only THIS module + retriever — rest of pipeline stays same

C# EQUIVALENT:
    Using Azure.Search.Documents SDK:
        var searchClient = new SearchClient(endpoint, indexName, credential);
        var batch = IndexDocumentsBatch.Upload(documents);
        await searchClient.IndexDocumentsAsync(batch);
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hashlib
import logging
import time
from typing import List, Dict, Any

import chromadb
from openai import AzureOpenAI

from src.ingestion.chunker import DocumentChunk

logger = logging.getLogger(__name__)


class VectorIndexer:
    """
    Handles embedding generation and ChromaDB storage.

    This is the BRIDGE between text processing and vector search.
    Everything before this deals with TEXT.
    Everything after this deals with VECTORS.
    """

    def __init__(
        self,
        azure_endpoint: str,
        azure_api_key: str,
        azure_api_version: str,
        embedding_deployment: str,
        chromadb_path: str,
        collection_name: str = "arch_knowledge",
    ):
        """
        Initialize connections to Azure OpenAI and ChromaDB.

        PYTHON CONCEPT — Dependency Injection:
            We pass in ALL configuration instead of reading it here.
            This makes the class:
            - Testable (pass mock clients in tests)
            - Flexible (same class works with different configs)
            - Clear (you can see all dependencies in __init__)

            C# equivalent:
                public VectorIndexer(
                    AzureOpenAIClient openaiClient,
                    ChromaDbClient chromaClient,
                    string collectionName
                ) { ... }
        """
        # Azure OpenAI client for generating embeddings
        self.openai_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
        )
        self.embedding_deployment = embedding_deployment

        # ChromaDB persistent client
        # PersistentClient = data survives app restarts (saved to disk)
        # In-memory client would lose everything on restart
        #
        # PYTHON CONCEPT — chromadb.PersistentClient:
        #   This creates a local database at the given path.
        #   Similar to SQLite — file-based, no separate server needed.
        #   Perfect for Phase 1 (single machine).
        #   Phase 2 replaces this with Azure AI Search (cloud service).
        self.chroma_client = chromadb.PersistentClient(path=chromadb_path)

        # Get or create the collection
        # "cosine" = similarity metric
        #   cosine measures the ANGLE between two vectors
        #   angle small → vectors point same direction → similar meaning
        #   This is the standard metric for text embeddings
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"VectorIndexer initialized. "
            f"Collection: {collection_name}, "
            f"Existing documents: {self.collection.count()}"
        )

    def _generate_chunk_id(self, chunk: DocumentChunk) -> str:
        """
        Generate a unique, DETERMINISTIC ID for a chunk.

        WHY deterministic (not random UUID)?
            If you re-ingest the same file:
            - Random UUID → creates DUPLICATE chunks
            - Deterministic ID → SAME ID → ChromaDB upserts (updates)

            This makes ingestion IDEMPOTENT:
            Run once = 68 chunks
            Run twice = still 68 chunks (not 136)

        ALGORITHM:
            ID = MD5 hash of (client + source_file + chunk_index)

            Same file, same chunk position → same ID → update, not duplicate

        PYTHON CONCEPT — hashlib.md5:
            MD5 creates a fixed-length hash from any input.
            Not secure for passwords, but perfect for deterministic IDs.
            .hexdigest() returns the hash as a readable hex string.

            C# equivalent:
                using var md5 = MD5.Create();
                var hash = md5.ComputeHash(Encoding.UTF8.GetBytes(input));
                return BitConverter.ToString(hash).Replace("-", "").ToLower();
        """
        id_string = (
            f"{chunk.metadata['client']}"
            f"_{chunk.metadata['source_file']}"
            f"_{chunk.metadata['chunk_index']}"
        )
        return hashlib.md5(id_string.encode()).hexdigest()

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        This calls Azure OpenAI's embedding API.
        Each text → 1536-dimensional vector (for text-embedding-3-small).

        WHAT HAPPENS INSIDE:
            "DataStories uses AWS for hosting"
                → Azure OpenAI processes this
                → Returns [0.0123, -0.0456, 0.0789, ..., 0.0321]
                   (1536 numbers that capture the MEANING)

        WHY BATCH?
            1 API call with 16 texts is faster than 16 API calls with 1 text each.
            Also avoids rate limiting.

        Args:
            texts: List of text strings to embed (max ~16 per batch)

        Returns:
            List of embedding vectors (each is 1536 floats)
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_deployment,
                input=texts,
            )
            # response.data is a list of embedding objects
            # Each has .embedding (the vector) and .index (position)
            embeddings = [item.embedding for item in response.data]
            return embeddings

        except Exception as e:
            logger.error(f"Embedding API error: {e}")
            raise

    def index_chunks(
        self,
        chunks: List[DocumentChunk],
        batch_size: int = 16,
    ) -> Dict[str, Any]:
        """
        Embed and store chunks in ChromaDB.

        THE INDEXING FLOW:
            1. Generate deterministic IDs for each chunk
            2. Process chunks in batches of 16
            3. For each batch:
               a. Call Azure OpenAI to get embeddings
               b. Upsert into ChromaDB (insert or update)
            4. Return statistics

        PYTHON CONCEPT — range(0, len, step):
            range(0, 68, 16) → [0, 16, 32, 48, 64]
            This gives us the START position of each batch.
            chunks[0:16], chunks[16:32], chunks[32:48], etc.

            C# equivalent:
                for (int i = 0; i < chunks.Count; i += batchSize)
                    var batch = chunks.Skip(i).Take(batchSize);

        Args:
            chunks: List of DocumentChunk objects to index
            batch_size: Chunks per API call (16 is safe for rate limits)

        Returns:
            Dict with: chunks_indexed, errors, total_in_collection
        """
        if not chunks:
            logger.warning("No chunks to index")
            return {"chunks_indexed": 0, "errors": 0, "total_in_collection": 0}

        logger.info(f"Indexing {len(chunks)} chunks in batches of {batch_size}...")

        total_indexed = 0
        total_errors = 0

        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(chunks) + batch_size - 1) // batch_size

            logger.info(
                f"  Batch {batch_num}/{total_batches}: "
                f"{len(batch)} chunks"
            )

            try:
                # Prepare batch data
                ids = [self._generate_chunk_id(c) for c in batch]
                texts = [c.content for c in batch]
                metadatas = [c.metadata for c in batch]

                # Generate embeddings via Azure OpenAI
                embeddings = self._embed_batch(texts)

                # Upsert into ChromaDB
                # UPSERT = INSERT if new, UPDATE if exists
                # This is what makes ingestion idempotent
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )

                total_indexed += len(batch)
                logger.info(f"  Batch {batch_num} ✅")

                # Rate limiting: small delay between batches
                # Prevents hitting Azure OpenAI's tokens-per-minute limit
                if i + batch_size < len(chunks):
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"  Batch {batch_num} ❌: {e}")
                total_errors += len(batch)

        result = {
            "chunks_indexed": total_indexed,
            "errors": total_errors,
            "total_in_collection": self.collection.count(),
        }

        logger.info(
            f"Indexing complete: {total_indexed} indexed, "
            f"{total_errors} errors, "
            f"{self.collection.count()} total in collection"
        )
        return result

    def delete_by_source(self, source_file: str) -> int:
        """
        Delete all chunks from a specific source file.

        WHY?
            When a PPT is updated, you need to:
            1. Delete OLD chunks (this method)
            2. Re-ingest the updated PPT
            This ensures the index always reflects the LATEST version.

        Args:
            source_file: Filename to delete chunks for

        Returns:
            Number of chunks deleted
        """
        try:
            results = self.collection.get(
                where={"source_file": source_file},
            )

            if results and results["ids"]:
                count = len(results["ids"])
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {count} chunks for: {source_file}")
                return count
            else:
                logger.info(f"No chunks found for: {source_file}")
                return 0

        except Exception as e:
            logger.error(f"Error deleting chunks for {source_file}: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Return statistics about the indexed collection.

        Useful for:
        - /stats API endpoint
        - Verifying ingestion worked
        - Monitoring index health
        """
        total = self.collection.count()

        if total == 0:
            return {
                "total_chunks": 0,
                "unique_clients": 0,
                "unique_files": 0,
                "clients": [],
                "files": [],
                "section_types": [],
            }

        # Get all metadata
        all_data = self.collection.get(include=["metadatas"])

        clients = set()
        files = set()
        section_types = set()

        if all_data and all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                if meta:
                    clients.add(meta.get("client", "unknown"))
                    files.add(meta.get("source_file", "unknown"))
                    section_types.add(meta.get("section_type", "unknown"))

        return {
            "total_chunks": total,
            "unique_clients": len(clients),
            "unique_files": len(files),
            "clients": sorted(list(clients)),
            "files": sorted(list(files)),
            "section_types": sorted(list(section_types)),
        }

    def get_clients(self) -> List[str]:
        """Return unique client names from the indexed collection."""
        stats = self.get_stats()
        return stats.get("clients", [])


# ── Standalone Testing ─────────────────────────────────────────
# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    from config.settings import get_settings
    settings = get_settings()

    from src.ingestion.scanner import DocumentScanner
    from src.ingestion.extractor import TextExtractor
    from src.ingestion.chunker import DocumentChunker

    print("=" * 60)
    print("Vector Indexer — Standalone Test")
    print("=" * 60)

    # ── Step 1: Scan + Extract + Chunk ──
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

    # ── Step 2: Initialize Indexer ──
    print("\n🔌 Connecting to Azure OpenAI + ChromaDB...")
    indexer = VectorIndexer(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_api_key=settings.azure_openai_api_key,
        azure_api_version=settings.azure_openai_api_version,
        embedding_deployment=settings.azure_openai_embedding_model,
        chromadb_path=str(settings.chromadb_dir),
        collection_name="arch_knowledge",
    )

    # ── Step 3: Index ──
    print("\n⚡ Embedding and indexing chunks...")
    result = indexer.index_chunks(all_chunks)

    print(f"\n{'=' * 60}")
    print(f"INDEXING RESULTS:")
    print(f"  Chunks indexed:       {result['chunks_indexed']}")
    print(f"  Errors:               {result['errors']}")
    print(f"  Total in collection:  {result['total_in_collection']}")
    print(f"{'=' * 60}")

    # ── Step 4: Show stats ──
    stats = indexer.get_stats()
    print(f"\n📊 Index Statistics:")
    print(f"  Total chunks:    {stats['total_chunks']}")
    print(f"  Clients:         {stats['clients']}")
    print(f"  Files:           {stats['unique_files']}")
    print(f"  Section types:   {stats['section_types']}")
    print(f"{'=' * 60}")