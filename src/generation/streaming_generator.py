"""
Streaming Generator — Token-by-token answer delivery
=====================================================

LAYMAN:
    Before: Wait 10 seconds, get entire answer at once (like waiting for a letter)
    After:  Words appear one by one as they're generated (like watching someone type)
    
    Same answer. Same quality. But MUCH better user experience.
    User sees first words within 1 second instead of waiting 10.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from typing import List, Dict, Any, Optional, Generator

from openai import AzureOpenAI
from src.retrieval.retriever import RetrievalResult
from src.generation.generator import SYSTEM_PROMPT, COMPARISON_PROMPT

logger = logging.getLogger(__name__)


class StreamingGenerator:
    """
    Same as AnswerGenerator but yields tokens one at a time.
    
    Usage:
        for token in generator.stream(query, chunks):
            print(token, end="", flush=True)  # Appears word by word
    """

    def __init__(
        self,
        azure_endpoint: str,
        azure_api_key: str,
        azure_api_version: str,
        chat_deployment: str,
    ):
        self.openai_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
        )
        self.chat_deployment = chat_deployment

    def stream(
        self,
        query: str,
        retrieval_results: List[RetrievalResult],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream answer tokens one at a time.
        
        THE KEY DIFFERENCE:
            Normal:    response = client.create(...)  → wait → full text
            Streaming: response = client.create(stream=True) → yields tokens
        
        LAYMAN:
            Normal:    Chef cooks entire meal, brings it all at once
            Streaming: Chef sends each dish as it's ready
        """
        if not retrieval_results:
            yield "I don't have enough information in the available documents to answer this question."
            return

        # Build context (same as non-streaming)
        context = self._build_context(retrieval_results)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        if conversation_history:
            messages.extend(conversation_history[-10:])

        messages.append({
            "role": "user",
            "content": f"## Retrieved Architecture Context\n\n{context}\n\n## Question\n{query}",
        })

        try:
            # THE MAGIC: stream=True
            # Instead of waiting for the full response,
            # Azure OpenAI sends tokens as they're generated
            response = self.openai_client.chat.completions.create(
                model=self.chat_deployment,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
                stream=True,  # ← This changes everything
            )

            # Yield each token as it arrives
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"\n\nError: {str(e)}"

    def stream_comparison(
        self,
        query: str,
        current_chunks: List[RetrievalResult],
        proposed_chunks: List[RetrievalResult],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, None]:
        """Stream comparison answer."""
        if not current_chunks and not proposed_chunks:
            yield "I don't have enough information to compare architectures."
            return

        current_ctx = self._build_context(current_chunks, "CURRENT ARCHITECTURE")
        proposed_ctx = self._build_context(proposed_chunks, "PROPOSED ARCHITECTURE")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + COMPARISON_PROMPT},
        ]
        if conversation_history:
            messages.extend(conversation_history[-10:])

        messages.append({
            "role": "user",
            "content": f"## Retrieved Context\n\n{current_ctx}\n\n{proposed_ctx}\n\n## Question\n{query}",
        })

        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_deployment,
                messages=messages,
                temperature=0.1,
                max_tokens=2500,
                stream=True,
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"\n\nError: {str(e)}"

    def _build_context(self, results, label="RETRIEVED CONTEXT"):
        if not results:
            return f"## {label}\nNo relevant documents found."
        parts = [f"## {label}\n"]
        for i, r in enumerate(results, 1):
            m = r.metadata
            parts.append(
                f"[{i}] Source: {m.get('source_file', '?')}, Slide {m.get('slide_number', '?')}\n"
                f"    Client: {m.get('client', '?')} | Section: {m.get('section_type', '?')}\n"
                f"    Content:\n{r.content}\n"
            )
        return "\n".join(parts)