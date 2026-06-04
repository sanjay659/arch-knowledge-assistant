# 🏗️ The Complete RAG Guide
## From Theory to Production

### Architecture Knowledge Assistant — A Hands-On RAG Learning Journey

**Author:** Architecture Team
**Date:** June 2026
**Version:** 1.0

> After reading this guide, you will confidently understand how to design,
> build, evaluate, and modernize a production-grade RAG system.
> Every concept is explained with real code, real bugs, and real cost numbers
> from a working project — not from theory or tutorials.

---

## 📑 Table of Contents

| # | Section | What You'll Learn |
|---|---------|-------------------|
| 1 | What is RAG? | The concept, why it exists, how it compares to alternatives |
| 2 | Problem Statement | Our use case — why RAG fits |
| 3 | Architecture Overview | Phase 1 (local) and Phase 2 (Azure-native) |
| 4 | The RAG Pipeline | Write path (ingestion) and Read path (query) |
| 5 | Deep Dive: Each Layer | Extraction, preprocessing, chunking, embeddings, retrieval, generation |
| 6 | Chunking — The Most Critical Decision | Chunk size analysis with real examples |
| 7 | LLM Model Selection Framework | How to choose models, multi-model routing |
| 8 | Embedding Model Selection | Which model, why, and the critical same-model rule |
| 9 | Cost Analysis | Per-query, monthly, and scaling projections |
| 10 | What We Built | Complete module inventory |
| 11 | Real Bugs We Hit | 4 production bugs with fixes and lessons |
| 12 | Phase 2 Modernization | Azure-native migration path |
| 13 | Missing Links & Gaps | What's not implemented yet and why |
| 14 | Advanced RAG Patterns | Agentic, multimodal, graph, corrective RAG |
| 15 | Next Goals | Short, medium, long-term roadmap |
| 16 | Key Takeaways | 10 lessons from building this system |
| 17 | Appendix | Tech stack, API, folder structure, sample outputs |

---

# 1. What is RAG?

## 1.1 Definition

**RAG (Retrieval-Augmented Generation)** is a pattern where an LLM generates answers using information **retrieved from your own documents**, rather than relying solely on its training data.

Traditional LLM:                                              │
│    Question ──→ LLM (training data only) ──→ Answer            │
│                                                                │
│    ⚠️ May hallucinate. No private data. Can't cite sources.   │
│                                                                │
│  RAG:                                                          │
│    Question ──→ RETRIEVE relevant docs ──→ LLM + docs ──→ Answer│
│                                                                │
│    ✅ Grounded in YOUR data. Cited. Accurate. Updatable.       │
│                                                                │
└──────────────────────────────────────────────────────────────┘

## 1.2 Why RAG Exists — The Three Approaches Compared

When you want an LLM to know about YOUR data, you have three options:

| Approach | How It Works | Pros | Cons | Cost | When to Use |
|----------|-------------|------|------|------|-------------|
| **Raw LLM** | Ask GPT directly, no custom data | Simple, fast | Hallucinations, no private data, no citations | Free (just API) | General knowledge Q&A |
| **Fine-tuning** | Retrain the model on your data | Deep domain knowledge, no retrieval needed | Very expensive ($1000s+), data goes stale, hard to update | $$$$ | When you have massive stable datasets |
| **RAG** | Retrieve docs at query time, pass to LLM | Fresh data, cited, affordable, updatable | Needs pipeline engineering, retrieval quality matters | $-$$ | Enterprise docs, knowledge bases, support bots |

**RAG is the sweet spot** for most enterprise use cases because:
- Your architecture documents change (new PPTs every week)
- Answers must be traceable to source documents
- You can't afford to fine-tune every time a PPT is updated
- You need different clients' data isolated

## 1.3 The RAG Iceberg — What Tutorials Don't Teach

Most RAG tutorials cover only what's above the water. Production RAG requires everything below.


          ╔═══════════════════════════════════╗
           ▲    ║  ABOVE THE WATER (Beginner)       ║
           │    ║                                   ║
           │    ║  • LangChain / LlamaIndex basics  ║
           │    ║  • Data loaders (PDF, PPT)        ║
           │    ║  • Chunking and embeddings        ║
           │    ║  • Vector databases (FAISS/Chroma)║
           │    ║  • Prompt templates               ║
           │    ║  • Basic retrieval + generation   ║
      ~~~~~~~~~ ╚═══════════════════════════════════╝ ~~~~~~~~~
           │    ┌───────────────────────────────────┐
           │    │  BELOW THE WATER (Builder)        │
           │    │                                   │
           │    │  • Preprocessing & cleaning       │
           │    │  • Section type classification    │
           │    │  • Metadata filtering             │
           │    │  • Query intent detection         │
           │    │  • Reranking (cross-encoders)     │
           │    │  • Evaluation metrics             │
           │    │  • Hallucination control          │
           │    │  • Multi-hop retrieval            │
           │    │  • PII masking                    │
           │    │  • Caching & latency optimization │
           │    │  • Feedback loops                 │
           │    │  • Embedding model selection      │
           │    │  • LLM model routing              │
           │    │  • Cost optimization              │
           │    │  • Secure retrieval (RBAC)        │
           │    │  • Version-aware retrieval        │
           ▼    └───────────────────────────────────┘

