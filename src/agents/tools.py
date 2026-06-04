"""
RAG Tools — Functions the agent can call during reasoning
==========================================================

LAYMAN:
    Tools are like apps on your phone — each does one specific thing.
    The agent DECIDES which app to open based on what it needs.
    
    Tool 1: "Search architecture docs" (general search)
    Tool 2: "Search specific client" (filtered search)
    Tool 3: "Search specific section type" (budget, security, etc.)
    Tool 4: "List all clients" (metadata query)

TECHNICAL:
    These are OpenAI function-calling compatible tool definitions.
    The LLM sees these definitions and decides when to call them.
    We execute the actual function and return results to the LLM.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


# ── Tool Definitions (what the LLM sees) ──────────────────────
# These JSON schemas tell the LLM WHAT tools are available
# and WHAT parameters each tool accepts.

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_architecture_docs",
            "description": (
                "Search architecture documents for information about client systems. "
                "Use this to find details about hosting, infrastructure, migration plans, "
                "budgets, security, timelines, and architecture designs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — what information are you looking for?"
                    },
                    "client": {
                        "type": "string",
                        "description": "Optional: filter to a specific client (e.g., 'DataStories', 'TechNova', 'MediFlow', 'RetailEdge'). Leave empty to search all clients."
                    },
                    "section_type": {
                        "type": "string",
                        "enum": [
                            "current_architecture", "proposed_architecture",
                            "hosting", "security", "budget", "migration",
                            "risk_dependency", "assumptions", "inventory",
                            "timeline", "success_criteria", "operations",
                            "contacts", "integration"
                        ],
                        "description": "Optional: filter to a specific section type."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_clients",
            "description": "Get the list of all clients that have architecture documents indexed in the system.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_index_stats",
            "description": "Get statistics about the indexed documents — total chunks, clients, section types available.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


class RAGToolExecutor:
    """
    Executes tool calls made by the agent.
    
    LAYMAN:
        The LLM says: "I want to call search_architecture_docs with query='budget'"
        This class actually RUNS that search and returns the results.
        The LLM then reads the results and decides what to do next.
    """

    def __init__(self, retriever, indexer=None):
        """
        Args:
            retriever: Phase 1 or Phase 2 retriever (same interface)
            indexer: For stats queries (optional)
        """
        self.retriever = retriever
        self.indexer = indexer

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a tool call and return results as a string.
        
        The LLM sends: {"name": "search_architecture_docs", "arguments": {"query": "budget", "client": "TechNova"}}
        We execute the search and return the results as text.
        """
        logger.info(f"  🔧 Tool call: {tool_name}({json.dumps(arguments)})")

        if tool_name == "search_architecture_docs":
            return self._search(arguments)
        elif tool_name == "list_available_clients":
            return self._list_clients()
        elif tool_name == "get_index_stats":
            return self._get_stats()
        else:
            return f"Unknown tool: {tool_name}"

    def _search(self, args: Dict) -> str:
        """Execute a search and format results for the LLM."""
        query = args.get("query", "")
        client = args.get("client") or None
        section_type = args.get("section_type") or None

        results = self.retriever.retrieve(
            query=query,
            client_filter=client,
            section_type_filter=section_type,
            top_k=5,  # Fewer results per tool call (agent makes multiple calls)
        )

        if not results:
            return f"No results found for query: '{query}' (client={client}, section_type={section_type})"

        # Format results as readable text for the LLM
        output_parts = [f"Found {len(results)} results:\n"]
        for i, r in enumerate(results, 1):
            m = r.metadata
            output_parts.append(
                f"[{i}] Source: {m.get('source_file', '?')}, Slide {m.get('slide_number', '?')}\n"
                f"    Client: {m.get('client', '?')} | Type: {m.get('section_type', '?')}\n"
                f"    Content: {r.content[:500]}\n"
            )

        return "\n".join(output_parts)

    def _list_clients(self) -> str:
        """Return list of available clients."""
        if hasattr(self.retriever, '_known_clients'):
            clients = self.retriever._known_clients
        else:
            clients = ["DataStories", "TechNova", "MediFlow", "RetailEdge"]
        return f"Available clients: {', '.join(clients)}"

    def _get_stats(self) -> str:
        """Return index statistics."""
        if self.indexer:
            stats = self.indexer.get_stats()
            return (
                f"Index statistics:\n"
                f"  Total chunks: {stats.get('total_chunks', 0)}\n"
                f"  Clients: {stats.get('clients', [])}\n"
                f"  Section types: {stats.get('section_types', [])}\n"
                f"  Files: {stats.get('unique_files', 0)}"
            )
        return "Stats not available"