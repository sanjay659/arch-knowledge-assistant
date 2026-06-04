"""
Answer Generator — Creates answers from retrieved context using LLM
====================================================================

WHAT THIS MODULE DOES:
    Takes retrieved chunks + user question → LLM → Answer with citations.

    This is the G in RAG — the GENERATION step.

RAG CONCEPT — Grounded Generation:
    The key difference between RAG and raw LLM:

    Raw LLM:
        "Tell me about DataStories architecture"
        → Uses training data → May hallucinate → No sources

    RAG LLM:
        "Here are the actual documents. Answer based on THESE."
        → Uses YOUR documents → Grounded in facts → Citable sources

    The system prompt ENFORCES grounding:
    - "Answer ONLY from the provided context"
    - "If context doesn't contain the answer, say so"
    - "Include citations to source documents"

RAG CONCEPT — Prompt Engineering:
    The prompt is the most important part of generation.
    A bad prompt with good retrieval = bad answers.
    A good prompt with good retrieval = great answers.

    Our prompt structure:
    ┌─────────────────────────────────────────┐
    │ SYSTEM: Role + Rules + Format           │
    │ CONTEXT: Numbered chunks with metadata  │
    │ QUESTION: User's query                  │
    └─────────────────────────────────────────┘

PHASE 2 MIGRATION NOTE:
    Generator mostly stays the same. Improvements:
    - Streaming responses (token by token to UI)
    - Response caching for repeated questions
    - Multi-model routing (Mini for simple, Full for complex)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from openai import AzureOpenAI

from src.retrieval.retriever import RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAnswer:
    """
    Complete answer with metadata.

    WHY track all these fields?
        answer:          What the user sees
        sources:         For citation display in UI
        model:           Track which model generated this
        tokens_used:     Cost monitoring (input + output tokens)
        processing_time: Latency monitoring
    """
    answer: str
    sources: List[Dict[str, str]]
    model: str
    tokens_used: Dict[str, int]
    processing_time: float


# ── System Prompt ──────────────────────────────────────────────
# Every word in this prompt is INTENTIONAL.
# This is the most important text in the entire system.

SYSTEM_PROMPT = """You are the Architecture Knowledge Assistant for an enterprise architecture team.

## Your Role
You help architects understand client architecture designs by answering questions based ONLY on the provided architecture documentation.

## Rules — FOLLOW STRICTLY

1. **Answer ONLY from the provided context.**
   - Do NOT use any knowledge from your training data.
   - Do NOT assume or infer details not in the context.
   - If information is in the context, use it. If not, say so.

2. **Include citations for every factual claim.**
   - Format: [Source: <filename>, Slide <number>]
   - Place citations at the end of the relevant sentence.
   - Example: "DataStories uses AWS for hosting [Source: blueprint.pptx, Slide 9]."

3. **If the context does NOT contain enough information:**
   - Say: "I don't have enough information in the available documents to fully answer this."
   - Mention what IS available and what's missing.
   - Do NOT guess or fabricate.

4. **Structure your answers clearly:**
   - Use bullet points and headings for complex answers.
   - Start with a brief summary, then provide details.
   - For architecture: describe components, flows, integrations.

5. **For comparison questions:**
   - Present Current and Proposed as separate sections.
   - Highlight key differences.

6. **Be precise.**
   - Use exact numbers, names, and technical terms from the context.
   - Don't paraphrase in ways that change the meaning.
"""

COMPARISON_PROMPT = """
## Special Instruction: Comparison Query
The user wants to COMPARE current vs proposed architecture.
Context is provided in two sections: CURRENT and PROPOSED.

Structure your response as:
### Current Architecture
(describe current state with citations)

### Proposed Architecture
(describe proposed state with citations)

