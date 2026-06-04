"""
Generate Architecture Presentation — 11 slides with LLD placeholders
Run: python docs/generate_arch_ppt.py
Output: docs/Architecture_Presentation.pptx

After generating, manually insert the 3 LLD images into slides 4, 6, 9.
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

BG = (13, 17, 23)
TITLE_BLUE = RGBColor(88, 166, 255)
BODY_WHITE = RGBColor(220, 225, 235)
BODY_GRAY = RGBColor(160, 170, 185)
ACCENT_GREEN = RGBColor(46, 160, 67)
ACCENT_ORANGE = RGBColor(249, 115, 22)
TABLE_HEADER = RGBColor(30, 80, 160)
TABLE_LIGHT = RGBColor(25, 30, 42)
TABLE_DARK = RGBColor(35, 42, 58)


def set_bg(slide):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(*BG)


def add_title(slide, text, size=28):
    tx = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(0.8))
    tf = tx.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = True
    p.font.color.rgb = TITLE_BLUE


def add_subtitle(slide, text, top=0.9):
    tx = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(9), Inches(0.4))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(13)
    p.font.italic = True
    p.font.color.rgb = BODY_GRAY


def add_body(slide, text, top=1.4, left=0.5, width=9, height=5.5, size=13):
    tx = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tx.text_frame
    tf.word_wrap = True
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.color.rgb = BODY_WHITE
        p.space_after = Pt(4)


def add_centered_text(slide, text, top=2.5, size=20, color=BODY_GRAY):
    tx = slide.shapes.add_textbox(Inches(1), Inches(top), Inches(8), Inches(2))
    tf = tx.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = color
    p.font.italic = True
    p.alignment = PP_ALIGN.CENTER


def set_cell_shading(cell, r, g, b):
    shading = cell._element.get_or_add_tcPr()
    elem = shading.makeelement(qn('w:shd'), {qn('w:fill'): f'{r:02X}{g:02X}{b:02X}', qn('w:val'): 'clear'})
    shading.append(elem)


def add_table(slide, headers, rows, top=1.8, left=0.3, width=9.4, row_h=0.4):
    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl = slide.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top), Inches(width), Inches(row_h * n_rows))
    table = tbl.table
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(10)
            p.font.bold = True
            p.font.color.rgb = RGBColor(255, 255, 255)
            p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = TABLE_HEADER
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(9)
                p.font.color.rgb = BODY_WHITE
            cell.fill.solid()
            cell.fill.fore_color.rgb = TABLE_LIGHT if i % 2 == 0 else TABLE_DARK
    return table


def make_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(s)
    return s


# ═══════════════════════════════════════
prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
os.makedirs("docs", exist_ok=True)

# ── Slide 1: Title ──
s = make_slide(prs)
tx = s.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(8.4), Inches(3))
tf = tx.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "Architecture Knowledge Assistant"
p.font.size = Pt(34)
p.font.bold = True
p.font.color.rgb = TITLE_BLUE
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "Complete System Architecture"
p2.font.size = Pt(22)
p2.font.color.rgb = BODY_WHITE
p2.alignment = PP_ALIGN.CENTER
p3 = tf.add_paragraph()
p3.text = "\nPhase 1 → Phase 2 → Phase 3 Evolution"
p3.font.size = Pt(16)
p3.font.color.rgb = BODY_GRAY
p3.alignment = PP_ALIGN.CENTER
p4 = tf.add_paragraph()
p4.text = "\nArchitecture Team | June 2026"
p4.font.size = Pt(13)
p4.font.color.rgb = BODY_GRAY
p4.alignment = PP_ALIGN.CENTER

# ── Slide 2: The Evolution Story ──
s = make_slide(prs)
add_title(s, "The Evolution Story — Three Phases")
add_body(s, """Phase 1: FOUNDATION — "Can we build a RAG system?"
  ✅ Full RAG pipeline: Scan → Extract → Chunk → Embed → Retrieve → Generate
  ✅ ChromaDB (local vector store), semantic search only
  ✅ 12 Python modules, 89 chunks indexed, FastAPI + Streamlit
  ✅ Cost: ~₹8K-11K/month

Phase 2: ENTERPRISE — "Can we make it production-ready?"
  ✅ Azure AI Search (hybrid: vector + BM25 keyword search)
  ✅ Streaming responses (word-by-word), response caching
  ✅ Feature flags (switch Phase 1 ↔ 2 in .env)
  ✅ Azure Document Intelligence ready (OCR for diagrams)
  ✅ Cost: ~₹15K-18K/month

