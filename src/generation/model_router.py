"""
Model Router — Selects the right LLM model based on query intent
=================================================================

LAYMAN:
    Not every question needs the most powerful (expensive) model.
    
    "What client is DataStories?"     → Nano  ($0.0002/call) — simple lookup
    "Explain MediFlow architecture"   → Mini  ($0.0029/call) — standard Q&A
    "Compare all clients' budgets     → Full  ($0.0144/call) — complex reasoning
     and recommend cost-effective"

    Average cost drops from $0.014 → $0.004 per query (70% savings)
    AND quality improves because each model is optimized for its task.

TECHNICAL:
    Uses OpenAI's multi-deployment feature in Azure.
    Each model is a separate deployment in your Azure OpenAI resource.
    The router picks which deployment to call based on intent.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelSelection:
    """Which model to use and why."""
    deployment: str          # Azure OpenAI deployment name
    model_name: str          # Human-readable name
    reason: str              # Why this model was selected
    max_tokens: int          # Output token limit for this task
    temperature: float       # Creativity level


class ModelRouter:
    """
    Routes queries to the optimal model based on intent and complexity.
    
    ROUTING TABLE:
        comparison        → GPT-4.1 Full  (needs deep reasoning)
        explanation       → GPT-4.1 Mini  (good enough, 80% cheaper)
        specific_component → GPT-4.1 Mini  (focused lookup)
        listing           → GPT-4.1 Mini  (straightforward)
        general           → GPT-4.1 Mini  (default)
        classification    → GPT-4.1 Nano  (simple label, 95% cheaper)
    """

    def __init__(
        self,
        full_deployment: str = "gpt-4.1",
        mini_deployment: str = "gpt-4.1-mini",
        nano_deployment: str = "gpt-4.1-nano",
    ):
        """
        Args:
            full_deployment: Azure deployment name for GPT-4.1 Full
            mini_deployment: Azure deployment name for GPT-4.1 Mini
            nano_deployment: Azure deployment name for GPT-4.1 Nano
            
        NOTE: You need all 3 deployed in your Azure OpenAI resource.
              If Mini/Nano aren't deployed, set them to "gpt-4.1" (falls back to Full).
        """
        self.full = full_deployment
        self.mini = mini_deployment
        self.nano = nano_deployment

        logger.info(
            f"ModelRouter initialized: Full={full_deployment}, "
            f"Mini={mini_deployment}, Nano={nano_deployment}"
        )

    def select(self, intent: str, chunk_count: int = 0) -> ModelSelection:
        """
        Select the optimal model based on query intent.
        
        LAYMAN:
            Simple question → cheap model (why pay more?)
            Complex question → powerful model (need the best)
            
        Args:
            intent: Detected query intent from retriever
            chunk_count: Number of retrieved chunks (more chunks = more complex)
            
        Returns:
            ModelSelection with deployment name and parameters
        """
        if intent == "comparison":
            # Comparisons need deep reasoning across multiple documents
            # Full model is significantly better at structured analysis
            selection = ModelSelection(
                deployment=self.full,
                model_name="GPT-4.1 Full",
                reason="Comparison requires deep reasoning across multiple documents",
                max_tokens=2500,
                temperature=0.1,
            )

        elif intent == "explanation" and chunk_count > 6:
            # Large context explanations benefit from Full model
            selection = ModelSelection(
                deployment=self.full,
                model_name="GPT-4.1 Full",
                reason="Large context explanation (>6 chunks) benefits from stronger model",
                max_tokens=2000,
                temperature=0.1,
            )

        elif intent in ("explanation", "specific_component", "listing", "general"):
            # Standard queries — Mini handles these well
            selection = ModelSelection(
                deployment=self.mini,
                model_name="GPT-4.1 Mini",
                reason=f"Standard {intent} query — Mini provides good quality at lower cost",
                max_tokens=2000,
                temperature=0.1,
            )

        else:
            # Default fallback
            selection = ModelSelection(
                deployment=self.mini,
                model_name="GPT-4.1 Mini",
                reason="Default model selection",
                max_tokens=2000,
                temperature=0.1,
            )

        logger.info(
            f"  Model selected: {selection.model_name} "
            f"(reason: {selection.reason})"
        )
        return selection

    def select_for_classification(self) -> ModelSelection:
        """
        Select model for classification tasks (section type, intent).
        Always uses Nano — classification is simple and high-volume.
        
        LAYMAN:
            Classifying "Is this about budget or security?" is simple.
            Don't need a senior architect for that — intern can do it.
        """
        return ModelSelection(
            deployment=self.nano,
            model_name="GPT-4.1 Nano",
            reason="Classification task — simple, high-volume, Nano is sufficient",
            max_tokens=20,
            temperature=0.0,  # Deterministic for classification
        )