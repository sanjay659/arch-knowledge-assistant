"""
Generate RAG Complete Guide — Batch 4 (Topics 13-16)
Run: python docs/generate_guide_batch4.py
Output: docs/RAG_Guide_Batch4.docx
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
    return doc.add_paragraph(text)


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
# TOPIC 13: COST ANALYSIS
# ═══════════════════════════════════════════════════════════════

doc.add_heading('13. Cost Analysis', level=1)

doc.add_heading('13.1 How Azure OpenAI Pricing Works', level=2)
add_body(doc,
    'Azure OpenAI charges per TOKEN — both input (what you send) and output (what you receive). '
    'There is no monthly subscription or per-user fee. You pay only for what you use.')
add_body(doc, 'Two types of charges in our system:')
add_bullet(doc, 'Embedding calls: Charged on INPUT tokens only (no output). Used for indexing and query embedding.')
add_bullet(doc, 'Chat completion calls: Charged on both INPUT and OUTPUT tokens. Used for answer generation.')

doc.add_heading('13.2 Per-Query Cost Breakdown', level=2)
add_body(doc, 'What happens when someone asks "How is DataStories hosted?":')
add_table(doc,
    ["Step", "API Call", "Tokens", "Model", "Cost"],
    [
        ["1. Embed query", "Embeddings API", "~20 input", "text-embedding-3-small ($0.02/1M)", "$0.0000004"],
        ["2. Retrieve chunks", "ChromaDB local", "0", "N/A (local)", "$0.00"],
        ["3. Build prompt", "None (local)", "0", "N/A", "$0.00"],
        ["4. Generate answer", "Chat Completions", "~4,000 input", "GPT-4.1 Mini ($0.40/1M input)", "$0.0016"],
        ["5. Receive answer", "Chat Completions", "~800 output", "GPT-4.1 Mini ($1.60/1M output)", "$0.00128"],
        ["TOTAL", "", "", "", "$0.00288 (Rs.0.27)"],
    ]
)
add_body(doc,
    'One comprehensive architecture answer with citations costs less than 30 paise. '
    'This is why RAG is cost-effective compared to fine-tuning.')

doc.add_heading('13.3 Monthly Cost Projections', level=2)
add_body(doc, 'Scenario: 6 architects, 10 queries/day each = 60 queries/day = 1,800 queries/month')

add_table(doc,
    ["Component", "Calculation", "Monthly USD", "Monthly INR"],
    [
        ["AI — Embeddings (queries)", "1,800 x 20 tokens x $0.02/1M", "$0.001", "Rs.0.07"],
        ["AI — Generation (Mini)", "1,800 x $0.00288", "$5.18", "Rs.492"],
        ["AI — Ingestion (one-time)", "89 chunks x 300 tokens x $0.02/1M", "$0.001", "Rs.0.05"],
        ["AI SUBTOTAL", "", "$5.18", "Rs.492"],
        ["", "", "", ""],
        ["VM (D2as_v5)", "$0.086/hour x 730 hours", "$62.78", "Rs.5,959"],
        ["Blob Storage (100GB Hot)", "100GB x $0.018/GB", "$1.80", "Rs.171"],
        ["INFRA SUBTOTAL", "", "$64.58", "Rs.6,130"],
        ["", "", "", ""],
        ["GRAND TOTAL", "", "$69.76", "Rs.6,622"],
    ]
)

add_body(doc, 'Key insight: The AI token cost (Rs.492) is only 7.4% of the total. '
    'Infrastructure (VM) dominates at 90%. This means:')
add_bullet(doc, 'Switching from GPT-4.1 Mini to Full increases AI cost 5x but total cost only by ~30%')
add_bullet(doc, 'The biggest cost optimization is VM right-sizing, not model selection')
add_bullet(doc, 'In Phase 2 (Azure App Service), you can use consumption plan to reduce infra cost further')

doc.add_heading('13.4 Ingestion Cost', level=2)
add_code(doc,
    'Full re-indexing (all 4 clients, 89 chunks):\n'
    '  89 chunks x ~300 avg tokens = 26,700 tokens\n'
    '  26,700 x ($0.02 / 1,000,000) = $0.000534\n'
    '  = Rs.0.05 (five paise)\n\n'
    'Even if you re-index daily for a month:\n'
    '  30 x Rs.0.05 = Rs.1.50/month\n\n'
    'Ingestion cost is essentially FREE.\n'
    'Never let embedding cost influence your re-indexing frequency.')

doc.add_heading('13.5 Phase 1 vs Phase 2 Cost Comparison', level=2)
add_table(doc,
    ["Component", "Phase 1 Monthly", "Phase 2 Monthly", "Difference"],
    [
        ["Compute (VM / App Service)", "Rs.5,959", "Rs.3,800", "-Rs.2,159 (consumption plan)"],
        ["Vector Store (Chroma / AI Search Basic)", "Rs.0 (local)", "Rs.6,998", "+Rs.6,998"],
        ["Storage (local / Blob)", "Rs.171", "Rs.171", "Rs.0"],
        ["AI Tokens", "Rs.492", "Rs.492", "Rs.0"],
        ["Key Vault", "Rs.0", "Rs.50", "+Rs.50"],
        ["Monitor / App Insights", "Rs.0", "Rs.200", "+Rs.200"],
        ["TOTAL", "Rs.6,622", "Rs.11,711", "+Rs.5,089"],
    ]
)
add_body(doc,
    'Phase 2 costs more because Azure AI Search (Basic tier at $73.73/month) replaces free local ChromaDB. '
    'However, the quality improvement (hybrid search + semantic reranking) significantly improves answer accuracy. '
    'The ROI comes from better answers, not lower cost.')

doc.add_heading('13.6 Cost at Scale', level=2)
add_body(doc, 'What happens as usage grows:')
add_table(doc,
    ["Scale", "Queries/Month", "AI Cost (Mini)", "AI Cost (Full)", "Key Decision"],
    [
        ["Current (6 users)", "1,800", "Rs.492", "Rs.2,460", "Mini is sufficient"],
        ["Team grows (15 users)", "4,500", "Rs.1,230", "Rs.6,150", "Mini still fine, monitor quality"],
        ["Department (50 users)", "15,000", "Rs.4,100", "Rs.20,500", "Consider Nano for simple queries"],
        ["Organization (200 users)", "60,000", "Rs.16,400", "Rs.82,000", "Must use multi-model routing"],
        ["Enterprise (1000 users)", "300,000", "Rs.82,000", "Rs.410,000", "Caching + batching essential"],
    ]
)
add_body(doc,
    'At scale, the multi-model routing strategy (Nano for classification, Mini for Q&A, Full for comparison) '
    'becomes essential. Caching frequent queries can reduce costs by 40-60%.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 14: EVALUATION FRAMEWORK
# ═══════════════════════════════════════════════════════════════

doc.add_heading('14. Evaluation Framework', level=1)

doc.add_heading('14.1 Why Evaluation is NOT Optional', level=2)
add_body(doc,
    'Without evaluation, you are flying blind. "It seems to work" is NOT the same as "it works correctly." '
    'Evaluation answers the question: "How good is our RAG system, measured objectively?"')
add_body(doc, 'Evaluation enables:')
add_bullet(doc, 'Knowing if a change IMPROVED or BROKE the system')
add_bullet(doc, 'Justifying the system to stakeholders with numbers')
add_bullet(doc, 'Finding and fixing specific failure modes')
add_bullet(doc, 'Comparing different configurations (chunk size A vs B, model X vs Y)')
add_bullet(doc, 'Setting quality gates in CI/CD (deploy only if accuracy >= 70%)')

doc.add_heading('14.2 Our Three Evaluation Metrics', level=2)
add_table(doc,
    ["Metric", "What It Checks", "How We Measure", "Why It Matters"],
    [
        ["Retrieval Hit", "Did we find chunks matching expected section types?", "Check if retrieved chunks contain expected section_type values", "Catches retrieval failures BEFORE they reach the LLM"],
        ["Faithfulness", "Does the answer contain key facts from the expected answer?", "Extract significant words from expected answer, check if 50%+ appear in actual answer", "Catches hallucination — making up information not in the documents"],
        ["Citation Present", "Does the answer include source references?", "Regex search for [Source: ...] or Slide patterns", "Catches unverifiable answers — citations are non-negotiable for enterprise"],
    ]
)

doc.add_heading('14.3 Golden Q&A Pairs', level=2)
add_body(doc,
    'Evaluation requires a "ground truth" — questions with known correct answers. '
    'We created 10 golden Q&A pairs based on the real DataStories PPT:')

add_table(doc,
    ["#", "Question", "Expected Section Types", "Difficulty"],
    [
        ["1", "Explain DataStories hosting architecture", "hosting, current_architecture", "Medium"],
        ["2", "How is DataStories currently hosted?", "current_architecture, hosting", "Easy"],
        ["3", "What is the proposed target architecture?", "proposed_architecture", "Medium"],
        ["4", "Compare current vs proposed for DataStories", "current_architecture, proposed_architecture", "Hard"],
        ["5", "What is the hosting integration process?", "timeline, general", "Medium"],
        ["6", "What is the website migration plan?", "migration", "Easy"],
        ["7", "What are the success criteria?", "success_criteria", "Easy"],
        ["8", "What security standards must be complied with?", "security", "Medium"],
        ["9", "What is the budget for hosting integration?", "budget", "Medium"],
        ["10", "What is the inventory and assessment summary?", "inventory, hosting", "Medium"],
    ]
)

doc.add_heading('14.4 Quality Gate', level=2)
add_body(doc,
    'We set a quality gate at 70% overall accuracy. This means:')
add_code(doc,
    'Overall Accuracy = (Retrieval Accuracy + Faithfulness Accuracy + Citation Accuracy) / 3\n\n'
    'If Overall >= 70%  -->  QUALITY GATE PASSED (safe to deploy/present)\n'
    'If Overall <  70%  -->  QUALITY GATE FAILED (needs fixing before deployment)\n\n'
    'Example result:\n'
    '  Retrieval:    9/10 = 90%\n'
    '  Faithfulness: 8/10 = 80%\n'
    '  Citation:     8/10 = 80%\n'
    '  Overall:      (90 + 80 + 80) / 3 = 83%  -->  PASSED')

doc.add_heading('14.5 What to Do When Evaluation Fails', level=2)
add_table(doc,
    ["Failure", "Symptom", "Root Cause", "Fix"],
    [
        ["Low retrieval hit", "Wrong chunks retrieved", "Keywords not matching section type, or threshold too high", "Add keywords to preprocessor, lower min_relevance"],
        ["Low faithfulness", "Answer missing key facts", "Relevant chunks not retrieved, or LLM ignoring context", "Check retrieval first, then adjust prompt"],
        ["Low citation", "No [Source: ...] in answer", "System prompt not enforced, or LLM too creative", "Strengthen citation instruction in prompt, lower temperature"],
        ["Wrong client", "Answer contains other client's data", "Client not detected, metadata filter not applied", "Check client detection logic, verify metadata tagging"],
        ["Hallucination", "Answer contains facts not in any document", "LLM using training data instead of context", "Strengthen 'ONLY from context' rule, add 'I don't know' examples"],
    ]
)

doc.add_heading('14.6 Continuous Evaluation', level=2)
add_body(doc, 'Evaluation is not a one-time activity. Run it:')
add_bullet(doc, 'After every code change (did the change improve or break quality?)')
add_bullet(doc, 'After adding new documents (does the system handle new content well?)')
add_bullet(doc, 'After changing chunk size or model (measure the impact)')
add_bullet(doc, 'Monthly (track quality trends over time)')
add_body(doc,
    'In Phase 2, evaluation can be automated in CI/CD: every code push triggers evaluation, '
    'and deployment is blocked if the quality gate fails.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 15: REAL BUGS WE HIT & FIXED
# ═══════════════════════════════════════════════════════════════

doc.add_heading('15. Real Bugs We Hit & Fixed', level=1)

add_body(doc,
    'These are REAL bugs encountered while building this system. Every one is a common RAG pitfall '
    'that tutorials never mention. Learning from these will save you weeks of debugging on future projects.')

doc.add_heading('15.1 Bug 1: "shape is not a placeholder"', level=2)
add_table(doc,
    ["Aspect", "Detail"],
    [
        ["Error", "ValueError: shape is not a placeholder"],
        ["Where", "extractor.py — accessing shape.placeholder_format"],
        ["Root Cause", "python-pptx attribute EXISTS on all shapes (hasattr returns True) but ACCESSING it on non-placeholder shapes raises ValueError"],
        ["Impact", "Entire PPT extraction failed — 0 slides extracted from a 26-slide PPT"],
        ["Fix", "Wrap placeholder detection in try/except ValueError"],
        ["Lesson", "Real enterprise PPTs break library assumptions. ALWAYS wrap shape processing in try/except."],
    ]
)

doc.add_heading('15.2 Bug 2: Dimension Mismatch (1536 vs 384)', level=2)
add_table(doc,
    ["Aspect", "Detail"],
    [
        ["Error", "Collection expecting embedding with dimension of 1536, got 384"],
        ["Where", "retriever.py — using query_texts parameter in ChromaDB"],
        ["Root Cause", "ChromaDB auto-downloaded its default model (all-MiniLM-L6-v2, 384 dims) when we used query_texts. Our indexed chunks used Azure OpenAI (1536 dims)."],
        ["Impact", "Zero retrieval results for every query — system completely non-functional"],
        ["Fix", "Embed queries ourselves with Azure OpenAI, pass as query_embeddings instead of query_texts"],
        ["Lesson", "ALWAYS use the SAME embedding model for indexing AND querying. No exceptions."],
    ]
)

doc.add_heading('15.3 Bug 3: Module Import Errors (sys.path)', level=2)
add_table(doc,
    ["Aspect", "Detail"],
    [
        ["Error", "ModuleNotFoundError: No module named 'src'"],
        ["Where", "Running python src/ingestion/chunker.py directly"],
        ["Root Cause", "Python adds the FILE's directory to sys.path, not the PROJECT ROOT. So 'from src.ingestion.extractor' fails because Python looks for 'src' inside 'src/ingestion/'."],
        ["Impact", "Cannot run modules individually for testing"],
        ["Fix", "Use python -m src.ingestion.chunker (module flag) OR add sys.path.insert(0, project_root) at top of file"],
        ["Lesson", "Python module resolution differs from C# project references. Use -m flag or fix sys.path explicitly."],
    ]
)

doc.add_heading('15.4 Bug 4: Settings Attribute Mismatch', level=2)
add_table(doc,
    ["Aspect", "Detail"],
    [
        ["Error", "AttributeError: 'Settings' object has no attribute 'DOCUMENTS_DIR'"],
        ["Where", "indexer.py using UPPERCASE names, settings.py had lowercase"],
        ["Root Cause", "Two versions of settings.py evolved during development. Indexer assumed DOCUMENTS_DIR but actual attribute was documents_dir."],
        ["Impact", "Indexer crashes at startup — cannot find document path"],
        ["Fix", "Check actual attribute names with dir(settings), use consistent naming"],
        ["Lesson", "Configuration naming must be consistent across ALL modules. One mismatch = crash."],
    ]
)

doc.add_heading('15.5 Meta-Lesson', level=2)
add_body(doc,
    'Tutorial RAG works on clean data with simple configurations. '
    'Production RAG requires handling real-world messiness at every step: '
    'broken PPT shapes, library quirks, dimension mismatches, path issues, '
    'and configuration inconsistencies.')
add_body(doc,
    'The difference between a demo and a real system is not the AI model — '
    'it is the engineering around the model: error handling, validation, '
    'logging, testing, and defensive coding.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# TOPIC 16: WHAT WE BUILT — MODULE INVENTORY
# ═══════════════════════════════════════════════════════════════

doc.add_heading('16. What We Built — Module Inventory', level=1)

doc.add_heading('16.1 Complete Module List', level=2)
add_table(doc,
    ["#", "File", "Purpose", "Key Concept Learned"],
    [
        ["1", "config/settings.py", "Centralized configuration", "Pydantic settings, .env loading, @lru_cache singleton"],
        ["2", "src/ingestion/scanner.py", "Discover files in folders", "Folder name = client name (auto metadata), Path objects"],
        ["3", "src/ingestion/extractor.py", "PPT/PDF/DOCX to text", "Shape extraction, table handling, try/except per shape"],
        ["4", "src/ingestion/preprocessor.py", "Clean + classify text", "Regex boilerplate removal, keyword classification, hybrid LLM fallback"],
        ["5", "src/ingestion/chunker.py", "Merge/split into chunks", "Structure-aware chunking, overlap, accumulator pattern"],
        ["6", "src/indexing/indexer.py", "Embed + store in ChromaDB", "Batch embedding, deterministic IDs, idempotent upsert"],
        ["7", "src/retrieval/retriever.py", "Semantic search + filtering", "Metadata filtering, intent detection, comparison retrieval, same-model rule"],
        ["8", "src/generation/generator.py", "LLM answers with citations", "System prompt design, grounded generation, temperature control"],
        ["9", "src/pipeline/query_pipeline.py", "E2E query orchestration", "Intent routing, conversation memory, sliding window"],
        ["10", "src/pipeline/ingest_pipeline.py", "E2E ingestion orchestration", "Pipeline pattern, error isolation, idempotent re-indexing"],
        ["11", "src/api/main.py", "REST API (FastAPI)", "Lazy initialization, CORS, Pydantic request/response models"],
        ["12", "ui/app.py", "Chat UI (Streamlit)", "Session state, chat interface, API integration"],
    ]
)

doc.add_heading('16.2 System Statistics', level=2)
add_table(doc,
    ["Metric", "Value"],
    [
        ["Total Python modules", "12"],
        ["Total client documents", "4 PPTs"],
        ["Total slides processed", "72"],
        ["Meaningful slides (after filtering)", "67"],
        ["Total chunks indexed", "89"],
        ["Unique clients", "4 (DataStories, MediFlow, RetailEdge, TechNova)"],
        ["Section types detected", "8 (current_architecture, proposed_architecture, hosting, integration, migration, operations, success_criteria, contacts)"],
        ["API endpoints", "5 (/health, /ingest, /query, /stats, /clients)"],
        ["Evaluation questions", "10 golden Q&A pairs"],
        ["Unit tests", "20+ test cases across 3 test files"],
    ]
)

doc.add_heading('16.3 Sample Query Results', level=2)
add_body(doc, 'Actual results from our system:')
add_table(doc,
    ["Query", "Client Detected", "Intent", "Chunks Retrieved", "Tokens Used", "Time", "Quality"],
    [
        ["How is DataStories hosted?", "DataStories", "explanation", "8", "1,979", "5.7s", "Excellent"],
        ["Explain MediFlow architecture", "MediFlow", "explanation", "8", "4,367", "8.4s", "Excellent"],
        ["What is the budget for TechNova?", "TechNova", "explanation", "8", "4,738", "3.3s", "Excellent"],
        ["Compare current vs proposed RetailEdge", "RetailEdge", "comparison", "6 (3+3)", "6,996", "13.1s", "Excellent"],
        ["Which clients use AWS?", "All (none)", "listing", "8", "1,991", "3.4s", "Excellent"],
        ["What about the security standards?", "DataStories (memory)", "general", "8", "2,851", "7.6s", "Good"],
    ]
)

add_body(doc, 'Total cost of all 6 test queries:')
add_code(doc,
    'Total tokens: 22,922\n'
    'Input cost:  ~17,000 tokens x ($0.40/1M) = $0.0068\n'
    'Output cost: ~5,900 tokens x ($1.60/1M) = $0.0094\n'
    'Total: $0.016 = Rs.1.52\n\n'
    'Six comprehensive architecture answers for Rs.1.52')

doc.add_heading('16.4 What the Answers Look Like', level=2)
add_body(doc, 'Sample answer for "How is DataStories currently hosted?":')
add_code(doc,
    '### Summary\n'
    'DataStories is currently hosted using a combination of AWS and\n'
    'a third-party platform called Unbounce.\n\n'
    '### Details\n'
    '- AWS Hosting:\n'
    '  - The main website (https://datastories.com/) is hosted on AWS\n'
    '    [Source: blueprint.pptx, Slide 10]\n'
    '  - AWS account number: 556008695729\n'
    '    [Source: blueprint.pptx, Slide 10]\n\n'
    '- Third-Party Hosting (Unbounce):\n'
    '  - demo.datastories.com and discover.datastories.com\n'
    '    are hosted on Unbounce\n'
    '    [Source: blueprint.pptx, Slide 10]\n'
    '  - These will be decommissioned\n'
    '    [Source: blueprint.pptx, Slide 4]\n\n'
    '| Website                    | Platform | Status      |\n'
    '|----------------------------|----------|-------------|\n'
    '| datastories.com            | AWS      | Retained    |\n'
    '| demo.datastories.com       | Unbounce | To be removed|\n'
    '| discover.datastories.com   | Unbounce | To be removed|')

add_body(doc,
    'Note: The LLM generated the summary table on its own — we did not instruct it to create a table. '
    'It understood the data was tabular and formatted it accordingly. '
    'Every factual claim has a citation to the source slide.')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════

output_path = "docs/RAG_Guide_Batch4.docx"
doc.save(output_path)
print(f"✅ Saved: {output_path}")
print(f"   Topics covered: 13-16")
print(f"   (Cost Analysis, Evaluation, Bugs, Module Inventory)")