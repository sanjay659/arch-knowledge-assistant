"""
Ingestion Pipeline — End-to-end document ingestion orchestrator
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any

from config.settings import get_settings
from src.ingestion.scanner import DocumentScanner
from src.ingestion.extractor import TextExtractor
from src.ingestion.chunker import DocumentChunker
from src.indexing.indexer import VectorIndexer

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    files_processed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    processing_time: float = 0.0
    details: List[Dict[str, Any]] = field(default_factory=list)


class IngestionPipeline:

    def __init__(self):
        settings = get_settings()

        self.scanner = DocumentScanner(str(settings.documents_dir))
        self.extractor = TextExtractor()
        self.chunker = DocumentChunker(
            min_length=settings.min_chunk_length,
            max_length=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        self.indexer = VectorIndexer(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_api_key=settings.azure_openai_api_key,
            azure_api_version=settings.azure_openai_api_version,
            embedding_deployment=settings.azure_openai_embedding_model,
            chromadb_path=str(settings.chromadb_dir),
            collection_name="arch_knowledge",
        )
        logger.info("IngestionPipeline initialized")

    def run(self) -> IngestionReport:
        start_time = time.time()
        report = IngestionReport()

        logger.info("=" * 60)
        logger.info("INGESTION PIPELINE — Starting")
        logger.info("=" * 60)

        # Step 1: Scan
        documents = self.scanner.scan()
        if not documents:
            logger.warning("No documents found!")
            report.processing_time = time.time() - start_time
            return report

        logger.info(f"Found {len(documents)} documents")

        # Step 2: Process each document
        for doc_info in documents:
            logger.info(f"\nProcessing: {doc_info.file_name} (client: {doc_info.client_name})")

            try:
                # Extract
                slides = self.extractor.extract(doc_info.file_path)
                if not slides:
                    report.files_skipped += 1
                    continue

                # Chunk
                chunks = self.chunker.chunk_document(
                    slides=slides,
                    client_name=doc_info.client_name,
                    source_file=doc_info.file_name,
                    file_type=doc_info.file_type,
                )
                if not chunks:
                    report.files_skipped += 1
                    continue

                # Delete old chunks (for re-indexing)
                self.indexer.delete_by_source(doc_info.file_name)

                # Index new chunks
                index_result = self.indexer.index_chunks(chunks)

                report.files_processed += 1
                report.chunks_created += index_result["chunks_indexed"]
                report.details.append({
                    "file": doc_info.file_name,
                    "client": doc_info.client_name,
                    "slides": len(slides),
                    "chunks": index_result["chunks_indexed"],
                    "status": "success",
                })

                logger.info(
                    f"  ✅ {doc_info.file_name}: "
                    f"{len(slides)} slides → {index_result['chunks_indexed']} chunks"
                )

            except Exception as e:
                logger.error(f"  ❌ Error: {e}")
                report.errors.append({
                    "file": doc_info.file_name,
                    "error": str(e),
                })

        report.processing_time = time.time() - start_time

        logger.info(f"\n{'=' * 60}")
        logger.info(f"INGESTION COMPLETE")
        logger.info(f"  Files: {report.files_processed} | Chunks: {report.chunks_created} | Errors: {len(report.errors)} | Time: {report.processing_time:.2f}s")
        logger.info(f"{'=' * 60}")

        return report