Phase 3: INTELLIGENT — "Can it think and plan?"
  ✅ Agentic RAG with OpenAI function calling (tool-use)
  ✅ Multi-model routing: Nano (simple) / Mini (standard) / Full (complex)
  ✅ Multi-hop retrieval: per-client searches, cross-client reasoning
  ✅ Self-correction: broadens search when initial results are insufficient
  ✅ Cost: ~₹700/month with model routing (93% less than Full for simple queries)""", size=12)

# ── Slide 3: Phase 1 Overview ──
s = make_slide(prs)
add_title(s, "Phase 1 — Foundation RAG")
add_subtitle(s, "ChromaDB + Semantic Search + Fixed Pipeline")
add_body(s, """What we built:
  • Document ingestion: PPT/PDF/DOCX → text extraction → preprocessing → chunking
  • Vector storage: ChromaDB (local, 89 chunks, 1536-dim embeddings)
  • Retrieval: Semantic search only (cosine similarity, top-K=8)
  • Generation: GPT-4.1 with grounding prompt + citations
  • Intent detection: comparison, explanation, specific, listing, general
  • Client auto-detection: folder name = client name (automatic metadata)
  • API: FastAPI with 5 endpoints (/health, /ingest, /query, /stats, /clients)
  • UI: Streamlit chat interface with sources panel

Key numbers:
  • 4 clients, 72 slides, 89 chunks indexed
  • 8 section types detected automatically
  • Answers include [Source: file.pptx, Slide X] citations
  • Evaluation framework: 10 golden Q&A pairs, 70% quality gate""", size=12)

# ── Slide 4: Phase 1 LLD ──
s = make_slide(prs)
add_title(s, "Phase 1 Architecture — Low-Level Design")
add_centered_text(s, "[ INSERT PHASE 1 LLD DIAGRAM HERE ]", top=2.8, size=22)
add_body(s, "→ Save the Phase 1 LLD image and insert it here (Delete this text after inserting)", top=5.5, size=10)

# ── Slide 5: Phase 2 Overview ──
s = make_slide(prs)
add_title(s, "Phase 2 — Enterprise RAG (Azure-Native)")
add_subtitle(s, "Hybrid Search + Streaming + Caching + Feature Flags")
add_body(s, """What changed from Phase 1:

Search (the biggest improvement):
  • ChromaDB (vector only) → Azure AI Search (vector + BM25 keyword + score fusion)
  • "account number 556008695729" → now found via BM25 exact match!
  • Comparison retrieval: 3+3 chunks → 4+4 chunks (more context)

New capabilities:
  • Streaming responses: words appear one-by-one (SSE via /query/stream)
  • Response caching: repeat queries return instantly (in-memory, 1hr TTL)
  • Feature flags: USE_AZURE_SEARCH, USE_DOC_INTELLIGENCE (switch in .env)
  • Azure Document Intelligence: ready but OFF (reserved for live demo)

What stayed the same:
  • Same ingestion pipeline (scan → extract → chunk → embed)
  • Same generation (GPT-4.1 + system prompt + citations)
  • Same UI (Streamlit) — but now with streaming display""", size=12)

# ── Slide 6: Phase 2 LLD ──
s = make_slide(prs)
add_title(s, "Phase 2 Architecture — Low-Level Design")
add_centered_text(s, "[ INSERT PHASE 2 LLD DIAGRAM HERE ]", top=2.8, size=22)
add_body(s, "→ Save the Phase 2 LLD image and insert it here (Delete this text after inserting)", top=5.5, size=10)

# ── Slide 7: Phase 1 vs Phase 2 Comparison ──
s = make_slide(prs)
add_title(s, "Phase 1 vs Phase 2 — What Changed")
add_table(s,
    ["Component", "Phase 1", "Phase 2", "Impact"],
    [
        ["Vector Store", "ChromaDB (local)", "Azure AI Search (cloud)", "Managed, scalable, hybrid search"],
        ["Search Type", "Semantic only", "Hybrid (vector + BM25 + fusion)", "Finds exact terms + meaning"],
        ["Reranking", "None", "Available on Basic tier", "Better precision on top results"],
        ["Streaming", "No (full response at once)", "Yes (word-by-word SSE)", "User sees first words in 1s"],
        ["Caching", "No", "In-memory (1hr TTL, 200 max)", "Repeat queries: instant + free"],
        ["Doc Extraction", "python-pptx only", "python-pptx OR Azure Doc Intelligence", "OCR reads diagram text"],
        ["Config Switch", "Hardcoded", "Feature flags in .env", "Switch Phase 1↔2 without code change"],
        ["API Endpoints", "5", "6 (added /query/stream)", "Streaming support"],
        ["Monthly Cost", "~₹8K-11K", "~₹15K-18K", "Azure AI Search adds ₹7K"],
    ], top=1.3, row_h=0.38)

# ── Slide 8: Phase 3 Overview ──
s = make_slide(prs)
add_title(s, "Phase 3 — Agentic RAG")
add_subtitle(s, "Intelligent Agent that Thinks, Plans, Acts, and Answers using Tools")
add_body(s, """What's new — the agent DECIDES what to do:

