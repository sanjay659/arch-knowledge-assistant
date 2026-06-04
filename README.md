# 🏗️ Architecture Knowledge Assistant

> **RAG-powered internal tool** for architecture teams to query client architecture documents using natural language.

![Phase](https://img.shields.io/badge/Phase-1%20Local%20Self--Hosted-blue)
![Python](https://img.shields.io/badge/Python-3.11+-green)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

---

## 📋 Problem Statement

Architecture teams work across multiple clients. Each architect maintains their own client-specific architecture documents (PPTs, PDFs, DOCX). This creates **knowledge silos** where:

- No one has visibility into other clients' architectures
- Finding information requires manually opening and searching files
- Onboarding new team members takes weeks
- Cross-client insights are nearly impossible

## 💡 Solution

A **RAG (Retrieval Augmented Generation)** system that:

1. **Ingests** architecture documents from a shared folder structure
2. **Indexes** content with rich metadata (client, doc type, section)
3. **Retrieves** relevant information using semantic + metadata filtering
4. **Generates** clear, cited answers using Azure OpenAI

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    USERS (6 Architects)              │
│                         │                            │
│                    ┌────▼────┐                       │
│                    │ Web UI  │ (Streamlit)            │
│                    └────┬────┘                       │
│                         │                            │
│                    ┌────▼────┐                       │
│                    │ FastAPI │ (Query API)            │
│                    └────┬────┘                       │
│                    ┌────▼────┐                       │
│                    │Retriever│                        │
│                    └──┬───┬──┘                       │
│              ┌───────┘   └────────┐                  │
│         ┌────▼────┐          ┌────▼────┐            │
│         │ChromaDB │          │Azure    │            │
│         │(Vectors)│          │OpenAI   │            │
│         └────┬────┘          │(GPT-4.1)│            │
│              │               └─────────┘            │
│         ┌────▼────┐                                  │
│         │Embeddings│ (text-embedding-3-small)        │
│         └────┬────┘                                  │
│         ┌────▼────┐                                  │
│         │Chunker + │                                 │
│         │Metadata  │                                 │
│         └────┬────┘                                  │
│         ┌────▼────┐                                  │
│         │Extractor│ (PPT/PDF/DOCX)                   │
│         └────┬────┘                                  │
│         ┌────▼────┐                                  │
│         │ Shared  │                                  │
│         │ Folder  │ (data/documents/)                │
│         └─────────┘                                  │
│                                                      │
│  ☁️ Azure VM (D2as_v5)                               │
└─────────────────────────────────────────────────────┘
```

---

## ✨ Features

### Phase 1 (Current) — Local Self-Hosted
- [x] Multi-format document ingestion (PPT, PDF, DOCX)
- [x] Automatic client detection from folder structure
- [x] Smart chunking with metadata tagging
- [x] Semantic search with ChromaDB
- [x] Client-filtered retrieval
- [x] LLM-powered answer generation with citations
- [x] FastAPI REST endpoints
- [x] Streamlit web UI
- [x] Evaluation harness
- [ ] Current vs Proposed comparison queries
- [ ] Cross-client queries

### Phase 2 (Future) — Azure-Native Managed
- [ ] Azure Blob Storage (document store)
- [ ] Azure AI Search (hybrid + semantic search)
- [ ] Azure Document Intelligence (OCR + tables)
- [ ] Azure App Service (managed hosting)
- [ ] Azure Key Vault (secrets)
- [ ] Azure Monitor (observability)
- [ ] RBAC access control

---

## 📁 Project Structure

```
C:\AI\arch-knowledge-assistant\
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Centralized configuration (pydantic-settings)
│
├── data/
│   ├── documents/               # ← Client architecture documents
│   │   ├── DataStories/
│   │   ├── TechNova/
│   │   ├── MediFlow/
│   │   └── RetailEdge/
│   └── chromadb/                # Vector store (auto-generated)
│
├── src/
│   ├── ingestion/
│   │   ├── scanner.py           # Folder scanning + file detection
│   │   ├── extractor.py         # PPT/PDF/DOCX → raw text
│   │   ├── preprocessor.py      # Text cleaning + normalization
│   │   └── chunker.py           # Smart chunking + metadata
│   │
│   ├── indexing/
│   │   └── indexer.py           # Embed + store in ChromaDB
│   │
│   ├── retrieval/
│   │   └── retriever.py         # Query → filter → retrieve → rank
│   │
│   ├── generation/
│   │   └── generator.py         # Context + question → LLM answer
│   │
│   ├── pipeline/
│   │   ├── ingest_pipeline.py   # End-to-end ingestion orchestration
│   │   └── query_pipeline.py    # End-to-end Q&A orchestration
│   │
│   └── api/
│       └── main.py              # FastAPI application
│
├── ui/
│   └── app.py                   # Streamlit web interface
│
├── eval/
│   ├── golden_qa.json           # Test Q&A pairs
│   └── evaluate.py              # Evaluation script
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_retrieval.py
│   └── test_generation.py
│
├── results/                     # Output logs and saved responses
│
├── requirements.txt
├── .env                         # Environment variables (not in git)
├── .gitignore
└── README.md
```

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.11+
- Azure OpenAI resource with:
  - `text-embedding-3-small` deployment
  - `gpt-4.1` deployment

### Step 1: Clone and setup
```bash
cd C:\AI\arch-knowledge-assistant
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Step 2: Configure environment
```bash
# Edit .env with your Azure OpenAI credentials
# Set AZURE_OPENAI_API_KEY to your actual key
```

### Step 3: Add documents
```bash
# Place client PPTs/PDFs in data/documents/<ClientName>/
# Folder name = Client name (auto-detected)
```

### Step 4: Run ingestion
```bash
python -m src.pipeline.ingest_pipeline
```

### Step 5: Start API server
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### Step 6: Start Web UI
```bash
streamlit run ui/app.py
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | Core development |
| Embeddings | Azure OpenAI text-embedding-3-small | Vector embeddings |
| LLM | Azure OpenAI GPT-4.1 | Answer generation |
| Vector DB | ChromaDB | Local vector storage |
| API | FastAPI + Uvicorn | REST API |
| UI | Streamlit | Web interface |
| Config | pydantic-settings + python-dotenv | Settings management |

---

## 📊 Supported Query Types

| Query Type | Example |
|-----------|---------|
| Explain architecture | "Explain TechNova architecture" |
| Current design | "What is MediFlow's current architecture?" |
| Proposed design | "What is the proposed design for RetailEdge?" |
| Hosting details | "How is DataStories hosted?" |
| Integration flows | "How does MediFlow integrate with hospital systems?" |
| Budget/costs | "What is TechNova's migration budget?" |
| Compare designs | "Compare current vs proposed for RetailEdge" |
| Security | "How does MediFlow handle HIPAA compliance?" |
| Cross-client | "Which clients use AWS?" |
| Specific component | "Explain the API gateway in RetailEdge" |

---

## 💰 Cost

| Phase | Monthly Cost |
|-------|-------------|
| Phase 1 (Local) | ~₹8,000 – ₹11,000 |
| Phase 2 (Azure-Native) | ~₹15,000 – ₹18,000 |

---

## 📈 Migration Path

| Component | Phase 1 | Phase 2 |
|-----------|---------|---------|
| Document Store | Local folder | Azure Blob Storage |
| Text Extraction | python-pptx / PyMuPDF | Azure Document Intelligence |
| Vector Store | ChromaDB | Azure AI Search |
| Search | Semantic only | Hybrid (vector + BM25 + semantic) |
| API Host | FastAPI on VM | Azure App Service |
| Security | None | Key Vault + RBAC |
| Monitoring | Console logs | Azure Monitor + App Insights |

---

## 👥 Team

Built as a learning + internal tool by the Architecture Team.

---

## 📄 License

Internal use only — not for distribution.
