"""
Document Chunker — Splits documents into retrieval-ready chunks
================================================================

WHAT THIS MODULE DOES:
    Takes cleaned slides/pages → Returns chunks with rich metadata.
    
    This is the LAST step before content enters the vector database.
    After this, each chunk gets embedded and stored.

WHY THIS IS THE MOST IMPORTANT MODULE:
    The chunker determines WHAT the retriever can find.
    
    If important info is split across two chunks → retriever may miss half.
    If unrelated topics are in one chunk → retriever gets noise.
    If metadata is wrong → filtered retrieval returns wrong results.
    
    Every decision here directly impacts answer quality.

THE THREE OPERATIONS:
    ┌─────────────────────────────────────────────────────────┐
    │                                                         │
    │  1. MERGE (small slides → combined chunk)               │
    │     Slide 4: "Hosting Overview" (200 chars)             │
    │     Slide 5: "Integration Process..." (890 chars)       │
    │     → Merged chunk: 1090 chars, slides "4-5"            │
    │                                                         │
    │  2. KEEP (right-sized slides → chunk as-is)             │
    │     Slide 13: "Budget Details..." (880 chars)           │
    │     → Chunk: 880 chars, slide "13"                      │
    │                                                         │
    │  3. SPLIT (large slides → sub-chunks with overlap)      │
    │     Slide 99: "Very long content..." (2500 chars)       │
    │     → Sub-chunk A: 0-1500 chars, slide "99"             │
    │     → Sub-chunk B: 1350-2500 chars, slide "99"          │
    │                                                         │
    └─────────────────────────────────────────────────────────┘

PYTHON CONCEPTS COVERED:
    - dataclass with Dict type
    - datetime with timezone
    - List of tuples
    - Accumulator pattern (collecting items then flushing)
    - String slicing with overlap

C# EQUIVALENTS:
    - DocumentChunk dataclass → C# record
    - List[tuple] → List<(string, List<int>, string)>
    - Accumulator pattern → same in C# (StringBuilder pattern)
    - datetime.now(timezone.utc) → DateTime.UtcNow
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict, Any

from src.ingestion.extractor import SlideContent
from src.ingestion.preprocessor import TextPreprocessor

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """
    A single chunk ready for embedding and storage.

    This is the FINAL data structure before the vector database.

    WHY separate content from metadata?
        content  → gets EMBEDDED (converted to vector)
        metadata → gets STORED alongside the vector for FILTERING

        When someone asks "Explain DataStories architecture":
        1. "DataStories" → used to FILTER by metadata.client
        2. "architecture" → used to SEARCH by content similarity

        Without metadata, you can only search.
        With metadata, you can search AND filter.

    C# equivalent:
        public record DocumentChunk(
            string Content,
            Dictionary<string, object> Metadata
        );
    """
    content: str                    # The text to embed
    metadata: Dict[str, Any]        # Structured metadata for filtering


class DocumentChunker:
    """
    Converts cleaned document content into retrieval-ready chunks.

    DESIGN PRINCIPLE: Structure-aware chunking
        We don't blindly split at every N characters.
        We respect the document's own structure:
        - PPT: slide boundaries
        - PDF: page boundaries
        - DOCX: heading boundaries

        Then we apply merge/split rules on top.
    """

    def __init__(
        self,
        min_length: int = 100,
        max_length: int = 1500,
        overlap: int = 150,
    ):
        """
        Args:
            min_length: Chunks below this → merge with next
                       (100 chars ≈ 25 tokens)
            max_length: Chunks above this → split with overlap
                       (1500 chars ≈ 375 tokens)
            overlap:    When splitting, overlap by this many chars
                       (150 chars ≈ 37 tokens ≈ 2-3 sentences)
        """
        self.min_length = min_length
        self.max_length = max_length
        self.overlap = overlap
        self.preprocessor = TextPreprocessor()

    def chunk_document(
        self,
        slides: List[SlideContent],
        client_name: str,
        source_file: str,
        file_type: str,
    ) -> List[DocumentChunk]:
        """
        Convert a list of slides into chunks with metadata.

        THE FULL CHUNKING FLOW:
            1. Clean each slide (remove boilerplate)
            2. Filter out non-meaningful slides
            3. Apply merge/split logic
            4. Attach metadata to each chunk
            5. Return list of DocumentChunk

        Args:
            slides: Raw SlideContent objects from the extractor
            client_name: Client name (from folder structure)
            source_file: Original filename (for citations)
            file_type: File extension (.pptx, .pdf, .docx)

        Returns:
            List of DocumentChunk objects ready for embedding
        """
        logger.info(
            f"  Chunking {len(slides)} slides from {source_file} "
            f"(client: {client_name})"
        )

        # ── Step 1: Clean and filter slides ──
        # Remove boilerplate, skip meaningless slides
        cleaned_slides = []
        for slide in slides:
            cleaned_content = self.preprocessor.clean_text(slide.content)
            cleaned_title = self.preprocessor.clean_title(slide.title)

            if self.preprocessor.is_meaningful(cleaned_content):
                cleaned_slides.append(SlideContent(
                    slide_number=slide.slide_number,
                    title=cleaned_title,
                    content=cleaned_content,
                    has_table=slide.has_table,
                    table_data=slide.table_data,
                ))
            else:
                logger.debug(
                    f"    Slide {slide.slide_number}: skipped "
                    f"(not meaningful after cleaning)"
                )

        logger.info(
            f"  After cleaning: {len(cleaned_slides)} meaningful slides "
            f"(removed {len(slides) - len(cleaned_slides)})"
        )

        # ── Step 2: Apply merge/split logic ──
        # This is where the chunk size rules are applied
        merged_chunks = self._merge_and_split(cleaned_slides)

        # ── Step 3: Create DocumentChunk objects with metadata ──
        ingestion_time = datetime.now(timezone.utc).isoformat()
        total_chunks = len(merged_chunks)

        document_chunks = []
        for idx, (content, slide_nums, title) in enumerate(merged_chunks):

            # Detect section type from content and title
            section_type = self.preprocessor.detect_section_type(
                content, title
            )

            # Build slide_number string for citations
            # Single slide: "5"
            # Merged slides: "4-5"
            # This appears in citations as [Source: file.pptx, Slide 4-5]
            if len(slide_nums) == 1:
                slide_str = str(slide_nums[0])
            else:
                slide_str = f"{slide_nums[0]}-{slide_nums[-1]}"

            chunk = DocumentChunk(
                content=content,
                metadata={
                    "client": client_name,
                    "source_file": source_file,
                    "file_type": file_type,
                    "slide_number": slide_str,
                    "section_type": section_type,
                    "chunk_index": idx,
                    "total_chunks": total_chunks,
                    "ingested_at": ingestion_time,
                    "title": title,
                }
            )
            document_chunks.append(chunk)

            logger.debug(
                f"    Chunk {idx}: slides {slide_str}, "
                f"type={section_type}, {len(content)} chars"
            )

        logger.info(f"  Created {len(document_chunks)} chunks")
        return document_chunks

    def _merge_and_split(
        self, slides: List[SlideContent]
    ) -> List[tuple]:
        """
        Apply merge (small) and split (large) logic to slides.

        Returns:
            List of tuples: (content_text, [slide_numbers], title)

        THE ALGORITHM (Accumulator Pattern):
        ─────────────────────────────────────────────────
        Walk through slides one by one.
        Maintain an "accumulator" for merging small slides.

        For each slide:
            IF too short (< min_length):
                → Add to accumulator (merge with next)
                → If accumulator is now big enough → flush it as a chunk

            IF too long (> max_length):
                → Flush any accumulated text first
                → Split this slide into sub-chunks with overlap

            IF just right (between min and max):
                → If accumulator has text → merge accumulator + this slide → flush
                → If accumulator empty → emit this slide as a standalone chunk

        At the end: flush any remaining accumulated text.

        PYTHON CONCEPT — Accumulator Pattern:
            This is like StringBuilder in C#:
            - Collect small pieces
            - Flush when big enough
            - Don't lose anything at the end

            C# equivalent:
                var sb = new StringBuilder();
                foreach (var slide in slides) {
                    if (slide.Length < minLength) {
                        sb.Append(slide);
                        if (sb.Length >= minLength) {
                            result.Add(sb.ToString());
                            sb.Clear();
                        }
                    }
                    ...
                }
                if (sb.Length > 0) result.Add(sb.ToString()); // Don't forget!
        """
        result = []

        # Accumulator for merging small slides
        acc_text = ""           # Accumulated text
        acc_slides = []         # Which slide numbers are accumulated
        acc_title = ""          # Title of first accumulated slide

        for slide in slides:
            text = slide.content
            text_length = len(text)

            # ── CASE 1: Slide is TOO LONG → split ──
            if text_length > self.max_length:

                # First, flush any accumulated small slides
                if acc_text:
                    result.append((acc_text, acc_slides[:], acc_title))
                    acc_text = ""
                    acc_slides = []
                    acc_title = ""

                # Split this large slide into sub-chunks
                sub_chunks = self._split_text(
                    text, slide.slide_number, slide.title
                )
                result.extend(sub_chunks)

            # ── CASE 2: Slide is TOO SHORT → accumulate ──
            elif text_length < self.min_length:

                # Add to accumulator
                if acc_text:
                    acc_text += "\n\n" + text
                else:
                    acc_text = text
                    acc_title = slide.title
                acc_slides.append(slide.slide_number)

                # If accumulated text is now big enough, flush it
                if len(acc_text) >= self.min_length:
                    result.append((acc_text, acc_slides[:], acc_title))
                    acc_text = ""
                    acc_slides = []
                    acc_title = ""

            # ── CASE 3: Slide is JUST RIGHT → keep ──
            else:
                if acc_text:
                    # Merge accumulated small text with this slide
                    combined = acc_text + "\n\n" + text
                    acc_slides.append(slide.slide_number)

                    # Check if merged text needs splitting
                    if len(combined) > self.max_length:
                        # Flush accumulator as one chunk
                        result.append((acc_text, acc_slides[:-1], acc_title))
                        # Keep this slide as separate chunk
                        result.append((text, [slide.slide_number], slide.title))
                    else:
                        result.append((combined, acc_slides[:], acc_title))

                    acc_text = ""
                    acc_slides = []
                    acc_title = ""
                else:
                    # No accumulated text — emit this slide as-is
                    result.append((text, [slide.slide_number], slide.title))

        # ── Don't forget remaining accumulated text! ──
        # This is a VERY COMMON BUG in accumulator patterns.
        # If the last few slides were all small, they're still
        # in the accumulator. Flush them now.
        if acc_text:
            result.append((acc_text, acc_slides[:], acc_title))

        return result

    def _split_text(
        self, text: str, slide_number: int, title: str
    ) -> List[tuple]:
        """
        Split a long text into sub-chunks with overlap.

        This handles the case where a single slide has more text
        than CHUNK_MAX_LENGTH (1500 chars).

        ALGORITHM:
            1. Start at position 0
            2. Take max_length characters
            3. Look backwards for a natural break point (newline, period, space)
            4. Emit that as a sub-chunk
            5. Move forward by (chunk_length - overlap) characters
            6. Repeat until end of text

        WHY look for natural break points?
            Splitting at exactly 1500 chars might cut mid-word:
                "...the API Gate" | "way connects to..."
            
            Looking backwards for a newline or period gives:
                "...the API Gateway." | "After validation, the request..."
            
            Much better for both embedding quality and readability.

        PYTHON CONCEPT — String slicing:
            text[start:end]  → characters from position start to end-1
            text[10:50]      → characters 10 through 49
            text.rfind("\n", start, end) → find LAST newline between start and end

            C# equivalent:
                text.Substring(start, length)
                text.LastIndexOf('\n', end, end - start)

        Returns:
            List of tuples: (sub_chunk_text, [slide_number], title)
        """
        chunks = []
        start = 0
        part_idx = 0

        while start < len(text):
            # Calculate end position
            end = start + self.max_length

            if end >= len(text):
                # Last sub-chunk — take everything remaining
                chunk_text = text[start:]
            else:
                # Try to find a natural break point
                # Priority: newline > period+space > space > hard cut

                # Look for last newline in the range
                break_point = text.rfind("\n", start, end)

                # If no newline, look for last period+space
                if break_point == -1 or break_point <= start:
                    break_point = text.rfind(". ", start, end)
                    if break_point != -1:
                        break_point += 1  # Include the period

                # If no period, look for last space
                if break_point == -1 or break_point <= start:
                    break_point = text.rfind(" ", start, end)

                # If no space at all (very long word?), hard cut
                if break_point == -1 or break_point <= start:
                    break_point = end

                chunk_text = text[start:break_point + 1]

            chunk_text = chunk_text.strip()

            if chunk_text:
                # Add part number to title for multi-part chunks
                part_title = title
                if part_idx > 0 and title:
                    part_title = f"{title} (part {part_idx + 1})"

                chunks.append((chunk_text, [slide_number], part_title))
                part_idx += 1

            # Move start forward
            # Key: we DON'T start from where we left off.
            # We go back by 'overlap' characters so content is repeated.
            next_start = start + len(chunk_text)
            if next_start < len(text):
                # Apply overlap — go back by overlap amount
                next_start = max(start + 1, next_start - self.overlap)
            start = next_start

        logger.debug(
            f"    Split slide {slide_number} into {len(chunks)} sub-chunks"
        )
        return chunks


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.ingestion.scanner import DocumentScanner
    from src.ingestion.extractor import TextExtractor

    print("=" * 60)
    print("Document Chunker — Standalone Test")
    print("=" * 60)

    # Step 1: Scan for documents
    scanner = DocumentScanner("data/documents")
    documents = scanner.scan()

    if not documents:
        print("\n❌ No documents found in data/documents/")
        sys.exit(1)

    extractor = TextExtractor()
    chunker = DocumentChunker(
        min_length=100,
        max_length=1500,
        overlap=150,
    )

    total_chunks = 0

    for doc in documents:
        print(f"\n{'─' * 50}")
        print(f"📄 {doc.client_name}/{doc.file_name}")
        print(f"{'─' * 50}")

        # Extract
        slides = extractor.extract(doc.file_path)
        print(f"  Extracted: {len(slides)} slides")

        # Chunk
        chunks = chunker.chunk_document(
            slides=slides,
            client_name=doc.client_name,
            source_file=doc.file_name,
            file_type=doc.file_type,
        )

        total_chunks += len(chunks)

        # Display chunks
        for chunk in chunks:
            meta = chunk.metadata
            preview = chunk.content[:100].replace('\n', ' ')
            print(
                f"\n  📦 Chunk {meta['chunk_index']}: "
                f"Slide {meta['slide_number']} | "
                f"Type: {meta['section_type']} | "
                f"{len(chunk.content)} chars"
            )
            print(f"     Title: {meta['title'] or '(none)'}")
            print(f"     Preview: {preview}...")

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_chunks} chunks from {len(documents)} files")
    print(f"{'=' * 60}")