Agent Loop (Think → Act → Observe → Repeat):
  • LLM reads question → decides which tools to call
  • Executes tools (search, list clients, get stats)
  • Reads results → decides if more info needed → calls more tools
  • When satisfied → generates comprehensive answer with citations

Multi-Model Routing:
  • Simple queries ("How is DataStories hosted?") → GPT-4.1 Mini ($0.001)
  • Complex queries ("Compare budgets across all clients") → GPT-4.1 Full ($0.014)
  • Classification tasks → GPT-4.1 Nano ($0.0002)
  • Average 80% cost reduction on simple queries

Self-Correction:
  • Agent searches with section_type="budget" → 0 results
  • Agent adapts: removes filter, searches broader → finds results
  • Phase 1-2 would just return "no information found"

Real results:
  • Simple query: 1 tool call, 1 iteration, Mini model, 10.7s
  • Budget comparison: 4 tool calls, 2 iterations, Full model, 15.2s
  • Cross-client AWS: 7 tool calls, 5 iterations, Full model, 19.3s""", size=11)

# ── Slide 9: Phase 3 LLD ──
s = make_slide(prs)
add_title(s, "Phase 3 Architecture — Low-Level Design")
add_centered_text(s, "[ INSERT PHASE 3 LLD DIAGRAM HERE ]", top=2.8, size=22)
add_body(s, "→ Save the Phase 3 LLD image and insert it here (Delete this text after inserting)", top=5.5, size=10)

# ── Slide 10: Complete Journey By Numbers ──
s = make_slide(prs)
add_title(s, "The Complete Journey — By The Numbers")
add_table(s,
    ["Metric", "Phase 1", "Phase 2", "Phase 3"],
    [
        ["Search Type", "Semantic only", "Hybrid (vector+BM25)", "Hybrid + agent-chosen"],
        ["LLM Models", "GPT-4.1 (all queries)", "GPT-4.1 (all queries)", "Mini/Full/Nano (routed)"],
        ["Tool Calls/Query", "0 (fixed pipeline)", "0 (fixed pipeline)", "1-21 (dynamic)"],
        ["Iterations/Query", "1 (always)", "1 (always)", "1-6 (adaptive)"],
        ["Self-Correction", "❌ No", "❌ No", "✅ Broadens search"],
        ["Cross-Client Query", "Limited (1 search)", "Better (hybrid)", "✅ Per-client searches"],
        ["Streaming", "❌ No", "✅ Word-by-word", "✅ Word-by-word"],
        ["Caching", "❌ No", "✅ In-memory (1hr)", "✅ In-memory (1hr)"],
        ["Simple Query Cost", "$0.014", "$0.014", "$0.001 (93% less)"],
        ["Exact Term Search", "❌ Misses", "✅ BM25 finds", "✅ BM25 finds"],
        ["Feature Flags", "❌ No", "✅ Switch in .env", "✅ Switch in .env"],
    ], top=1.2, row_h=0.35)

# ── Slide 11: Thank You ──
s = make_slide(prs)
tx = s.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(8.4), Inches(4))
tf = tx.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "Thank You"
p.font.size = Pt(42)
p.font.bold = True
p.font.color.rgb = TITLE_BLUE
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "\nQuestions & Discussion"
p2.font.size = Pt(22)
p2.font.color.rgb = BODY_GRAY
p2.alignment = PP_ALIGN.CENTER
p3 = tf.add_paragraph()
p3.text = "\n\n3 Phases | 89 Chunks | 4 Clients | Hybrid Search | Agentic RAG"
p3.font.size = Pt(14)
p3.font.color.rgb = BODY_GRAY
p3.alignment = PP_ALIGN.CENTER
p4 = tf.add_paragraph()
p4.text = "\nArchitecture Team | June 2026"
p4.font.size = Pt(14)
p4.font.color.rgb = BODY_GRAY
p4.alignment = PP_ALIGN.CENTER
p5 = tf.add_paragraph()
p5.text = '\n"The best way to learn RAG is to build RAG."'
p5.font.size = Pt(13)
p5.font.italic = True
p5.font.color.rgb = RGBColor(100, 110, 130)
p5.alignment = PP_ALIGN.CENTER

# ═══════════════════════════════════════
output = "docs/Architecture_Presentation.pptx"
prs.save(output)
print(f"✅ Saved: {output}")
print(f"   11 slides generated")
print(f"")
print(f"📌 NEXT STEPS:")
print(f"   1. Open docs/Architecture_Presentation.pptx in PowerPoint")
print(f"   2. Slide 4: Insert Phase 1 LLD image (delete placeholder text)")
print(f"   3. Slide 6: Insert Phase 2 LLD image (delete placeholder text)")
print(f"   4. Slide 9: Insert Phase 3 LLD image (delete placeholder text)")
print(f"   5. Present! 🚀")