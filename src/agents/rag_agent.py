"""
RAG Agent — Intelligent question answering with tool use
==========================================================

THIS IS THE CORE OF PHASE 3.

LAYMAN:
    Phase 1-2: Robot follows a recipe (fixed pipeline)
    Phase 3:   Smart assistant who PLANS what to do (agent)

    "Compare budgets across all clients and recommend the most cost-effective"
    
    Robot (Phase 1-2):
        → ONE search → random mix of chunks → incomplete answer
    
    Agent (Phase 3):
        → Thinks: "I need budget for each client"
        → Searches DataStories budget
        → Searches TechNova budget
        → Searches MediFlow budget
        → Searches RetailEdge budget
        → Thinks: "Now I have all data, let me compare"
        → Writes comprehensive comparison with recommendation

TECHNICAL:
    Uses OpenAI function calling (tool_use).
    The LLM decides WHEN and WHICH tools to call.
    We execute the tools and feed results back.
    Loop continues until LLM generates a final answer (no more tool calls).

MAX ITERATIONS:
    We limit to 10 tool calls to prevent infinite loops.
    Most queries need 1-4 tool calls.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.generation.model_router import ModelRouter
from openai import AzureOpenAI
from src.agents.tools import TOOL_DEFINITIONS, RAGToolExecutor

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10  # Safety limit — prevent infinite tool-calling loops

AGENT_SYSTEM_PROMPT = """You are an intelligent Architecture Knowledge Assistant with access to tools.

## Your Role
You help architects understand client architecture designs by searching and analyzing architecture documentation.

## Your Tools
You have access to:
1. **search_architecture_docs** — Search architecture documents with optional client and section type filters
2. **list_available_clients** — Get the list of all available clients
3. **get_index_stats** — Get statistics about indexed documents

## How to Work
1. **Analyze the question** — What information do you need?
2. **Plan your approach** — Which tools to call and in what order?
3. **Execute searches** — Call tools to gather information
4. **If you need more info** — Call more tools with refined queries
5. **Synthesize and answer** — Combine all gathered information into a clear answer

## Rules
- Use tools to find information — do NOT make up facts
- Search for EACH client separately when comparing across clients
- Include citations: [Source: filename, Slide X] for every factual claim
- If information is not found after searching, say so honestly
- Structure complex answers with headings and bullet points
- For comparisons, present each client's data, then summarize differences

