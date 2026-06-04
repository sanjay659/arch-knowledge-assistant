"""
Streamlit UI — Chat interface for Architecture Knowledge Assistant
===================================================================

RUNNING:
    1. Start the API first:  uvicorn src.api.main:app --port 8000
    2. Then start the UI:    streamlit run ui/app.py
    3. Open: http://localhost:8501
"""

import streamlit as st
import requests

# ── Page Config ──
st.set_page_config(
    page_title="Architecture Knowledge Assistant",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = "http://localhost:8000"


# ── Session State ──
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_client" not in st.session_state:
    st.session_state.selected_client = None


# ── Helper ──
def api_request(method, endpoint, **kwargs):
    """Call the FastAPI backend."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "GET":
            resp = requests.get(url, timeout=120)
        elif method == "POST":
            resp = requests.post(url, **kwargs, timeout=120)
        else:
            return {"error": f"Unsupported method: {method}"}

        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"API error ({resp.status_code}): {resp.text}"}

    except requests.exceptions.ConnectionError:
        return {
            "error": (
                "Cannot connect to API. Start it first:\n"
                "uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"
            )
        }
    except Exception as e:
        return {"error": str(e)}


# ── Sidebar ──
with st.sidebar:
    st.title("🏗️ Arch Knowledge")
    st.caption("Architecture Knowledge Assistant")
    st.markdown("---")

    # Client filter
    st.subheader("🔍 Filter by Client")
    clients_result = api_request("GET", "/clients")
    if isinstance(clients_result, list):
        clients = clients_result
    else:
        clients = []

    client_options = ["All Clients"] + clients
    selected = st.selectbox("Select client:", options=client_options, index=0)
    st.session_state.selected_client = None if selected == "All Clients" else selected

    st.markdown("---")

    # Ingestion
    st.subheader("📥 Document Ingestion")
    if st.button("🔄 Ingest Documents", use_container_width=True):
        with st.spinner("Ingesting... This may take a minute."):
            result = api_request("POST", "/ingest")
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(
                    f"✅ Done!\n\n"
                    f"Files: {result.get('files_processed', 0)}\n"
                    f"Chunks: {result.get('chunks_created', 0)}\n"
                    f"Time: {result.get('processing_time', 0):.1f}s"
                )

    st.markdown("---")

    # Stats
    st.subheader("📊 Index Stats")
    stats = api_request("GET", "/stats")
    if "error" not in stats:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Chunks", stats.get("total_chunks", 0))
        with col2:
            st.metric("Clients", stats.get("unique_clients", 0))
        if stats.get("clients"):
            st.caption(f"Clients: {', '.join(stats['clients'])}")
    else:
        st.caption("⚠️ API not connected")

    st.markdown("---")

    # Clear chat
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Phase 1 — Local Self-Hosted\nChromaDB + Azure OpenAI")


# ── Main Chat Area ──
st.title("🏗️ Architecture Knowledge Assistant")
st.caption("Ask questions about client architecture designs. Powered by RAG.")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Show sources for assistant messages
        if message["role"] == "assistant" and "sources" in message:
            sources = message["sources"]
            if sources:
                with st.expander(f"📎 Sources ({len(sources)} references)"):
                    for s in sources:
                        st.caption(
                            f"📄 {s.get('file', '?')} | "
                            f"Slide {s.get('slide', '?')} | "
                            f"Client: {s.get('client', '?')} | "
                            f"Type: {s.get('section_type', '?')}"
                        )

        # Show metadata
        if message["role"] == "assistant" and "metadata" in message:
            meta = message["metadata"]
            with st.expander("ℹ️ Details"):
                c1, c2, c3, c4 = st.columns(4)
                c1.caption(f"Intent: {meta.get('intent', '?')}")
                c2.caption(f"Chunks: {meta.get('chunks', '?')}")
                c3.caption(f"Tokens: {meta.get('tokens', '?')}")
                c4.caption(f"Time: {meta.get('time', '?')}s")

# Chat input
if prompt := st.chat_input("Ask about architecture..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get response — try streaming first, fall back to normal
    with st.chat_message("assistant"):
        request_body = {"question": prompt}
        if st.session_state.selected_client:
            request_body["client"] = st.session_state.selected_client

        try:
            # Try streaming endpoint
            import requests as req
            response = req.post(
                f"{API_BASE_URL}/query/stream",
                json=request_body,
                stream=True,
                timeout=120,
            )

            if response.status_code == 200:
                # Stream tokens into the UI
                answer_placeholder = st.empty()
                full_answer = ""
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        full_answer += chunk
                        answer_placeholder.markdown(full_answer + "▌")
                answer_placeholder.markdown(full_answer)

                # Get sources from non-streaming endpoint (quick call)
                result = api_request("POST", "/query", json=request_body)
                sources = result.get("sources", []) if "error" not in result else []
                meta = {
                    "intent": result.get("intent", "?"),
                    "chunks": result.get("retrieval_count", 0),
                    "tokens": result.get("tokens_used", {}).get("total", 0),
                    "time": f"{result.get('processing_time', 0):.2f}",
                } if "error" not in result else {}

            else:
                # Streaming failed — fall back to normal
                result = api_request("POST", "/query", json=request_body)
                if "error" in result:
                    full_answer = f"❌ Error: {result['error']}"
                    st.error(full_answer)
                    sources = []
                    meta = {}
                else:
                    full_answer = result.get("answer", "No answer generated.")
                    st.markdown(full_answer)
                    sources = result.get("sources", [])
                    meta = {
                        "intent": result.get("intent", "?"),
                        "chunks": result.get("retrieval_count", 0),
                        "tokens": result.get("tokens_used", {}).get("total", 0),
                        "time": f"{result.get('processing_time', 0):.2f}",
                    }

        except Exception:
            # Connection error — fall back to normal
            result = api_request("POST", "/query", json=request_body)
            if "error" in result:
                full_answer = f"❌ Error: {result['error']}"
                st.error(full_answer)
                sources = []
                meta = {}
            else:
                full_answer = result.get("answer", "No answer generated.")
                st.markdown(full_answer)
                sources = result.get("sources", [])
                meta = {
                    "intent": result.get("intent", "?"),
                    "chunks": result.get("retrieval_count", 0),
                    "tokens": result.get("tokens_used", {}).get("total", 0),
                    "time": f"{result.get('processing_time', 0):.2f}",
                }

        # Show sources
        if sources:
            with st.expander(f"📎 Sources ({len(sources)} references)"):
                for s in sources:
                    st.caption(
                        f"📄 {s.get('file', '?')} | "
                        f"Slide {s.get('slide', '?')} | "
                        f"Client: {s.get('client', '?')} | "
                        f"Type: {s.get('section_type', '?')}"
                    )

        # Show metadata
        if meta:
            with st.expander("ℹ️ Details"):
                c1, c2, c3, c4 = st.columns(4)
                c1.caption(f"Intent: {meta.get('intent', '?')}")
                c2.caption(f"Chunks: {meta.get('chunks', '?')}")
                c3.caption(f"Tokens: {meta.get('tokens', '?')}")
                c4.caption(f"Time: {meta.get('time', '?')}s")

        # Save to history
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_answer,
            "sources": sources,
            "metadata": meta,
        })