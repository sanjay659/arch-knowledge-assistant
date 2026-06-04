"""
Architecture Knowledge Assistant — Settings Configuration

Uses pydantic-settings to load configuration from .env file.
All settings are centralized here — no hardcoded values anywhere else.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Azure OpenAI
    # ------------------------------------------------------------------
    azure_openai_endpoint: str = "https://sanjay-workflow-resource.openai.azure.com/"
    azure_openai_api_key: str = "5AIDgubHY6qnsKRSZv09IZGx9aI1SJSUpggD0Tm0CwdIqmQBcEtZJQQJ99CBACYeBjFXJ3w3AAAAACOGtAEb"
    azure_openai_api_version: str = "2024-12-01-preview"

    # Model deployments
    azure_openai_embedding_model: str = "text-embedding-3-small"
    azure_openai_chat_model: str = "gpt-4.1"

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    documents_path: str = "data/documents"
    chromadb_path: str = "data/chromadb"

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    chunk_size: int = 1000           # Max characters per chunk
    chunk_overlap: int = 150         # Overlap between consecutive chunks
    min_chunk_length: int = 100      # Minimum chunk length (merge if shorter)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    retrieval_top_k: int = 8         # Number of chunks to retrieve
    retrieval_min_relevance: float = 0.35  # Minimum similarity score

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    generation_max_tokens: int = 2000
    generation_temperature: float = 0.3

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    app_name: str = "Architecture Knowledge Assistant"
    app_version: str = "1.0.0"
    app_port: int = 8000

    # ── Phase 2: Azure AI Search ──────────────────────────
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "arch-knowledge-index"

    # ── Phase 2: Azure Document Intelligence ──────────────
    azure_docintel_endpoint: str = ""
    azure_docintel_api_key: str = ""

    # ── Phase 3: Multi-Model Routing ──────────────────────
    azure_openai_chat_model_full: str = "gpt-4.1"
    azure_openai_chat_model_mini: str = "gpt-4.1-mini"
    azure_openai_chat_model_nano: str = "gpt-4.1-nano"

    # ── Phase 2: Feature Flags ────────────────────────────
    # These let you switch between Phase 1 and Phase 2 components
    # without changing any code — just change .env
    #
    # Layman: Like a light switch — flip to "true" to use
    #         Azure services, keep "false" to use local services.
    #
    # WHY feature flags?
    #   You can test Phase 2 components one at a time:
    #   1. First switch search: USE_AZURE_SEARCH=true (keep extraction same)
    #   2. Then switch extraction: USE_DOC_INTELLIGENCE=true
    #   3. If anything breaks, flip back to false instantly
    use_azure_search: bool = False
    use_doc_intelligence: bool = False

    # ------------------------------------------------------------------
    # Derived paths (computed properties)
    # ------------------------------------------------------------------
    @property
    def documents_dir(self) -> Path:
        """Absolute path to documents directory."""
        return Path(self.documents_path).resolve()

    @property
    def chromadb_dir(self) -> Path:
        """Absolute path to ChromaDB directory."""
        return Path(self.chromadb_path).resolve()

    def get_client_dirs(self) -> list[Path]:
        """Return list of client directories (each subfolder = one client)."""
        docs_dir = self.documents_dir
        if not docs_dir.exists():
            return []
        return sorted([
            d for d in docs_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

    def get_client_names(self) -> list[str]:
        """Return list of client names detected from folder structure."""
        return [d.name for d in self.get_client_dirs()]


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance.
    Call this function anywhere in the project to get settings.

    Usage:
        from config.settings import get_settings
        settings = get_settings()
        print(settings.azure_openai_endpoint)
    """
    return Settings()