Our project covers BOTH layers — that's what makes this guide different.

## 1.4 How RAG Works (The 30-Second Version)


Step 1: INGESTION (one-time per document)
Your PPT ──→ Extract text ──→ Split into chunks ──→ Convert to vectors ──→ Store
Step 2: QUERY (every time someone asks a question)
"How is Client1 hosted?"
│
▼
Convert question to vector
│
▼
Find most similar chunks in vector store
│
▼
Pass chunks + question to LLM
│
▼
"Client1 is hosted on AWS with account 556008695729.
The main website is on AWS, with two additional sites
on Unbounce planned for decommissioning.
[Source: blueprint.pptx, Slide 9]"

That's RAG in a nutshell. The rest of this guide explains each step in depth.

---

# 2. Problem Statement

## 2.1 The Scenario


┌────────────────────────────────────────────────────────────────┐
│                     ARCHITECTURE TEAM                          │
│                                                                │
│  👤 Architect 1 ──→ Client A PPTs (only they know this)       │
│  👤 Architect 2 ──→ Client B PPTs (only they know this)       │
│  👤 Architect 3 ──→ Client C PPTs (only they know this)       │
│  👤 Architect 4 ──→ Client D PPTs (only they know this)       │
│  👤 Architect 5 ──→ Client E PPTs (only they know this)       │
│  👤 Architect 6 ──→ Client F PPTs (only they know this)       │
│                                                                │
│  ❌ PROBLEM: Knowledge is SILOED                               │
│  ❌ Nobody knows the other's client architecture               │
│  ❌ Finding info = manually opening and searching PPTs         │
│  ❌ Onboarding new members takes weeks                         │
│  ❌ Cross-client insights are nearly impossible                │
└────────────────────────────────────────────────────────────────┘

## 2.2 The Solution


┌────────────────────────────────────────────────────────────────┐
│                ARCHITECTURE KNOWLEDGE ASSISTANT                │
│                                                                │
│  👤 Any architect asks:                                        │
│     "Explain Client A architecture"                            │
│     "What is the budget for Client B?"                         │
│     "Compare current vs proposed for Client C"                 │
│     "Which clients use AWS?"                                   │
│                                                                │
│  🤖 System:                                                    │
│     1. Finds relevant slides from the right client's PPTs      │
│     2. Generates a clear answer with citations                 │
│     3. Shows source: [blueprint.pptx, Slide 9]                 │
│                                                                │
│  ✅ Knowledge is SHARED                                        │
│  ✅ Answers in seconds (not hours of searching)                │
│  ✅ Cross-client queries work                                  │
│  ✅ New members can onboard instantly                          │
└────────────────────────────────────────────────────────────────┘

## 2.3 Why This is a GOOD RAG Use Case

Not every problem needs RAG. Here's why ours does:

| Criterion | Our Scenario | RAG Fit |
|-----------|-------------|---------|
| **Knowledge type** | Architecture PPTs (semi-structured text + tables) | ✅ Perfect for text extraction + retrieval |
| **Data freshness** | PPTs updated weekly/monthly | ✅ RAG re-indexes easily (fine-tuning can't) |
| **Question types** | Natural language ("explain", "compare", "what is") | ✅ Exactly what RAG handles |
| **Answer source** | Must come from actual documents | ✅ RAG provides citations |
| **Data sensitivity** | Client-specific, internal only | ✅ RAG keeps data local (no training data leak) |
| **User count** | 6 architects (low volume) | ✅ Cost-effective at this scale |
| **Multiple sources** | Different clients = different PPTs | ✅ Metadata filtering separates them |

## 2.4 What the System Actually Processes

Our test dataset:

| Client | File | Slides | Industry | Migration Type |
|--------|------|--------|----------|---------------|
| DataStories | Hosting Integration Blueprint | 26 | Analytics/SaaS | AWS → GMCS |
| TechNova | Hosting Blueprint | 17 | SaaS Platform | AWS → Azure |
| MediFlow | Cloud Migration Blueprint | 14 | Healthcare | On-Prem → AWS |
| RetailEdge | Architecture Blueprint | 15 | E-Commerce | Hybrid Multi-Cloud |

**Total: 72 slides → 89 indexed chunks → searchable in < 1 second**

## 2.5 Types of Questions the System Handles

| # | Question Type | Example | What Happens |
|---|-------------|---------|-------------|
| 1 | **Explain architecture** | "Explain DataStories architecture" | Multi-chunk summary from one client |
| 2 | **Current design** | "How is MediFlow currently hosted?" | Filters current_architecture chunks |
| 3 | **Proposed design** | "What is the target architecture?" | Filters proposed_architecture chunks |
| 4 | **Compare** | "Compare current vs proposed for RetailEdge" | Two separate retrievals → structured comparison |
| 5 | **Budget** | "What is the budget for TechNova?" | Filters budget-related chunks |
| 6 | **Security** | "What security standards apply?" | Retrieves security/compliance chunks |
| 7 | **Cross-client** | "Which clients use AWS?" | Searches ALL clients (no filter) |
| 8 | **Specific component** | "How does the API gateway work?" | Precise semantic search |
| 9 | **Follow-up** | "What about the risks?" | Uses conversation memory |
| 10 | **Listing** | "List all migration milestones" | Retrieves timeline chunks |