### Key Differences
(highlight what changes and why)
"""


class AnswerGenerator:
    """
    Generates grounded answers from retrieved context using Azure OpenAI.
    """

    def __init__(
        self,
        azure_endpoint: str,
        azure_api_key: str,
        azure_api_version: str,
        chat_deployment: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
    ):
        """
        Args:
            azure_endpoint: Azure OpenAI endpoint
            azure_api_key: API key
            azure_api_version: API version
            chat_deployment: Chat model deployment name (e.g., "gpt-4.1")
            max_tokens: Max tokens in generated answer
            temperature: 0.0 = deterministic, 1.0 = creative
                        We use 0.1 for factual, grounded answers
        """
        self.openai_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
        )
        self.chat_deployment = chat_deployment
        self.max_tokens = max_tokens
        self.temperature = temperature

        logger.info(f"AnswerGenerator initialized with model: {chat_deployment}")

    def generate(
        self,
        query: str,
        retrieval_results: List[RetrievalResult],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> GeneratedAnswer:
        """
        Generate an answer from retrieved context.

        Args:
            query: User's question
            retrieval_results: Chunks from the retriever
            conversation_history: Previous Q&A pairs (for follow-ups)

        Returns:
            GeneratedAnswer with answer, sources, tokens, timing
        """
        start_time = time.time()

        # Handle empty results
        if not retrieval_results:
            return GeneratedAnswer(
                answer=(
                    "I don't have enough information in the available "
                    "documents to answer this question.\n\n"
                    "Please ensure the relevant architecture documents "
                    "have been ingested into the system."
                ),
                sources=[],
                model=self.chat_deployment,
                tokens_used={"prompt_tokens": 0, "completion_tokens": 0, "total": 0},
                processing_time=time.time() - start_time,
            )

        # Build context from chunks
        context = self._build_context(retrieval_results)
        sources = self._extract_sources(retrieval_results)

        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Add conversation history (last 5 turns for follow-ups)
        if conversation_history:
            messages.extend(conversation_history[-10:])  # 5 pairs = 10 messages

        # Add context + question
        user_content = (
            f"## Retrieved Architecture Context\n\n"
            f"{context}\n\n"
            f"## Question\n{query}"
        )
        messages.append({"role": "user", "content": user_content})

        # Call LLM
        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_deployment,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            answer_text = response.choices[0].message.content
            usage = response.usage
            tokens = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total": usage.total_tokens,
            }

            processing_time = time.time() - start_time

            logger.info(
                f"  Answer generated: {tokens['total']} tokens, "
                f"{processing_time:.2f}s"
            )

            return GeneratedAnswer(
                answer=answer_text,
                sources=sources,
                model=self.chat_deployment,
                tokens_used=tokens,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"  LLM error: {e}")
            return GeneratedAnswer(
                answer=f"Error generating answer: {str(e)}",
                sources=sources,
                model=self.chat_deployment,
                tokens_used={"prompt_tokens": 0, "completion_tokens": 0, "total": 0},
                processing_time=time.time() - start_time,
            )

    def generate_comparison(
        self,
        query: str,
        current_chunks: List[RetrievalResult],
        proposed_chunks: List[RetrievalResult],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> GeneratedAnswer:
        """
        Generate a comparison answer with current vs proposed context.

        Uses separate context sections so the LLM can structure
        the comparison clearly.
        """
        start_time = time.time()

        # Build separate context sections
        current_context = self._build_context(current_chunks, label="CURRENT ARCHITECTURE")
        proposed_context = self._build_context(proposed_chunks, label="PROPOSED ARCHITECTURE")
        combined_context = f"{current_context}\n\n{proposed_context}"

        # Combine sources
        all_chunks = current_chunks + proposed_chunks
        sources = self._extract_sources(all_chunks)

        # Handle empty
        if not current_chunks and not proposed_chunks:
            return GeneratedAnswer(
                answer=(
                    "I don't have enough information to compare the "
                    "current and proposed architectures.\n\n"
                    "Please ensure both current and proposed architecture "
                    "documents have been ingested."
                ),
                sources=[],
                model=self.chat_deployment,
                tokens_used={"prompt_tokens": 0, "completion_tokens": 0, "total": 0},
                processing_time=time.time() - start_time,
            )

        # Build messages with comparison prompt
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + COMPARISON_PROMPT},
        ]

        if conversation_history:
            messages.extend(conversation_history[-10:])

        user_content = (
            f"## Retrieved Architecture Context\n\n"
            f"{combined_context}\n\n"
            f"## Question\n{query}"
        )
        messages.append({"role": "user", "content": user_content})

        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_deployment,
                messages=messages,
                temperature=self.temperature,
                max_tokens=2500,  # Comparisons need more space
            )

            answer_text = response.choices[0].message.content
            usage = response.usage
            tokens = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total": usage.total_tokens,
            }

            processing_time = time.time() - start_time

            logger.info(
                f"  Comparison answer: {tokens['total']} tokens, "
                f"{processing_time:.2f}s"
            )

            return GeneratedAnswer(
                answer=answer_text,
                sources=sources,
                model=self.chat_deployment,
                tokens_used=tokens,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"  LLM comparison error: {e}")
            return GeneratedAnswer(
                answer=f"Error generating comparison: {str(e)}",
                sources=sources,
                model=self.chat_deployment,
                tokens_used={"prompt_tokens": 0, "completion_tokens": 0, "total": 0},
                processing_time=time.time() - start_time,
            )

    def _build_context(
        self,
        results: List[RetrievalResult],
        label: str = "RETRIEVED CONTEXT",
    ) -> str:
        """
        Format retrieved chunks into numbered context for the LLM.

        WHY numbered?
            Helps the LLM reference specific chunks.
            Helps YOU debug which chunks influenced the answer.

        WHY include metadata?
            The LLM needs source info to generate citations:
            [Source: blueprint.pptx, Slide 5]
        """
        if not results:
            return f"## {label}\nNo relevant documents found."

        context_parts = [f"## {label}\n"]

        for i, result in enumerate(results, 1):
            meta = result.metadata
            source_file = meta.get("source_file", "unknown")
            slide_num = meta.get("slide_number", "?")
            section_type = meta.get("section_type", "general")
            client = meta.get("client", "unknown")

            context_parts.append(
                f"[{i}] Source: {source_file}, Slide {slide_num}\n"
                f"    Client: {client} | Section: {section_type}\n"
                f"    Content:\n{result.content}\n"
            )

        return "\n".join(context_parts)

    def _extract_sources(
        self, results: List[RetrievalResult]
    ) -> List[Dict[str, str]]:
        """
        Extract unique source references (deduplicated).
        """
        seen = set()
        sources = []

        for result in results:
            meta = result.metadata
            key = f"{meta.get('source_file', '')}_{meta.get('slide_number', '')}"

            if key not in seen:
                seen.add(key)
                sources.append({
                    "file": meta.get("source_file", "unknown"),
                    "slide": meta.get("slide_number", "?"),
                    "client": meta.get("client", "unknown"),
                    "section_type": meta.get("section_type", "general"),
                })

        return sources


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    from config.settings import get_settings
    settings = get_settings()

    from src.retrieval.retriever import KnowledgeRetriever

    print("=" * 60)
    print("Answer Generator — End-to-End Test")
    print("=" * 60)

    # Initialize retriever
    retriever = KnowledgeRetriever(
        chromadb_path=str(settings.chromadb_dir),
        collection_name="arch_knowledge",
        top_k=settings.retrieval_top_k,
        min_relevance=settings.retrieval_min_relevance,
        azure_endpoint=settings.azure_openai_endpoint,
        azure_api_key=settings.azure_openai_api_key,
        azure_api_version=settings.azure_openai_api_version,
        embedding_deployment=settings.azure_openai_embedding_model,
    )

    # Initialize generator
    generator = AnswerGenerator(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_api_key=settings.azure_openai_api_key,
        azure_api_version=settings.azure_openai_api_version,
        chat_deployment=settings.azure_openai_chat_model,
    )

    # ── Test 1: Simple explanation ──
    print(f"\n{'━' * 60}")
    query1 = "How is DataStories currently hosted?"
    print(f"❓ {query1}")
    print(f"{'━' * 60}")

    intent1 = retriever.detect_query_intent(query1)
    results1 = retriever.retrieve(query1)
    answer1 = generator.generate(query1, results1)

    print(f"\n📝 Answer:\n{answer1.answer}")
    print(f"\n📎 Sources: {len(answer1.sources)}")
    for s in answer1.sources:
        print(f"   {s['file']} | Slide {s['slide']} | {s['client']}")
    print(f"\n💰 Tokens: {answer1.tokens_used}")
    print(f"⏱️  Time: {answer1.processing_time:.2f}s")

    # ── Test 2: Comparison ──
    print(f"\n{'━' * 60}")
    query2 = "Compare current vs proposed architecture for DataStories"
    print(f"❓ {query2}")
    print(f"{'━' * 60}")

    comparison = retriever.retrieve_for_comparison(query2)
    answer2 = generator.generate_comparison(
        query2,
        comparison["current"],
        comparison["proposed"],
    )

    print(f"\n📝 Answer:\n{answer2.answer}")
    print(f"\n📎 Sources: {len(answer2.sources)}")
    print(f"💰 Tokens: {answer2.tokens_used}")
    print(f"⏱️  Time: {answer2.processing_time:.2f}s")

    # ── Test 3: Cross-client ──
    print(f"\n{'━' * 60}")
    query3 = "Which clients use AWS?"
    print(f"❓ {query3}")
    print(f"{'━' * 60}")

    results3 = retriever.retrieve(query3)
    answer3 = generator.generate(query3, results3)

    print(f"\n📝 Answer:\n{answer3.answer}")
    print(f"\n💰 Tokens: {answer3.tokens_used}")
    print(f"⏱️  Time: {answer3.processing_time:.2f}s")

    print(f"\n{'=' * 60}")
    print("✅ Generator test complete!")
    print(f"{'=' * 60}")