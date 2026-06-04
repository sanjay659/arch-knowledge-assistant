"""
Text Extractor — Extracts readable text from PPT, PDF, and DOCX files
======================================================================

WHAT THIS MODULE DOES:
    Takes a file path → Returns structured text content per slide/page.

    This is the BRIDGE between:
        Binary files (PPT, PDF)  →  Text that can be chunked and embedded

WHY THIS IS THE HARDEST PART OF RAG:
    Most RAG tutorials use clean text files or markdown.
    Real enterprise documents are MESSY:

    1. PPTs have text scattered across shapes, tables, and notes
    2. PDFs may have multi-column layouts, headers, footers
    3. Architecture diagrams are IMAGES — text is NOT extractable
    4. Tables contain critical data (server lists, port mappings)
       but are stored as grid structures, not flowing text
    5. Boilerplate (copyright, page numbers) pollutes the content

    The quality of extraction DIRECTLY determines:
    - How good your chunks will be
    - How accurate your retrieval will be
    - How correct your final answers will be

    Rule: Garbage extraction → Garbage answers (no matter how good GPT is)

LIBRARIES USED:
    python-pptx  → PowerPoint (.pptx) extraction
    PyMuPDF      → PDF (.pdf) extraction (imported as 'fitz')
    python-docx  → Word (.docx) extraction

    WHY THESE SPECIFIC LIBRARIES?
    ┌─────────────┬──────────────┬───────────────────────────────┐
    │ Library     │ Alternatives │ Why we chose this one         │
    ├─────────────┼──────────────┼───────────────────────────────┤
    │ python-pptx │ comtypes,    │ Pure Python, no MS Office     │
    │             │ Aspose       │ needed, good shape/table API  │
    ├─────────────┼──────────────┼───────────────────────────────┤
    │ PyMuPDF     │ PyPDF2,      │ 10x faster, better Unicode,  │
    │ (fitz)      │ pdfplumber   │ handles complex layouts       │
    ├─────────────┼──────────────┼───────────────────────────────┤
    │ python-docx │ docx2txt,    │ Full paragraph + style access │
    │             │ mammoth      │ heading detection for sections │
    └─────────────┴──────────────┴───────────────────────────────┘

PHASE 2 MIGRATION NOTE:
    Replace all three libraries with Azure Document Intelligence:
    - Layout API → structure-aware extraction (tables, sections)
    - Read API → OCR on images (can read text from diagrams!)
    - One API handles PPT, PDF, DOCX, and even scanned documents

    That's the single biggest quality jump in Phase 2.

C# EQUIVALENT:
    In .NET you'd use:
    - DocumentFormat.OpenXml (for PPTX/DOCX — same concept as python-pptx)
    - iTextSharp or PdfSharp (for PDF)
    - Azure AI Document Intelligence SDK (same as Phase 2)
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


# ── SlideContent — Output Data Structure ──────────────────────
#
# PYTHON CONCEPT — field(default_factory=list):
#   Mutable default values in dataclasses need special handling.
#
#   This would be a BUG:
#       @dataclass
#       class SlideContent:
#           table_data: list = []  # ❌ ALL instances share the SAME list!
#
#   This is correct:
#       table_data: List[List[str]] = field(default_factory=list)  # ✅ Each gets its OWN list
#
#   WHY? Python evaluates default values ONCE at class definition time.
#   So `= []` creates ONE list object shared by ALL instances.
#   `field(default_factory=list)` calls `list()` each time → new list per instance.
#
#   C# doesn't have this problem because properties are initialized per instance.
#   But in Python, this is a VERY common gotcha.

@dataclass
class SlideContent:
    """
    Represents extracted content from a single slide (PPT) or page (PDF).

    WHY track each of these fields?

    slide_number:
        Enables precise citations: "[Source: blueprint.pptx, Slide 5]"
        Users can then open the PPT and verify on that exact slide.

    title:
        Slide titles are SEMANTICALLY important — they often describe
        the topic better than the body text.
        "Existing Hosting - Overview" tells us this is about current state.
        The preprocessor uses this for section_type detection.

    content:
        The full text of the slide. This is what gets chunked and embedded.

    has_table:
        Tables in architecture decks contain CRITICAL data:
        - Server inventories
        - Port mappings
        - Cost breakdowns
        - Support matrices
        Knowing a chunk has table data helps with special processing.

    table_data:
        The actual table rows/cells as a list of lists.
        Example: [["TYPE", "DESTINATION"], ["Public Cloud", "AWS account..."]]
        We convert this to text for embedding, but keep the raw data too.
    """
    slide_number: int                                       # 1-based index
    title: str                                              # Slide/page title
    content: str                                            # Full text content
    has_table: bool = False                                 # Contains a table?
    table_data: List[List[str]] = field(default_factory=list)  # Raw table rows


class TextExtractor:
    """
    Extracts text from PPT, PDF, and DOCX files.

    DESIGN PRINCIPLE:
        Extract MAXIMUM information now, clean up LATER.
        The preprocessor (next step) handles cleaning.

        Why? Because it's easier to REMOVE noise than to
        go back and RE-EXTRACT missing information.

    PYTHON CONCEPT — Dispatcher Pattern:
        The extract() method looks at the file extension and calls
        the right private method. This is like a Strategy pattern:

            .pptx → _extract_pptx()
            .pdf  → _extract_pdf()
            .docx → _extract_docx()

        C# equivalent: You might use a switch expression:
            return ext switch {
                ".pptx" => ExtractPptx(path),
                ".pdf"  => ExtractPdf(path),
                ".docx" => ExtractDocx(path),
                _ => throw new NotSupportedException()
            };
    """

    def extract(self, file_path: str) -> List[SlideContent]:
        """
        Main extraction method — dispatches to the right extractor.

        Args:
            file_path: Full path to the document file

        Returns:
            List of SlideContent objects (one per slide/page/section)
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        logger.info(f"Extracting: {path.name} (type: {ext})")

        # PYTHON CONCEPT — Dictionary dispatch (alternative to if/elif):
        #   Instead of:
        #       if ext == ".pptx": return self._extract_pptx(...)
        #       elif ext == ".pdf": return self._extract_pdf(...)
        #
        #   You could also do:
        #       extractors = {".pptx": self._extract_pptx, ".pdf": self._extract_pdf}
        #       return extractors[ext](file_path)
        #
        #   We use if/elif here for clarity since there are only 3 options.

        if ext == ".pptx":
            return self._extract_pptx(file_path)
        elif ext == ".pdf":
            return self._extract_pdf(file_path)
        elif ext == ".docx":
            return self._extract_docx(file_path)
        else:
            logger.error(f"Unsupported file type: {ext}")
            return []

    # ──────────────────────────────────────────────────────────
    # PPT Extraction (.pptx)
    # ──────────────────────────────────────────────────────────

    def _extract_pptx(self, file_path: str) -> List[SlideContent]:
        """
        Extract text from a PowerPoint presentation, slide by slide.

        HOW python-pptx WORKS:
            A PPTX file is actually a ZIP containing XML files.
            python-pptx parses this XML and gives us Python objects.

            Hierarchy:
                Presentation
                └── Slides (list)
                    └── Shapes (list) — everything on a slide is a "shape"
                        ├── TextFrame shapes — text boxes, titles, bullets
                        ├── Table shapes — grid data
                        ├── Picture shapes — images (we can't extract text from these)
                        ├── Chart shapes — graphs
                        └── Group shapes — grouped objects

        EXTRACTION STRATEGY:
            For each slide:
            1. Try to find the TITLE (placeholder with title type)
            2. Extract ALL text from ALL shapes
            3. Extract TABLE data separately (and also add as text)
            4. Track slide number for citations

        WHY per-slide extraction?
            Architecture PPTs typically organize content by slide:
            - Slide 3: Executive Summary
            - Slide 9: Existing Hosting Overview
            - Slide 11: Target Reference Architecture
            - Slide 13: Budget Details

            Slide boundaries = natural chunk boundaries.
            This is MUCH better than treating the entire PPT as one blob.

        WHAT WE CAN'T EXTRACT:
            ❌ Text inside images/diagrams (needs OCR → Phase 2)
            ❌ SmartArt text (sometimes works, sometimes doesn't)
            ❌ Text in grouped shapes (partially works)
            ❌ Animations/transitions (irrelevant for RAG)

        C# EQUIVALENT:
            Using DocumentFormat.OpenXml:
                var prs = PresentationDocument.Open(path, false);
                var slideParts = prs.PresentationPart.SlideParts;
                foreach (var slidePart in slideParts) {
                    var texts = slidePart.Slide.Descendants<Text>();
                    ...
                }
        """
        from pptx import Presentation

        slides_content = []

        try:
            prs = Presentation(file_path)

            # PYTHON CONCEPT — enumerate(iterable, start=1):
            #   Gives you both the INDEX and the ITEM in a loop.
            #
            #   Without enumerate:
            #       slide_idx = 0
            #       for slide in prs.slides:
            #           slide_idx += 1
            #           ...
            #
            #   With enumerate:
            #       for slide_idx, slide in enumerate(prs.slides, start=1):
            #           ...
            #
            #   start=1 makes it 1-based (Slide 1, not Slide 0)
            #   because humans think in 1-based slide numbers.
            #
            #   C# equivalent:
            #       foreach (var (slide, index) in slides.Select((s, i) => (s, i + 1)))

            for slide_idx, slide in enumerate(prs.slides, start=1):
                title = ""
                body_texts = []
                has_table = False
                table_data = []

                # Iterate through all shapes on this slide
                for shape in slide.shapes:
                    try:

                        # ── Extract text from text frames ──
                        # ── Extract text from text frames ──
                        if shape.has_text_frame:
                            text = shape.text_frame.text.strip()
                            if not text:
                                continue

                            # Check if this shape is a title placeholder.
                            # BUG FIX: python-pptx raises ValueError when you
                            # access .placeholder_format on non-placeholder shapes.
                            # The attribute EXISTS (hasattr returns True) but
                            # ACCESSING it throws an error. This is a library quirk.
                            #
                            # Solution: wrap the ENTIRE check in try/except ValueError.
                            is_title = False
                            try:
                                ph_format = shape.placeholder_format
                                if ph_format is not None:
                                    ph_type = ph_format.type
                                    if ph_type is not None and ph_type in (0, 1, 13, 15):
                                        title = text
                                        is_title = True
                            except (ValueError, AttributeError, KeyError):
                                # Not a placeholder shape — that's perfectly fine.
                                # Most shapes on a slide are NOT placeholders.
                                pass

                            if not is_title:
                                body_texts.append(text)

                        # ── Extract table data ──
                        # Tables in architecture decks contain critical info:
                        # - Server inventories
                        # - Integration endpoints
                        # - Cost breakdowns
                        # - Support matrices
                        #
                        # We extract tables in TWO ways:
                        # 1. Raw data (list of lists) → stored in table_data
                        # 2. Text representation → added to body_texts for embedding
                        if shape.has_table:
                            has_table = True
                            table = shape.table

                            for row in table.rows:
                                row_data = []
                                for cell in row.cells:
                                    cell_text = cell.text.strip()
                                    if cell_text:
                                        row_data.append(cell_text)
                                if row_data:
                                    table_data.append(row_data)

                            # Convert table to pipe-delimited text for embedding
                            # Example: "TYPE | DESTINATION\nPublic Cloud | AWS account..."
                            #
                            # WHY pipe-delimited?
                            #   The embedding model needs TEXT, not grid structures.
                            #   Pipes visually separate columns while keeping
                            #   the data as a readable string.
                            table_text = "\n".join(
                                " | ".join(row) for row in table_data
                            )
                            if table_text:
                                body_texts.append(f"[Table]\n{table_text}")
                    
                    except Exception as e:
                        # One bad shape should NOT skip the entire slide
                        logger.debug(
                            f"  Slide {slide_idx}: skipped a shape due to: {e}"
                        )
                        continue

                # ── Combine all text for this slide ──
                full_content = ""
                if title:
                    full_content = f"{title}\n"
                if body_texts:
                    full_content += "\n".join(body_texts)

                full_content = full_content.strip()

                # Only create SlideContent if there's actual text
                # Slides with only images/diagrams will have no text
                if full_content:
                    slides_content.append(SlideContent(
                        slide_number=slide_idx,
                        title=title,
                        content=full_content,
                        has_table=has_table,
                        table_data=table_data,
                    ))
                    logger.debug(
                        f"  Slide {slide_idx}: {len(full_content)} chars"
                        f"{'  [has table]' if has_table else ''}"
                    )
                else:
                    # This slide had no extractable text
                    # Common for: title slides with only logos,
                    # diagram-only slides, transition slides
                    logger.debug(f"  Slide {slide_idx}: empty/image-only, skipped")

            logger.info(
                f"  Extracted {len(slides_content)} slides with content "
                f"from {Path(file_path).name}"
            )

        except Exception as e:
            logger.error(f"  Error extracting PPT {file_path}: {e}")

        return slides_content

    # ──────────────────────────────────────────────────────────
    # PDF Extraction (.pdf)
    # ──────────────────────────────────────────────────────────

    def _extract_pdf(self, file_path: str) -> List[SlideContent]:
        """
        Extract text from a PDF document, page by page.

        LIBRARY: PyMuPDF (imported as 'fitz')
            WHY 'fitz'? PyMuPDF is built on top of MuPDF, which was
            created by Artifex Software. The Python binding kept the
            internal name 'fitz' for historical reasons.

            So: pip install PyMuPDF → import fitz  (confusing, but standard)

        STRATEGY:
            1. Open PDF with fitz
            2. Extract text per page (like per slide for PPTs)
            3. Use first line as title (basic heuristic)
            4. Close the document when done

        PDF EXTRACTION CHALLENGES:
            - Multi-column layouts → text may come out in wrong order
            - Headers/footers → repeated on every page
            - Tables → extracted as plain text (columns may misalign)
            - Scanned PDFs → NO text at all (needs OCR → Phase 2)

        C# EQUIVALENT:
            Using iTextSharp:
                var reader = new PdfReader(path);
                for (int i = 1; i <= reader.NumberOfPages; i++) {
                    var text = PdfTextExtractor.GetTextFromPage(reader, i);
                }
        """
        import fitz  # PyMuPDF

        pages_content = []

        try:
            # PYTHON CONCEPT — Context manager pattern:
            #   You COULD write:
            #       doc = fitz.open(file_path)
            #       ... do stuff ...
            #       doc.close()
            #
            #   But if an error happens before close(), the file stays open.
            #   We manually close here, but in Phase 2 you'd use:
            #       with fitz.open(file_path) as doc:
            #           ... guaranteed to close even on error ...
            #
            #   C# equivalent: using (var doc = ...) { ... }

            doc = fitz.open(file_path)

            for page_idx in range(len(doc)):
                page = doc[page_idx]

                # get_text("text") extracts plain text preserving reading order
                # Other options:
                #   "blocks" → text blocks with position info
                #   "dict"   → full structure (fonts, sizes, positions)
                #   "html"   → HTML formatted text
                text = page.get_text("text").strip()

                if text:
                    # Simple title detection: use first short line
                    lines = text.split("\n")
                    title = ""
                    if lines and len(lines[0].strip()) < 100:
                        title = lines[0].strip()

                    pages_content.append(SlideContent(
                        slide_number=page_idx + 1,  # 1-based
                        title=title,
                        content=text,
                        has_table=False,  # Basic; Phase 2 uses Doc Intelligence
                        table_data=[],
                    ))
                    logger.debug(f"  Page {page_idx + 1}: {len(text)} chars")

            doc.close()

            logger.info(
                f"  Extracted {len(pages_content)} pages "
                f"from {Path(file_path).name}"
            )

        except Exception as e:
            logger.error(f"  Error extracting PDF {file_path}: {e}")

        return pages_content

    # ──────────────────────────────────────────────────────────
    # DOCX Extraction (.docx)
    # ──────────────────────────────────────────────────────────

    def _extract_docx(self, file_path: str) -> List[SlideContent]:
        """
        Extract text from a Word document, grouped by headings.

        STRATEGY:
            Word docs have natural section boundaries defined by HEADINGS.
            Each heading starts a new "section" in our extraction.

            Document:
                # Executive Summary          ← Heading → new section
                This is the summary text...

                # Current Architecture       ← Heading → new section
                The current system uses...

            Becomes:
                SlideContent(1, "Executive Summary", "This is the summary...")
                SlideContent(2, "Current Architecture", "The current system...")

        WHY heading-based sectioning?
            - Headings indicate TOPIC changes
            - Each topic = good chunk boundary
            - Heading text = useful title metadata

        FALLBACK:
            If no headings found → treat entire document as one section.

        C# EQUIVALENT:
            Using DocumentFormat.OpenXml:
                var doc = WordprocessingDocument.Open(path, false);
                var body = doc.MainDocumentPart.Document.Body;
                foreach (var para in body.Elements<Paragraph>()) {
                    var style = para.ParagraphProperties?.ParagraphStyleId?.Val;
                    if (style?.Value?.StartsWith("Heading") == true) { ... }
                }
        """
        from docx import Document

        sections_content = []

        try:
            doc = Document(file_path)

            current_title = ""
            current_text_parts = []
            section_idx = 0

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                # Check if this paragraph is a heading
                # Word styles: "Heading 1", "Heading 2", "Heading 3", etc.
                style_name = para.style.name if para.style else ""
                is_heading = style_name.startswith("Heading")

                if is_heading:
                    # Save previous section (if it has content)
                    if current_text_parts:
                        section_idx += 1
                        sections_content.append(SlideContent(
                            slide_number=section_idx,
                            title=current_title,
                            content="\n".join(current_text_parts),
                        ))

                    # Start new section with this heading
                    current_title = text
                    current_text_parts = [text]
                else:
                    current_text_parts.append(text)

            # Don't forget the last section
            if current_text_parts:
                section_idx += 1
                sections_content.append(SlideContent(
                    slide_number=section_idx,
                    title=current_title,
                    content="\n".join(current_text_parts),
                ))

            # Fallback: if no headings found, entire doc = one section
            if not sections_content and doc.paragraphs:
                all_text = "\n".join(
                    p.text.strip() for p in doc.paragraphs if p.text.strip()
                )
                if all_text:
                    sections_content.append(SlideContent(
                        slide_number=1,
                        title="",
                        content=all_text,
                    ))

            logger.info(
                f"  Extracted {len(sections_content)} sections "
                f"from {Path(file_path).name}"
            )

        except Exception as e:
            logger.error(f"  Error extracting DOCX {file_path}: {e}")

        return sections_content


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("Text Extractor — Standalone Test")
    print("=" * 60)

    # Test with a file path from command line or default
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        # Default: look for DataStories PPT
        test_file = "data/documents/DataStories/Datastories Hosting Integration Blueprint v1.0.pptx"

    if not Path(test_file).exists():
        print(f"\n❌ File not found: {test_file}")
        print("Usage: python src/ingestion/extractor.py <path_to_file>")
        sys.exit(1)

    extractor = TextExtractor()
    slides = extractor.extract(test_file)

    print(f"\nExtracted {len(slides)} slides/pages:\n")

    for slide in slides:
        print(f"{'─' * 50}")
        print(f"  Slide {slide.slide_number}: {slide.title or '(no title)'}")
        print(f"  Length: {len(slide.content)} chars")
        print(f"  Has table: {slide.has_table}")
        if slide.table_data:
            print(f"  Table rows: {len(slide.table_data)}")
        # Show first 200 chars of content
        preview = slide.content[:200].replace('\n', ' ')
        print(f"  Preview: {preview}...")
        print()