## Important
- You can call multiple tools before answering
- Each tool call gives you more information
- Stop calling tools when you have enough to answer comprehensively
"""


@dataclass
class AgentResponse:
    """Complete agent response with metadata."""
    answer: str
    tool_calls_made: List[Dict[str, Any]]
    total_iterations: int
    tokens_used: Dict[str, int]
    processing_time: float
    model_used: str


class RAGAgent:
    """
    Agentic RAG — thinks, retrieves, reasons, and answers.
    
    THE AGENT LOOP:
        messages = [system_prompt, user_question]
        
        while True:
            response = LLM(messages + tools)
            
            if response has tool_calls:
                for each tool_call:
                    result = execute_tool(tool_call)
                    messages.append(tool_call)
                    messages.append(result)
                continue  # Loop — LLM will think again
            
            else:
                return response.content  # Final answer!
    """

    def __init__(self, retriever, indexer=None):
        from config.settings import get_settings
        settings = get_settings()

        self.openai_client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

        # Multi-model router — picks the right model per query
        self.router = ModelRouter(
            full_deployment=settings.azure_openai_chat_model_full,
            mini_deployment=settings.azure_openai_chat_model_mini,
            nano_deployment=settings.azure_openai_chat_model_nano,
        )

        # Default model for agent reasoning (Full — needs tool-use capability)
        self.agent_model = settings.azure_openai_chat_model_full

        # Tool executor
        self.tool_executor = RAGToolExecutor(
            retriever=retriever,
            indexer=indexer,
        )

        logger.info(
            f"RAGAgent initialized:\n"
            f"  Agent reasoning: {self.agent_model}\n"
            f"  Routing: Full={settings.azure_openai_chat_model_full}, "
            f"Mini={settings.azure_openai_chat_model_mini}, "
            f"Nano={settings.azure_openai_chat_model_nano}"
        )

    def ask(self, question: str) -> AgentResponse:
        start_time = time.time()
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total": 0}
        tool_calls_log = []

        # ── Step 1: Detect intent FIRST ──
        intent = self.tool_executor.retriever.detect_query_intent(question)
        model_selection = self.router.select(intent)

        logger.info(f"\n{'═' * 60}")
        logger.info(f"🤖 AGENT QUERY: {question}")
        logger.info(f"  Intent: {intent} | Model: {model_selection.model_name}")
        logger.info(f"{'═' * 60}")

        # ── Step 2: Simple queries → skip agent loop, use Mini ──
        if (intent in ("explanation", "specific_component", "general")
                and "compare" not in question.lower()
                and "all clients" not in question.lower()
                and "across" not in question.lower()):
            logger.info(f"  → Simple query → direct path with {model_selection.model_name}")
            return self._simple_answer(question, model_selection.deployment, model_selection)

        # ── Step 3: Complex queries → full agent loop ──
        logger.info(f"  → Complex query → agent loop with {self.agent_model}")

        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        # ── THE AGENT LOOP ──
        for iteration in range(MAX_ITERATIONS):
            logger.info(f"\n  --- Iteration {iteration + 1} ---")

            response = self.openai_client.chat.completions.create(
                model=self.agent_model,       # ← FIXED: was self.model
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.1,
                max_tokens=3000,
            )

            if response.usage:
                total_tokens["prompt_tokens"] += response.usage.prompt_tokens
                total_tokens["completion_tokens"] += response.usage.completion_tokens
                total_tokens["total"] += response.usage.total_tokens

            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                logger.info(f"  Agent wants to call {len(choice.message.tool_calls)} tool(s)")
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    result = self.tool_executor.execute(func_name, func_args)

                    tool_calls_log.append({
                        "iteration": iteration + 1,
                        "tool": func_name,
                        "arguments": func_args,
                        "result_preview": result[:200],
                    })

                    logger.info(f"  🔧 {func_name}({json.dumps(func_args)}) → {len(result)} chars")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

            else:
                answer = choice.message.content or "No answer generated."
                processing_time = time.time() - start_time

                logger.info(f"\n  ✅ Agent finished: {iteration + 1} iterations, "
                           f"{len(tool_calls_log)} tool calls, "
                           f"{total_tokens['total']} tokens, {processing_time:.2f}s, "
                           f"model={self.agent_model}")

                return AgentResponse(
                    answer=answer,
                    tool_calls_made=tool_calls_log,
                    total_iterations=iteration + 1,
                    tokens_used=total_tokens,
                    processing_time=processing_time,
                    model_used=self.agent_model,   # ← FIXED
                )

        return AgentResponse(
            answer="Reached maximum iterations.",
            tool_calls_made=tool_calls_log,
            total_iterations=MAX_ITERATIONS,
            tokens_used=total_tokens,
            processing_time=time.time() - start_time,
            model_used=self.agent_model,           # ← FIXED
        )
    def _simple_answer(self, question: str, model: str, selection) -> AgentResponse:
        """
        For simple queries, skip the agent loop entirely.
        Just retrieve + generate with the cheaper Mini model.
        
        LAYMAN:
            Complex question: "Compare budgets across all clients"
              → Needs agent loop (multiple searches, reasoning) → Full model
            
            Simple question: "How is DataStories hosted?"
              → One search is enough → Mini model (80% cheaper, 2x faster)
        
        WHY NOT always use the agent?
            The agent loop adds overhead:
            - Extra LLM call to "think" about what tools to use
            - Tool execution latency
            - More tokens consumed
            
            For "How is DataStories hosted?" the agent would:
            1. Think: "I need to search DataStories hosting" (1 LLM call)
            2. Search (1 tool call)
            3. Think: "I have enough info" (1 LLM call)
            4. Generate answer (implicit in step 3)
            = 2 LLM calls + 1 search
            
            Direct approach:
            1. Search (1 tool call)
            2. Generate answer (1 LLM call)
            = 1 LLM call + 1 search (50% fewer LLM calls)
        """
        start_time = time.time()
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total": 0}

        logger.info(f"  Using direct path with {selection.model_name}")

        # Detect client
        client = self.tool_executor.retriever.detect_client(question)

        # Single retrieval
        results = self.tool_executor.retriever.retrieve(
            query=question,
            client_filter=client,
        )

        # Build context
        context = self.tool_executor._search({
            "query": question,
            "client": client,
        })

        # Generate answer with the selected model (Mini for simple)
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ]

        response = self.openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=selection.temperature,
            max_tokens=selection.max_tokens,
        )

        answer = response.choices[0].message.content or "No answer generated."

        if response.usage:
            total_tokens["prompt_tokens"] = response.usage.prompt_tokens
            total_tokens["completion_tokens"] = response.usage.completion_tokens
            total_tokens["total"] = response.usage.total_tokens

        processing_time = time.time() - start_time

        logger.info(
            f"  ✅ Direct answer: {total_tokens['total']} tokens, "
            f"{processing_time:.2f}s, model={model}"
        )

        return AgentResponse(
            answer=answer,
            tool_calls_made=[{"iteration": 1, "tool": "search_architecture_docs",
                             "arguments": {"query": question, "client": client},
                             "result_preview": f"{len(results)} chunks retrieved"}],
            total_iterations=1,
            tokens_used=total_tokens,
            processing_time=processing_time,
            model_used=model,
        )

# ── Standalone Testing ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from config.settings import get_settings
    settings = get_settings()

    # Use Phase 2 retriever if available
    if settings.use_azure_search:
        from src.retrieval.azure_search_retriever import AzureSearchRetriever
        retriever = AzureSearchRetriever()
    else:
        from src.retrieval.retriever import KnowledgeRetriever
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

    agent = RAGAgent(retriever=retriever)

    # ── Test queries ──
    test_queries = [
        # Simple (should use 1 tool call)
        "How is DataStories hosted?",

        # Multi-hop (should use multiple tool calls)
        "Compare the migration budget across all 4 clients and tell me which is most cost-effective",

        # Cross-client reasoning
        "Which clients are migrating to AWS and what are their timelines?",
    ]

    for query in test_queries:
        print(f"\n{'━' * 70}")
        print(f"❓ {query}")
        print(f"{'━' * 70}")

        response = agent.ask(query)

        # Show answer (truncated)
        preview = response.answer[:600]
        if len(response.answer) > 600:
            preview += "\n... (truncated)"
        print(f"\n📝 {preview}")

        # Show metadata
        print(f"\n  🔧 Tool calls: {len(response.tool_calls_made)}")
        for tc in response.tool_calls_made:
            print(f"     Iter {tc['iteration']}: {tc['tool']}({json.dumps(tc['arguments'])})")
        print(f"  🔄 Iterations: {response.total_iterations}")
        print(f"  💰 Tokens: {response.tokens_used['total']}")
        print(f"  ⏱️  Time: {response.processing_time:.2f}s")

    print(f"\n{'═' * 70}")
    print("✅ Agent test complete!")