"""
Azure Document Intelligence Extractor — Phase 2 text extraction
================================================================

WHAT CHANGED FROM PHASE 1:
    Phase 1 (extractor.py):
        python-pptx reads text from shapes and tables
        CANNOT read text from images/diagrams
    
    Phase 2 (this file):
        Azure Document Intelligence reads EVERYTHING:
        - Text from shapes ✅ (same)
        - Text from images/diagrams ✅ (NEW — OCR!)
        - Table structure with merged cells ✅ (BETTER)
        - Document layout detection ✅ (NEW)

LAYMAN:
    Phase 1: A reader who can only read printed text
    Phase 2: A reader who can read printed text AND look at pictures
             and understand what the diagrams say

Run: python -m src.ingestion.azure_doc_extractor
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from typing import List

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from config.settings import get_settings
from src.ingestion.extractor import SlideContent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class AzureDocExtractor:
    """
    Phase 2 extractor using Azure Document Intelligence Layout API.
    
    SAME OUTPUT as Phase 1 extractor:
        extract(file_path) → List[SlideContent]
    
    The chunker doesn't need to know which extractor produced the data.
    This is the power of consistent interfaces.
    """

    def __init__(self):
        settings = get_settings()
        self.client = DocumentIntelligenceClient(
            endpoint=settings.azure_docintel_endpoint,
            credential=AzureKeyCredential(settings.azure_docintel_api_key),
        )
        logger.info(f"AzureDocExtractor initialized: {settings.azure_docintel_endpoint}")

    def extract(self, file_path: str) -> List[SlideContent]:
        """
        Extract text using Azure Document Intelligence Layout API.
        
        THE KEY DIFFERENCE:
            Phase 1: python-pptx reads shapes → misses images
            Phase 2: Layout API reads EVERYTHING including images (OCR)
        
        LAYMAN:
            Phase 1: Reads the text on each slide but skips pictures
            Phase 2: Reads the text AND looks at the pictures to read
                     any text inside diagrams, flowcharts, etc.
        """
        path = Path(file_path)
        logger.info(f"Extracting with Azure Doc Intelligence: {path.name}")

        try:
            # Read file bytes
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            # Analyze document with Layout model
            # "prebuilt-layout" understands:
            #   - Paragraphs (flowing text)
            #   - Tables (rows, columns, merged cells)
            #   - Figures (images — extracts text via OCR)
            #   - Selection marks (checkboxes)
            #   - Page structure (headers, footers, page numbers)
            poller = self.client.begin_analyze_document(
                model_id="prebuilt-layout",
                body=file_bytes,
                content_type="application/octet-stream",
            )
            result = poller.result()

            slides_content = []

            # Process each page (page ≈ slide for PPTs)
            for page_idx, page in enumerate(result.pages):
                page_num = page_idx + 1
                lines = []
                title = ""

                # Extract text lines from this page
                if page.lines:
                    for line in page.lines:
                        lines.append(line.content)
                    # First line as title (simple heuristic)
                    if lines and len(lines[0]) < 120:
                        title = lines[0]

                # Extract tables on this page
                table_texts = []
                has_table = False
                table_data = []

                if result.tables:
                    for table in result.tables:
                        # Check if table is on this page
                        table_on_page = False
                        if table.bounding_regions:
                            for region in table.bounding_regions:
                                if region.page_number == page_num:
                                    table_on_page = True
                                    break

                        if table_on_page:
                            has_table = True
                            rows = {}
                            for cell in table.cells:
                                ri = cell.row_index
                                ci = cell.column_index
                                if ri not in rows:
                                    rows[ri] = {}
                                rows[ri][ci] = cell.content or ""

                            # Build table text
                            for ri in sorted(rows.keys()):
                                row = rows[ri]
                                cells = [row.get(ci, "") for ci in sorted(row.keys())]
                                table_data.append(cells)

                            pipe_text = "\n".join(" | ".join(r) for r in table_data if any(r))
                            if pipe_text:
                                table_texts.append(f"[Table]\n{pipe_text}")

                # Combine all content for this page
                full_content = "\n".join(lines)
                if table_texts:
                    full_content += "\n" + "\n".join(table_texts)

                full_content = full_content.strip()

                if full_content:
                    slides_content.append(SlideContent(
                        slide_number=page_num,
                        title=title,
                        content=full_content,
                        has_table=has_table,
                        table_data=table_data,
                    ))
                    logger.debug(f"  Page {page_num}: {len(full_content)} chars")

            logger.info(f"  Extracted {len(slides_content)} pages from {path.name}")
            return slides_content

        except Exception as e:
            logger.error(f"  Error extracting {file_path}: {e}")
            return []


# ── Standalone Testing ──
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Azure Document Intelligence — Extraction Test")
    print("=" * 60)

    test_file = "data/documents/DataStories/Datastories Hosting Integration Blueprint v1.0.pptx"
    if not Path(test_file).exists():
        print(f"❌ File not found: {test_file}")
        sys.exit(1)

    extractor = AzureDocExtractor()
    slides = extractor.extract(test_file)

    print(f"\nExtracted {len(slides)} pages:\n")
    for slide in slides:
        print(f"{'─' * 50}")
        print(f"  Page {slide.slide_number}: {slide.title or '(no title)'}")
        print(f"  Length: {len(slide.content)} chars")
        print(f"  Has table: {slide.has_table}")
        preview = slide.content[:150].replace('\n', ' ')
        print(f"  Preview: {preview}...")