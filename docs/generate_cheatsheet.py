"""
Generate RAG Cheat Sheet — All terminology explained
Run: python docs/generate_cheatsheet.py
Output: docs/RAG_Cheatsheet.docx
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


def add_category_table(doc, category_name, terms):
    """Add a category heading and table of terms."""
    doc.add_heading(category_name, level=2)

    table = doc.add_table(rows=1 + len(terms), cols=4)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Set column widths roughly
    headers = ["Term", "What It Means", "Layman Analogy", "Technical Detail"]
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(9)
        set_cell_shading(cell, "1F4E79")

    for r_idx, (term, definition, analogy, technical) in enumerate(terms):
        row = table.rows[r_idx + 1]
        values = [term, definition, analogy, technical]
        for c_idx, val in enumerate(values):
            cell = row.cells[c_idx]
            cell.text = val
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(8)
                    if c_idx == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(88, 166, 255)
                    else:
                        run.font.color.rgb = RGBColor(50, 50, 50)
            if r_idx % 2 == 0:
                set_cell_shading(cell, "E8F0FE")

    doc.add_paragraph()  # Spacer


# ── Create Document ──
doc = Document()
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(10)
os.makedirs("docs", exist_ok=True)

# ── Title ──
title = doc.add_heading('RAG Cheat Sheet', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub = doc.add_paragraph('Every RAG Term Explained — In Plain English')
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in sub.runs:
    run.font.size = Pt(14)
    run.font.italic = True
    run.font.color.rgb = RGBColor(100, 100, 100)

doc.add_paragraph('Architecture Knowledge Assistant | June 2026').alignment = WD_ALIGN_PARAGRAPH.CENTER
doc.add_paragraph()

# ═══════════════════════════════════════════════════════════════
# 1. CORE RAG CONCEPTS
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "1. Core RAG Concepts", [
    (
        "RAG",
        "Retrieval-Augmented Generation. LLM answers using YOUR documents, not training data.",
        "Like an open-book exam — the AI looks up answers in your notes instead of guessing from memory.",
        "Pattern: embed query → retrieve relevant chunks from vector DB → pass chunks + question to LLM → generate grounded answer."
    ),
    (
        "Ingestion\n(Write Path)",
        "The process of getting your documents INTO the system. Runs once per document.",
        "Like organizing a library — you take books, label them, and put them on the right shelf so you can find them later.",
        "Pipeline: Scan files → Extract text → Clean → Chunk → Embed → Store in vector DB."
    ),
    (
        "Query\n(Read Path)",
        "The process of answering a question. Runs every time someone asks.",
        "Like asking a librarian — they know where everything is and bring you the right books.",
        "Pipeline: Embed question → Search vector DB → Filter by metadata → Pass chunks to LLM → Return answer."
    ),
    (
        "Grounding",
        "Ensuring the LLM answers ONLY from provided documents, not from training data.",
        "Like telling a witness: 'Only testify about what you personally saw, don't guess.'",
        "Enforced via system prompt: 'Answer ONLY from the provided context. If not found, say I don't know.'"
    ),
    (
        "Hallucination",
        "When the LLM makes up information that isn't in the documents.",
        "Like a student writing a confident answer on an exam about a book they never read.",
        "Caused by LLM using training data instead of provided context. Prevented by grounding + low temperature."
    ),
    (
        "Citation",
        "Source reference attached to each claim in the answer.",
        "Like footnotes in a research paper — readers can verify every claim.",
        "Format: [Source: blueprint.pptx, Slide 9]. Enables trust, verification, and debugging."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 2. DOCUMENT PROCESSING
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "2. Document Processing", [
    (
        "Extraction",
        "Pulling readable text out of PPT/PDF/DOCX files.",
        "Like photocopying the text from a book — you want the words, not the cover art.",
        "Libraries: python-pptx (PPT), PyMuPDF (PDF), python-docx (DOCX). Phase 2: Azure Document Intelligence."
    ),
    (
        "Preprocessing",
        "Cleaning the extracted text — removing junk, normalizing format.",
        "Like washing vegetables before cooking — remove the dirt, keep the good stuff.",
        "Removes: copyright notices, template placeholders, excessive whitespace. Uses regex patterns."
    ),
    (
        "Boilerplate",
        "Repeated template text that has no useful content.",
        "Like the 'Terms and Conditions' text nobody reads — it's on every page but adds no value.",
        "Examples: 'Copyright © 2025 Accenture', 'Place headline here (36pt)', slide numbers."
    ),
    (
        "Chunk",
        "One piece of text stored as a single unit in the vector database.",
        "Like one index card in a recipe box — each card has one recipe, not the whole cookbook.",
        "Each chunk gets its own embedding vector and is retrieved independently. Typically 500-1500 chars."
    ),
    (
        "Chunk Size",
        "How many characters (or tokens) each chunk contains.",
        "Like deciding how big to cut pizza slices — too small = crumbs, too big = can't eat, just right = perfect.",
        "Our settings: min=100 chars, max=1500 chars. 1500 chars ≈ 375 tokens ≈ embedding sweet spot."
    ),
    (
        "Chunk Overlap",
        "When splitting a large chunk, repeating some text in both pieces.",
        "Like overlapping puzzle pieces — the shared edge ensures nothing falls through the crack.",
        "Our setting: 150 chars overlap. Prevents losing context at chunk boundaries."
    ),
    (
        "Metadata",
        "Structured labels attached to each chunk (client, file, slide, type).",
        "Like tags on a product — brand, size, color, price. Helps you filter without reading every item.",
        "Our metadata: {client, source_file, slide_number, section_type, chunk_index, ingested_at}."
    ),
    (
        "Section Type",
        "A label describing what kind of content a chunk contains.",
        "Like sections in a newspaper — Sports, Business, Weather. Helps you find the right section fast.",
        "Types: current_architecture, proposed_architecture, budget, security, migration, risk, timeline, etc."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 3. EMBEDDINGS & VECTORS
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "3. Embeddings & Vectors", [
    (
        "Token",
        "A sub-word unit that AI models process. Not a character, not a full word — in between.",
        "Like syllables in speech — 'ar-chi-tec-ture' is 4 syllables. AI reads in similar pieces.",
        "1 token ≈ 4 characters ≈ 0.75 words. 'Architecture' = 2 tokens. 1500 chars ≈ 375 tokens."
    ),
    (
        "Embedding",
        "A list of numbers (vector) that captures the MEANING of text.",
        "Like GPS coordinates for meaning — similar meanings have nearby coordinates.",
        "text-embedding-3-small produces 1536 numbers per text input. Enables meaning-based search."
    ),
    (
        "Vector",
        "A list of numbers. In RAG, specifically an embedding vector.",
        "Like a point on a map — [latitude, longitude] but with 1536 dimensions instead of 2.",
        "Example: [0.12, -0.34, 0.56, ...] (1536 floats). Stored in vector database for similarity search."
    ),
    (
        "Dimensions",
        "How many numbers are in an embedding vector.",
        "Like resolution of a photo — more pixels = more detail. More dimensions = more nuance.",
        "text-embedding-3-small: 1536 dims. text-embedding-3-large: 3072 dims. More dims = slightly better but costs more."
    ),
    (
        "Embedding Model",
        "The AI model that converts text into embedding vectors.",
        "Like a translator who converts English into a universal number language that any computer can compare.",
        "Our model: text-embedding-3-small ($0.02/1M tokens, 1536 dims). MUST be same for indexing AND querying."
    ),
    (
        "Cosine Similarity",
        "Measures how similar two vectors are by comparing their direction.",
        "Like comparing which way two arrows point — same direction = similar, opposite = different.",
        "Score 0-1. 1.0 = identical meaning. 0.5 = somewhat related. 0.0 = completely unrelated."
    ),
    (
        "Distance vs\nSimilarity",
        "Distance = how FAR apart (lower = more similar). Similarity = how CLOSE (higher = more similar).",
        "Distance is like measuring miles between cities. Similarity is like a match percentage on a dating app.",
        "ChromaDB returns distance. We convert: similarity = 1 - distance. Threshold at 0.35 similarity."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 4. STORAGE & SEARCH
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "4. Storage & Search", [
    (
        "Vector Database",
        "A database optimized for storing and searching embedding vectors.",
        "Like a library catalog that finds books by MEANING, not just by title or author.",
        "Stores: vector + original text + metadata. Searches by vector similarity. Examples: ChromaDB, Pinecone, Azure AI Search."
    ),
    (
        "ChromaDB",
        "An open-source, local vector database. Our Phase 1 choice.",
        "Like a personal filing cabinet on your desk — free, fast, but only you can access it.",
        "PersistentClient stores to disk. Supports cosine/L2/IP distance. No server needed. Phase 2 replacement: Azure AI Search."
    ),
    (
        "Index / Collection",
        "A named container for vectors in the database. Like a table in SQL.",
        "Like a specific drawer in the filing cabinet — our drawer is called 'arch_knowledge'.",
        "Our collection: 'arch_knowledge' with 89 vectors. Each vector has document text + metadata."
    ),
    (
        "Semantic Search",
        "Finding content by MEANING, not exact keywords.",
        "Like asking a smart librarian 'books about space travel' — they find 'Interstellar Journey' even though 'space travel' isn't in the title.",
        "Embed query → compare vector against all stored vectors → return most similar. 'hosting setup' finds 'infrastructure deployment'."
    ),
    (
        "Keyword Search\n(BM25)",
        "Finding content by exact word matching. Traditional search.",
        "Like Ctrl+F — finds the exact text you typed, nothing more.",
        "BM25 algorithm scores based on word frequency + document length. Good for exact terms like 'port 443' or account numbers."
    ),
    (
        "Hybrid Search",
        "Combining semantic search + keyword search for best results.",
        "Like using both Google (meaning) and Ctrl+F (exact match) and combining the results.",
        "Azure AI Search combines vector similarity + BM25 scores using Reciprocal Rank Fusion. Phase 2 feature."
    ),
    (
        "Metadata\nFiltering",
        "Narrowing search results using structured labels before semantic search.",
        "Like filtering Amazon by 'Brand: Nike' before searching for 'running shoes'.",
        "filter: {client: 'DataStories'} → eliminates 69 of 89 chunks instantly → then semantic search on remaining 20."
    ),
    (
        "Top-K",
        "The maximum number of chunks to retrieve per query.",
        "Like telling Google 'show me the top 8 results' instead of all 10,000.",
        "Our setting: top_k=8. Higher K = more context but more noise. Lower K = more focused but may miss relevant chunks."
    ),
    (
        "Relevance\nThreshold",
        "Minimum similarity score to include a chunk in results.",
        "Like a minimum GPA to pass — below 0.35 similarity = not relevant enough, drop it.",
        "Our setting: 0.35. Chunks scoring below this are filtered out to prevent noise in LLM context."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 5. RETRIEVAL QUALITY
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "5. Retrieval Quality", [
    (
        "Bi-Encoder",
        "Encodes query and chunks SEPARATELY, then compares vectors.",
        "Like two people writing summaries of their books independently, then comparing summaries.",
        "Fast (one embedding per text). Less precise (no cross-attention). Used for initial retrieval."
    ),
    (
        "Cross-Encoder",
        "Reads query AND chunk TOGETHER to score relevance.",
        "Like a judge reading both the question and answer side by side before scoring.",
        "Slow (must process each pair). Very precise. Used for reranking top candidates."
    ),
    (
        "Reranking",
        "Second-pass scoring of retrieved results using a cross-encoder.",
        "Like a talent show — first round picks 20 contestants (fast), second round picks the winner (careful).",
        "Stage 1: bi-encoder retrieves top 20. Stage 2: cross-encoder re-scores and returns top 8. Built into Azure AI Search."
    ),
    (
        "Precision",
        "Of the chunks retrieved, how many are actually relevant?",
        "Like fishing — if you catch 10 fish and 8 are the kind you want, precision is 80%.",
        "High precision = less noise in LLM context = better answers. Improved by reranking and filtering."
    ),
    (
        "Recall",
        "Of all relevant chunks that exist, how many were retrieved?",
        "Like an Easter egg hunt — if there are 10 eggs and you found 7, recall is 70%.",
        "High recall = complete answers. Improved by higher top_k and hybrid search."
    ),
    (
        "Single-Hop\nRetrieval",
        "One search query → one set of results → answer. Standard RAG.",
        "Like asking one question and getting one answer. Simple but can't handle complex queries.",
        "Our current system. Works for: 'Explain DataStories architecture', 'What is the budget?'"
    ),
    (
        "Multi-Hop\nRetrieval",
        "Multiple search queries in sequence, each informed by previous results.",
        "Like a detective following clues — each clue leads to the next question.",
        "Needed for: 'Which clients with budget >$50K migrate to Azure?' Requires agentic approach."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 6. GENERATION
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "6. Generation", [
    (
        "LLM",
        "Large Language Model. The AI that generates human-like text responses.",
        "Like a very smart assistant who can read documents and write summaries, but needs to be told what to focus on.",
        "We use Azure OpenAI GPT-4.1. Takes: system prompt + context + question. Returns: answer with citations."
    ),
    (
        "System Prompt",
        "Instructions that define HOW the LLM should behave.",
        "Like a job description for the AI — 'You are an architecture assistant. Only answer from provided docs. Include citations.'",
        "Our 6 rules: only from context, include citations, say I don't know, structure clearly, comparisons separate, be precise."
    ),
    (
        "Context Window",
        "Maximum tokens the LLM can process in one call (input + output combined).",
        "Like the size of the AI's desk — it can only look at this many papers at once.",
        "GPT-4.1: 1,050,000 tokens. We use ~5,000 per query (0.5% of capacity). Plenty of room."
    ),
    (
        "Temperature",
        "Controls how creative/random vs deterministic the LLM's output is.",
        "Like a creativity dial: 0 = robot (always same answer), 1 = artist (different every time).",
        "We use 0.1 (almost deterministic). Factual RAG needs consistent, reliable answers, not creative ones."
    ),
    (
        "Input Tokens",
        "Tokens sent TO the LLM (system prompt + context + question). You pay for these.",
        "Like the pages of notes you give to a student before an exam.",
        "Our per-query: ~4,000 input tokens. Cost: 4000 x ($0.40/1M) = $0.0016 with GPT-4.1 Mini."
    ),
    (
        "Output Tokens",
        "Tokens generated BY the LLM (the answer). You pay more for these.",
        "Like the essay the student writes in response. Longer essay = more cost.",
        "Our per-query: ~800 output tokens. Cost: 800 x ($1.60/1M) = $0.00128 with GPT-4.1 Mini."
    ),
    (
        "Max Tokens",
        "Limit on how long the LLM's answer can be.",
        "Like a word limit on an essay — 'answer in 2000 words or less.'",
        "Our setting: 2000 tokens (~1500 words). Enough for detailed architecture explanations."
    ),
    (
        "Conversation\nMemory",
        "Keeping previous Q&A pairs so the LLM understands follow-up questions.",
        "Like a human conversation — 'What about the security?' makes sense because you remember we were talking about DataStories.",
        "We keep last 5 Q&A pairs. Sliding window — oldest dropped when new ones arrive. Lost on restart."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 7. ARCHITECTURE PATTERNS
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "7. Advanced RAG Patterns", [
    (
        "Agentic RAG",
        "An AI agent that DECIDES how to answer — plans, retrieves multiple times, reasons.",
        "Like a research assistant who plans their approach: 'First I'll look up budgets, then compare, then recommend.'",
        "Uses LLM function calling / tool use. Agent loops: think → act → observe → think again. Solves multi-hop queries."
    ),
    (
        "Multimodal RAG",
        "RAG that understands images, not just text.",
        "Like a person who can read BOTH the text AND the diagrams in a presentation.",
        "Vision model (GPT-4o) or Azure Doc Intelligence OCR extracts text from architecture diagrams. Phase 2+."
    ),
    (
        "Graph RAG",
        "Combines vector search with a knowledge graph for relationship-aware retrieval.",
        "Like a family tree — you can ask 'who is related to whom?' not just 'who exists?'",
        "Entities + relationships extracted from docs. Graph traversal for 'what depends on the API Gateway?'"
    ),
    (
        "Corrective RAG\n(CRAG)",
        "Self-correcting RAG that checks if its answer is grounded, re-tries if not.",
        "Like a student who checks their own work — 'Wait, I'm not sure about this. Let me look again.'",
        "Generate → verify grounding → if not grounded → re-retrieve → re-generate. Reduces hallucination."
    ),
    (
        "Adaptive RAG",
        "Adjusts retrieval strategy based on query complexity.",
        "Like a doctor who orders simple tests for a cold but full bloodwork for complex symptoms.",
        "Simple query → Nano model, few chunks. Complex query → Full model, multi-hop, more chunks. Our intent routing is a simple form."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 8. OPERATIONS
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "8. Operations & Evaluation", [
    (
        "Evaluation",
        "Measuring how good your RAG system is with objective metrics.",
        "Like grading an exam — you need answer keys to know if the student passed.",
        "Our metrics: retrieval hit, faithfulness, citation present. Quality gate: >= 70% to pass."
    ),
    (
        "Golden Q&A\nPairs",
        "Pre-written questions with known correct answers for testing.",
        "Like an answer key for an exam — you compare the system's answers against these.",
        "We created 10 pairs from the real DataStories PPT. Covers hosting, budget, security, migration, etc."
    ),
    (
        "Quality Gate",
        "Minimum accuracy threshold that must be met before deployment.",
        "Like a pass/fail grade — below 70% means the system needs fixing before anyone uses it.",
        "Our gate: 70% overall accuracy. Blocks deployment if accuracy drops after code changes."
    ),
    (
        "Faithfulness",
        "Does the answer contain facts from the actual documents?",
        "Like fact-checking a news article — are the claims backed by real sources?",
        "We check: do key words from expected answer appear in actual answer? 50%+ match = faithful."
    ),
    (
        "Retrieval Hit",
        "Did the retriever find chunks matching the expected section types?",
        "Like checking if the librarian brought books from the right shelf.",
        "Expected: budget question → budget chunks. If retriever returns hosting chunks instead = miss."
    ),
    (
        "Idempotent",
        "Running the same operation multiple times produces the same result.",
        "Like pressing an elevator button 5 times — you still go to the same floor, not floor 5.",
        "Our ingestion is idempotent: run twice = 89 chunks (not 178). Deterministic IDs + upsert."
    ),
    (
        "Batch\nProcessing",
        "Processing multiple items in one API call instead of one at a time.",
        "Like mailing 16 letters in one trip to the post office instead of 16 separate trips.",
        "We embed 16 chunks per API call. 89 chunks = 6 batches instead of 89 individual calls."
    ),
])

# ═══════════════════════════════════════════════════════════════
# 9. INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

add_category_table(doc, "9. Infrastructure & Azure Services", [
    (
        "Azure OpenAI",
        "Microsoft's hosted version of OpenAI models (GPT-4.1, embeddings) with enterprise security.",
        "Like having ChatGPT but hosted by Microsoft with your company's security and compliance.",
        "We use: text-embedding-3-small (embeddings) + GPT-4.1 (generation). Pay per token. Data stays in your Azure tenant."
    ),
    (
        "Azure AI Search",
        "Managed search service with vector, keyword, and semantic search built in.",
        "Like Google Search but for your private documents — finds by meaning AND exact words.",
        "Phase 2 replacement for ChromaDB. Adds: hybrid search, BM25, semantic reranking. $73.73/month (Basic tier)."
    ),
    (
        "Azure Document\nIntelligence",
        "AI service that extracts text, tables, and structure from documents including images.",
        "Like a super-powered scanner that can read text from photos and understand table layouts.",
        "Phase 2 replacement for python-pptx. Can OCR architecture diagrams! Layout API + Read API + Table API."
    ),
    (
        "RBAC",
        "Role-Based Access Control. Users see only data they're authorized for.",
        "Like hotel key cards — your card opens your room but not other guests' rooms.",
        "Phase 2: Azure Entra ID + search security filters. Architect A sees only Client A's documents."
    ),
    (
        "PII Masking",
        "Detecting and hiding personal information (emails, phone numbers) before indexing.",
        "Like blacking out names and addresses in a public document.",
        "Phase 2: Azure AI Language PII detection. Masks emails like roman.pantin@accenture.com before storing."
    ),
])

# ── Quick Reference Card ──
doc.add_page_break()
doc.add_heading('Quick Reference Card', level=1)

p = doc.add_paragraph()
run = p.add_run('The 10 Most Important Numbers in Our RAG System')
run.bold = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(88, 166, 255)

table = doc.add_table(rows=11, cols=3)
table.style = 'Table Grid'
headers = ["What", "Value", "Why This Number"]
for i, h in enumerate(headers):
    cell = table.rows[0].cells[i]
    cell.text = h
    for p2 in cell.paragraphs:
        for run2 in p2.runs:
            run2.bold = True
            run2.font.color.rgb = RGBColor(255, 255, 255)
            run2.font.size = Pt(10)
    set_cell_shading(cell, "1F4E79")

data = [
    ("Chunk size", "1500 chars (375 tokens)", "Embedding quality best at 200-400 tokens"),
    ("Chunk overlap", "150 chars (37 tokens)", "Preserves context at split boundaries"),
    ("Min chunk", "100 chars (25 tokens)", "Below = merge with next (too small)"),
    ("Top-K", "8 chunks per query", "Enough context without overwhelming LLM"),
    ("Min relevance", "0.35 similarity", "Below = drop (too irrelevant)"),
    ("Embedding dims", "1,536", "text-embedding-3-small output"),
    ("Temperature", "0.1", "Almost deterministic (factual RAG)"),
    ("Max output tokens", "2,000", "Enough for detailed architecture answers"),
    ("Conversation memory", "5 Q&A pairs", "Enables follow-up questions"),
    ("Cost per query", "Rs.0.27 (Mini)", "4000 input + 800 output tokens"),
]

for i, (what, value, why) in enumerate(data):
    row = table.rows[i + 1]
    row.cells[0].text = what
    row.cells[1].text = value
    row.cells[2].text = why
    for j in range(3):
        for p2 in row.cells[j].paragraphs:
            for run2 in p2.runs:
                run2.font.size = Pt(9)
        if i % 2 == 0:
            set_cell_shading(row.cells[j], "E8F0FE")

# ── Save ──
output = "docs/RAG_Cheatsheet.docx"
doc.save(output)
print(f"✅ Saved: {output}")
print(f"   9 categories, 50+ terms, all with layman analogies")
print(f"   + Quick Reference Card with the 10 key numbers")