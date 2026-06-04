"""
Generate RAG Complete Guide — Batch 2 (Topics 5-8)
Run: python docs/generate_guide_batch2.py
Output: docs/RAG_Guide_Batch2.docx
"""

import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn


def set_cell_shading(cell, color_hex):
    shading = cell._element.get_or_add_tcPr()
    elem = shading.makeelement(qn('w:shd'), {qn('w:fill'): color_hex, qn('w:val'): 'clear'})
    shading.append(elem)


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(10)
        set_cell_shading(cell, "1F4E79")
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = str(val)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(10)
            if r_idx % 2 == 0:
                set_cell_shading(cell, "D6E4F0")
    return table


def add_body(doc, text):
    p = doc.add_paragraph(text)
    return p


def add_bullet(doc, text):
    return doc.add_paragraph(text, style='List Bullet')


def add_code(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Consolas'
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(30, 30, 30)
    p.paragraph_format.left_indent = Cm(1)
    shading = p._element.get_or_add_pPr()
    elem = shading.makeelement(qn('w:shd'), {qn('w:fill'): 'F2F2F2', qn('w:val'): 'clear'})
    shading.append(elem)
    return p


# ── Create Document ──
doc = Document()
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
os.makedirs("docs", exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# TOPIC 5: DOCUMENT EXTRACTION
# ═══════════════════════════════════════════════════════════════

doc.add_heading('5. Document Extraction', level=1)

doc.add_heading('5.1 The Challenge', level=2)
add_body(doc,
    'Architecture PPTs are NOT text files. They are ZIP archives containing XML. '
    'Text is scattered across shapes, tables, images, and template elements. '
    'The extractor must handle all of these differently.')

doc.add_heading('5.2 What Can and Cannot Be Extracted', level=2)
add_table(doc,
    ["Element", "Extractable?", "How", "Quality"],
    [
        ["Text in shapes", "✅ Yes", "python-pptx shape.text_frame.text", "Good — preserves content"],
        ["Slide titles", "✅ Yes", "Placeholder detection (type 0, 1, 13, 15)", "Good — identifies topic"],
        ["Tables", "✅ Yes", "shape.table → rows → cells → text", "Good — converted to pipe-delimited text"],
        ["Bullet points", "✅ Yes", "Part of text frames", "Good — preserves hierarchy"],
        ["Diagrams/images", "❌ No", "Needs OCR (Phase 2)", "Not available in Phase 1"],
        ["SmartArt", "⚠️ Partial", "Sometimes text extractable, sometimes not", "Unreliable"],
        ["Charts/graphs", "❌ No", "Needs specialized parsing", "Not available"],
        ["Slide notes", "✅ Yes", "slide.notes_slide.notes_text_frame", "Available but not used"],
        ["Template boilerplate", "⚠️ Extracted but unwanted", "Copyright notices, placeholder text", "Must be cleaned by preprocessor"],
    ]
)

doc.add_heading('5.3 Table Extraction Strategy', level=2)
add_body(doc,
    'Tables in architecture decks contain critical data: server inventories, '
    'port mappings, cost breakdowns, support matrices. We extract tables in two ways:')
add_bullet(doc, 'Raw data (list of lists) → stored in table_data field for structured access')
add_bullet(doc, 'Pipe-delimited text → added to content for embedding. Example:')
add_code(doc,
    '[Table]\n'
    'TYPE | DESTINATION\n'
    'Public Cloud subscriptions | AWS account to be moved to Accenture\n'
    'Website Hosting | 3rd party hosted sites to be decommissioned')
add_body(doc,
    'Why pipe-delimited? The embedding model needs TEXT, not grid structures. '
    'Pipes visually separate columns while keeping data as a readable string.')

doc.add_heading('5.4 Real Bug: "shape is not a placeholder"', level=2)
add_body(doc, 'When processing the real DataStories PPT, we hit this error:')
add_code(doc, 'ValueError: shape is not a placeholder')
add_body(doc, 'Root cause:')
add_bullet(doc, 'python-pptx has a property called shape.placeholder_format')
add_bullet(doc, 'The property EXISTS on all shapes (hasattr returns True)')
add_bullet(doc, 'But ACCESSING it on non-placeholder shapes raises ValueError')
add_bullet(doc, 'This is a library quirk — the property exists but throws instead of returning None')
add_body(doc, 'Fix: Wrap the entire placeholder check in try/except ValueError:')
add_code(doc,
    'try:\n'
    '    ph_format = shape.placeholder_format\n'
    '    if ph_format is not None and ph_format.type in (0, 1, 13, 15):\n'
    '        title = text\n'
    'except (ValueError, AttributeError, KeyError):\n'
    '    pass  # Not a placeholder — treat as body text')
add_body(doc,
    'Lesson: Real enterprise PPTs break library assumptions. Always wrap '
    'extraction in try/except. One bad shape should NOT skip the entire slide.')

doc.add_heading('5.5 Phase 2 Improvement: Azure Document Intelligence', level=2)
add_table(doc,
    ["Capability", "Phase 1 (python-pptx)", "Phase 2 (Azure Doc Intelligence)"],
    [
        ["Text extraction", "Good", "Excellent — structure-aware"],
        ["Table extraction", "Basic (cell text only)", "Advanced (row/column structure, merged cells)"],
        ["Diagram text (OCR)", "Not possible", "Yes — reads text from images"],
        ["Layout detection", "None", "Detects headers, footers, sections"],
        ["Multi-language", "Text only", "Full OCR support"],
        ["Scanned PDFs", "No text extracted", "Full OCR"],
    ]
)
add_body(doc,
    'Azure Document Intelligence is the single biggest quality improvement in Phase 2. '
    'It can read text from architecture diagrams — something Phase 1 cannot do at all.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 6: PREPROCESSING & DATA QUALITY
# ═══════════════════════════════════════════════════════════════

doc.add_heading('6. Preprocessing & Data Quality', level=1)

doc.add_heading('6.1 The #1 Rule: Garbage In → Garbage Out', level=2)
add_body(doc,
    'This is the most important lesson in the entire RAG pipeline. '
    'No amount of fancy retrieval or powerful LLMs can fix bad data.')
add_body(doc, 'From our real DataStories PPT, 14 out of 26 slides had this as the "title":')
add_code(doc, 'Copyright © 2025 Accenture. All rights reserved.')
add_body(doc,
    'If this text enters the vector database, it competes with real architecture content '
    'during retrieval. When someone asks "Explain hosting architecture", a chunk containing '
    '"Copyright © 2025 Accenture" has a non-zero similarity to the query — and may displace '
    'the actual hosting chunk from the top results.')

doc.add_heading('6.2 Boilerplate Removal', level=2)
add_body(doc, 'The preprocessor removes these patterns using regex (regular expressions):')
add_table(doc,
    ["Pattern", "Example", "Why Remove"],
    [
        ["Copyright notices", "Copyright © 2025 Accenture. All rights reserved.", "Legal text, not architecture content"],
        ["Confidential notices", "HIGHLY CONFIDENTIAL- FOR COMPANY INTERNAL USE...", "Security label, not content"],
        ["Template placeholders", "Place headline here (36pt, min 30pt)", "PPT template artifact"],
        ["Bullet level indicators", "First level (bullet 20pt)", "Formatting instruction, not content"],
        ["Design tips", "Ensure the titles are not duplicated", "PPT design guidance, not content"],
        ["Standalone page numbers", "5, 6, 20", "Slide numbers leaking from template"],
    ]
)
add_body(doc, 'After cleaning, slide text is pure architecture content — ready for embedding.')

doc.add_heading('6.3 Section Type Classification', level=2)
add_body(doc,
    'Every chunk is tagged with a section_type that describes what kind of architecture '
    'content it contains. This enables FILTERED retrieval.')
add_body(doc, 'Why this matters:')
add_code(doc,
    'Without section_type:\n'
    '  "Compare current vs proposed" → retrieves MIXED chunks → confused comparison\n\n'
    'With section_type:\n'
    '  Retrieve section_type="current_architecture" → clean current state\n'
    '  Retrieve section_type="proposed_architecture" → clean proposed state\n'
    '  Pass both to LLM → structured comparison')

add_body(doc, 'Section types we detect:')
add_table(doc,
    ["Section Type", "Keywords That Trigger It", "Example Slide"],
    [
        ["current_architecture", "existing, current, legacy, old, as-is", "Existing Hosting - Overview"],
        ["proposed_architecture", "proposed, target, reference, new, to-be, future", "Target Reference Architecture"],
        ["hosting", "hosting, infrastructure, cloud, AWS, Azure, server", "Hosting Integration Overview"],
        ["security", "security, auth, VPN, firewall, encryption, FASM", "Accenture Security Standards"],
        ["budget", "budget, cost, pricing, expenditure, USD, opex", "Hosting IT Integration Budget Details"],
        ["migration", "migration, migrate, decommission, cutover", "Website Migration Plan"],
        ["risk_dependency", "risk, dependency, blocker, mitigation", "Risk and Dependencies"],
        ["assumptions", "assumption, assumed, prerequisite", "Key Assumptions"],
        ["inventory", "inventory, assessment, server list, disposition", "Inventory and Assessment Summary"],
        ["timeline", "milestone, timeline, schedule, phase, deadline", "Hosting Integration Milestones"],
        ["success_criteria", "success criteria, deemed successful, UAT", "Success Criteria"],
        ["operations", "support matrix, RACI, escalation", "Operations Support Matrix"],
        ["contacts", "contacts, workstream, owner, @email", "Contacts"],
        ["general", "(no keywords matched)", "Table of Contents"],
    ]
)

doc.add_heading('6.4 Hybrid Classification: Keywords + LLM Fallback', level=2)
add_body(doc,
    'Pure keyword matching has a limitation: it only matches patterns you have already seen. '
    'If a new client uses "Today\'s Landscape" instead of "Current Architecture", no keyword matches.')
add_body(doc, 'Solution: Hybrid approach — try keywords first, fall back to LLM if no match.')
add_code(doc,
    'Text arrives\n'
    '    |\n'
    '    v\n'
    'Keyword check (FREE, instant)\n'
    '    |\n'
    '    +-- Match found? --> Return label (e.g., "current_architecture")\n'
    '    |\n'
    '    +-- No match? --> Ask GPT-4.1 Nano to classify (~$0.0002 per call)\n'
    '                      |\n'
    '                      +-- Return label')

add_body(doc, 'Cost impact:')
add_bullet(doc, '~55 of 68 chunks match keywords → FREE')
add_bullet(doc, '~13 chunks need LLM → 13 × $0.0002 = $0.0026 total (₹0.25)')
add_bullet(doc, 'Best of both worlds: fast for known patterns, intelligent for surprises')

doc.add_heading('6.5 Meaningfulness Filter', level=2)
add_body(doc,
    'Not every slide is worth embedding. Slides with less than 50 characters of real '
    'content after cleaning are filtered out.')
add_body(doc, 'From our DataStories PPT:')
add_table(doc,
    ["Slide", "Content After Cleaning", "Length", "Decision"],
    [
        ["Slide 6", "Hosting Integration Milestones", "32 chars", "❌ SKIP (just a heading)"],
        ["Slide 7", "Hosting – High Level Migration Plan", "35 chars", "❌ SKIP (just a heading)"],
        ["Slide 23", "References", "10 chars", "❌ SKIP (empty section)"],
        ["Slide 9", "Existing Hosting - Overview Internet https://demo...", "199 chars", "✅ KEEP (real content)"],
        ["Slide 13", "Hosting IT Integration Budget Details Note: All costs...", "880 chars", "✅ KEEP (rich content)"],
    ]
)
add_body(doc,
    'Result: 26 slides → 21 meaningful slides. 5 slides filtered out = saved embedding cost '
    'and reduced noise in retrieval results.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 7: CHUNKING — THE MOST CRITICAL DECISION
# ═══════════════════════════════════════════════════════════════

doc.add_heading('7. Chunking — The Most Critical Decision', level=1)

doc.add_heading('7.1 What is a Chunk?', level=2)
add_body(doc,
    'A chunk is one piece of text stored as a single unit in the vector database. '
    'When someone asks a question, the system retrieves CHUNKS (not entire files, not entire slides). '
    'Each chunk gets its own embedding vector and is retrieved independently.')
add_code(doc,
    'Full PPT (26 slides, ~8000 chars)\n'
    '        | chunking\n'
    '[Chunk 1: 400 chars] [Chunk 2: 600 chars] [Chunk 3: 350 chars] ...\n'
    '        |\n'
    'Each chunk gets its OWN embedding vector\n'
    'Each chunk is retrieved INDEPENDENTLY')

doc.add_heading('7.2 Why Chunk Size is the #1 Tuning Parameter', level=2)
add_body(doc,
    'Chunk size determines what the retriever CAN find. '
    'If important info is split across two chunks, the retriever may miss half. '
    'If unrelated topics are in one chunk, the retriever gets noise with the signal.')

doc.add_heading('7.3 Too Small vs Just Right vs Too Large', level=2)

add_body(doc, 'TOO SMALL (100-300 chars):')
add_bullet(doc, 'Fragmented context — sentences cut in half')
add_bullet(doc, 'Lost relationships between concepts')
add_bullet(doc, 'Many chunks = higher embedding cost')
add_bullet(doc, 'Example: "The API Gateway connects to Auth" in one chunk, "Service which validates tokens" in another')

add_body(doc, 'JUST RIGHT (500-1500 chars) — our sweet spot:')
add_bullet(doc, 'Complete topic per chunk (one slide or two related slides)')
add_bullet(doc, 'Focused embedding meaning — vector captures the topic clearly')
add_bullet(doc, 'Balanced cost and quality')
add_bullet(doc, 'Easy to cite: [Source: blueprint.pptx, Slide 4-5]')

add_body(doc, 'TOO LARGE (3000+ chars):')
add_bullet(doc, 'Mixed topics in one chunk — embedding captures the AVERAGE meaning')
add_bullet(doc, 'Retrieves noise alongside signal')
add_bullet(doc, 'Hard to cite specifically — which part of the chunk is relevant?')
add_bullet(doc, 'Example: 7 slides merged — hosting, budget, risks all in one chunk')

doc.add_heading('7.4 Our Three Operations: Merge, Keep, Split', level=2)

add_table(doc,
    ["Condition", "Action", "Example"],
    [
        ["Slide < 100 chars", "MERGE with next slide", "Slide 6 (32 chars) + Slide 7 (35 chars) → combined chunk"],
        ["Slide 100-1500 chars", "KEEP as-is", "Slide 13 (880 chars) → one chunk"],
        ["Slide > 1500 chars", "SPLIT with 150-char overlap", "2000-char slide → Chunk A (0-1500) + Chunk B (1350-2000)"],
    ]
)

doc.add_heading('7.5 Overlap Explained', level=2)
add_body(doc,
    'When splitting a large chunk, we overlap by 150 characters so no information '
    'is lost at the boundary.')
add_code(doc,
    'Without overlap (split at 1500):\n'
    '  Chunk A: "...the API Gate"  |  Chunk B: "way connects to Auth..."\n'
    '  --> BROKEN mid-word\n\n'
    'With 150-char overlap:\n'
    '  Chunk A: "...the API Gateway connects to Auth Service."\n'
    '  Chunk B: "After validation, the API Gateway forwards the request..."\n'
    '  --> Both chunks have the complete thought about the Gateway')
add_body(doc,
    'Why 150 chars? That is roughly 2-3 sentences — enough to complete a thought '
    'without too much duplication (only ~10% of max chunk size).')

doc.add_heading('7.6 Understanding Tokens', level=2)
add_body(doc,
    'AI models do not process characters or words. They process TOKENS — '
    'pieces of words that capture meaningful sub-word units.')
add_code(doc,
    '"Hello world"           --> ["Hello", " world"]              = 2 tokens\n'
    '"Architecture"          --> ["Arch", "itecture"]              = 2 tokens\n'
    '"API Gateway"           --> ["API", " Gateway"]               = 2 tokens\n'
    '"https://datastories.com" --> ["https", "://", "data", "stories", ".com"] = 5 tokens')

add_body(doc, 'Rough conversion rule:')
add_table(doc,
    ["Characters", "Tokens (approx)", "Example"],
    [
        ["100 chars", "~25 tokens", "A short sentence"],
        ["500 chars", "~125 tokens", "A paragraph"],
        ["1000 chars", "~250 tokens", "Half a slide"],
        ["1500 chars", "~375 tokens", "Our max chunk size"],
        ["4000 chars", "~1000 tokens", "A full page"],
    ]
)

doc.add_heading('7.7 Why 1500 Chars (375 Tokens)?', level=2)
add_body(doc, 'Two constraints determine this number:')

add_body(doc, 'Constraint 1: Embedding model quality')
add_bullet(doc, 'text-embedding-3-small input limit: 8,191 tokens')
add_bullet(doc, 'But quality DEGRADES after ~500 tokens — the embedding becomes an average of too many topics')
add_bullet(doc, 'Best quality: 200-400 tokens')
add_bullet(doc, '1500 chars ≈ 375 tokens → sits in the best quality zone')

add_body(doc, 'Constraint 2: LLM context budget')
add_code(doc,
    'Per query, the LLM receives:\n'
    '  System prompt:          ~500 tokens\n'
    '  Conversation history:   ~500 tokens\n'
    '  Retrieved chunks:       8 x 375 = 3,000 tokens\n'
    '  User question:          ~20 tokens\n'
    '  -----------------------------------------\n'
    '  Total input:            ~4,020 tokens\n'
    '  Generated answer:       ~500-1,000 tokens\n'
    '  -----------------------------------------\n'
    '  Grand total:            ~5,000 tokens per query\n\n'
    '  GPT-4.1 context window: 1,050,000 tokens\n'
    '  We use only 0.5% of capacity --> plenty of room for growth')

doc.add_heading('7.8 Our Settings', level=2)
add_table(doc,
    ["Setting", "Value", "In Tokens", "Purpose"],
    [
        ["CHUNK_MIN_LENGTH", "100 chars", "~25 tokens", "Below this → merge with next slide (too small to be useful)"],
        ["CHUNK_MAX_LENGTH", "1500 chars", "~375 tokens", "Above this → split with overlap (too large, dilutes embedding)"],
        ["CHUNK_OVERLAP", "150 chars", "~37 tokens", "When splitting → overlap this much (preserves context at boundaries)"],
    ]
)
add_body(doc,
    'These are tunable in the .env file. After running evaluation, if retrieval quality is low, '
    'chunk size is the FIRST thing to adjust.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 8: EMBEDDINGS & VECTOR STORAGE
# ═══════════════════════════════════════════════════════════════

doc.add_heading('8. Embeddings & Vector Storage', level=1)

doc.add_heading('8.1 What is an Embedding?', level=2)
add_body(doc,
    'An embedding is a list of numbers (a vector) that captures the MEANING of text. '
    'Similar meanings produce similar vectors. Different meanings produce different vectors.')
add_code(doc,
    '"DataStories uses AWS"        --> [0.12, -0.34, 0.56, ...]  (1536 numbers)\n'
    '"Infrastructure on Amazon"    --> [0.11, -0.33, 0.55, ...]  (similar! close vectors)\n'
    '"Budget is $50K"              --> [-0.89, 0.22, -0.11, ...]  (different! far vectors)')

add_body(doc, 'Analogy: Think of embeddings like GPS coordinates for meaning.')
add_bullet(doc, '"Paris" and "France" are close on the map (related meanings)')
add_bullet(doc, '"Paris" and "Calculus" are far apart (unrelated meanings)')
add_bullet(doc, 'When you ask a question, it gets coordinates too, and we find the nearest stored points')

doc.add_heading('8.2 How Semantic Search Works', level=2)
add_code(doc,
    'User asks: "How is DataStories hosted?"\n'
    '  --> Embed question --> [0.15, -0.28, 0.67, ...]\n\n'
    'Compare against ALL 89 stored chunk vectors:\n'
    '  Chunk "Existing Hosting - Overview..."    --> distance: 0.18 (CLOSE)  ✅\n'
    '  Chunk "Budget Details..."                 --> distance: 0.72 (FAR)    ❌\n'
    '  Chunk "Key Assumptions..."                --> distance: 0.55 (MEDIUM) ⚠️\n\n'
    'Return the closest chunks = most relevant content')

doc.add_heading('8.3 Our Embedding Model', level=2)
add_table(doc,
    ["Property", "text-embedding-3-small (our choice)", "text-embedding-3-large"],
    [
        ["Dimensions", "1,536", "3,072"],
        ["Price per 1M tokens", "$0.02", "$0.13"],
        ["Quality (MIRACL benchmark)", "44.0", "54.9"],
        ["Max input tokens", "8,191", "8,191"],
        ["Best for", "Most use cases, cost-effective", "Complex semantic tasks, multi-language"],
    ]
)
add_body(doc,
    'We chose text-embedding-3-small because it is 6.5x cheaper with marginal quality '
    'difference for English enterprise documents. Upgrade to 3-large only if evaluation '
    'shows retrieval quality issues.')

doc.add_heading('8.4 ChromaDB — What It Stores', level=2)
add_body(doc, 'For each chunk, ChromaDB stores three things:')
add_code(doc,
    '{\n'
    '  "id": "md5_hash_of_client_file_index",\n'
    '  "embedding": [0.12, -0.34, 0.56, ...],   // 1536 floats\n'
    '  "document": "The actual text content...",  // for building LLM context\n'
    '  "metadata": {\n'
    '    "client": "DataStories",\n'
    '    "source_file": "blueprint.pptx",\n'
    '    "slide_number": "9",\n'
    '    "section_type": "current_architecture",\n'
    '    "chunk_index": 5,\n'
    '    "ingested_at": "2026-06-03T..."\n'
    '  }\n'
    '}')
add_body(doc,
    'The embedding enables semantic search (find by meaning). '
    'The metadata enables filtered search (find by client, section type). '
    'Both together give precise, relevant results.')

doc.add_heading('8.5 Cosine Similarity Explained', level=2)
add_body(doc,
    'Cosine similarity measures the ANGLE between two vectors, not the distance. '
    'This is important because it ignores magnitude (length of text) and focuses on direction (meaning).')
add_table(doc,
    ["Score", "Meaning", "Example"],
    [
        ["1.0", "Identical meaning", "Same text, rephrased"],
        ["0.7-0.9", "Highly similar", "Same topic, different words"],
        ["0.4-0.7", "Somewhat related", "Related topic, some overlap"],
        ["0.2-0.4", "Weakly related", "Different topic, minor connection"],
        ["0.0-0.2", "Unrelated", "Completely different topics"],
    ]
)
add_body(doc,
    'Our threshold is 0.35 — chunks scoring below this are dropped. '
    'This prevents low-quality context from confusing the LLM.')

doc.add_heading('8.6 Critical Bug: Dimension Mismatch (1536 vs 384)', level=2)
add_body(doc, 'This was one of the most educational bugs we encountered.')
add_code(doc,
    'INDEXING (Step 6):\n'
    '  Chunks --> Azure OpenAI text-embedding-3-small --> 1536-dim vectors\n'
    '  Stored in ChromaDB ✅\n\n'
    'QUERYING (Step 7, first attempt):\n'
    '  Query --> ChromaDB default model (all-MiniLM-L6-v2) --> 384-dim vectors\n'
    '  Tried to compare 384 vs 1536 --> CRASH\n\n'
    'Error: "Collection expecting embedding with dimension of 1536, got 384"')

add_body(doc, 'What happened:')
add_bullet(doc, 'ChromaDB downloaded its own embedding model (79MB!) when we used query_texts parameter')
add_bullet(doc, 'This default model produces 384-dimensional vectors')
add_bullet(doc, 'Our indexed chunks use Azure OpenAI which produces 1536-dimensional vectors')
add_bullet(doc, 'You cannot compare vectors of different dimensions — like comparing GPS coordinates in 2D vs 3D')

add_body(doc, 'Fix:')
add_code(doc,
    '# WRONG: Let ChromaDB embed (uses its 384-dim model)\n'
    'results = collection.query(query_texts=[question], ...)\n\n'
    '# CORRECT: We embed with Azure OpenAI (same 1536-dim model)\n'
    'query_vector = openai_client.embeddings.create(model="text-embedding-3-small", input=[question])\n'
    'results = collection.query(query_embeddings=[query_vector], ...)')

add_body(doc, 'THE RULE (memorize this):')
add_code(doc,
    'The embedding model used for QUERIES must be IDENTICAL\n'
    'to the model used for INDEXING.\n\n'
    'If you change the embedding model, you MUST re-index everything.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════

output_path = "docs/RAG_Guide_Batch2.docx"
doc.save(output_path)
print(f"✅ Saved: {output_path}")
print(f"   Topics covered: 5-8")
print(f"   (Extraction, Preprocessing, Chunking, Embeddings)")