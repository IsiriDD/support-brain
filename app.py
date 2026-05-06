import streamlit as st
from google import genai
from google.genai import types
from atlassian import Confluence
import re

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Support Brain", page_icon="🧠", layout="centered")

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 760px; }
.sb-logo { font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 500; color: #1a1a1a; }
.sb-tagline { font-size: 13px; color: #888; margin-bottom: 1.5rem; font-family: 'IBM Plex Mono', monospace; }
.sb-badge { display: inline-block; font-size: 11px; font-family: 'IBM Plex Mono', monospace; padding: 2px 8px; border-radius: 3px; border: 1px solid #ddd; color: #555; margin-right: 4px; }
.sb-badge.live { border-color: #2ecc71; color: #27ae60; background: #f0fff4; }
.msg-user { background: #f5f5f5; border-left: 3px solid #1a1a1a; padding: 12px 16px; border-radius: 0 6px 6px 0; margin: 12px 0; font-size: 15px; }
.msg-ai { background: #fff; border: 1px solid #e8e8e8; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 6px 6px 0; margin: 12px 0; font-size: 15px; line-height: 1.7; }
.msg-label { font-size: 10px; font-family: 'IBM Plex Mono', monospace; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: #aaa; margin-bottom: 6px; }
.source-row { margin-top: 10px; padding-top: 10px; border-top: 1px solid #f0f0f0; font-size: 12px; font-family: 'IBM Plex Mono', monospace; color: #999; }
.source-chip { display: inline-block; background: #f7f7f7; border: 1px solid #e8e8e8; border-radius: 3px; padding: 1px 7px; margin: 2px 3px 2px 0; font-size: 11px; color: #666; }
.sug-label { font-size: 11px; font-family: 'IBM Plex Mono', monospace; color: #bbb; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.07em; }
hr { border: none; border-top: 1px solid #f0f0f0; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Credentials ────────────────────────────────────────────────────────────────
GEMINI_API_KEY       = st.secrets.get("GEMINI_API_KEY", "")
CONFLUENCE_URL       = st.secrets.get("CONFLUENCE_URL", "")
CONFLUENCE_USERNAME  = st.secrets.get("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "")
CONFLUENCE_SPACE     = st.secrets.get("CONFLUENCE_SPACE", "")

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM = """You are Support Brain — an AI assistant for Datadog Premier Support Engineers (PSEs).
You help engineers quickly find answers from internal runbooks, Confluence docs, and team knowledge.

Guidelines:
- Be concise and practical. Engineers are in the middle of customer issues.
- If Confluence excerpts are provided, base your answer on them and cite the page title.
- Format troubleshooting steps as numbered lists.
- Keep answers under 250 words.
- End every answer with a SOURCES line in this exact format:
  SOURCES: [source1 | source2]
  Use doc titles from the excerpts, or "Support Brain knowledge base" if no docs were provided.
- Sound like a knowledgeable senior PSE, not a generic chatbot."""

# ── Gemini client ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    return genai.Client(api_key=GEMINI_API_KEY)

# ── Confluence search ──────────────────────────────────────────────────────────
@st.cache_resource
def get_confluence():
    if not CONFLUENCE_URL:
        return None
    return Confluence(url=CONFLUENCE_URL, username=CONFLUENCE_USERNAME, password=CONFLUENCE_API_TOKEN, cloud=True)

def search_confluence(query: str, limit: int = 3) -> list[dict]:
    cf = get_confluence()
    if not cf:
        return []
    try:
        cql = f'type=page AND space="{CONFLUENCE_SPACE}" AND text~"{query}"'
        results = cf.cql(cql, limit=limit).get("results", [])
        pages = []
        for r in results:
            page_id = r["content"]["id"]
            page = cf.get_page_by_id(page_id, expand="body.storage")
            raw_html = page.get("body", {}).get("storage", {}).get("value", "")
            text = re.sub(r"<[^>]+>", " ", raw_html)
            text = re.sub(r"\s+", " ", text).strip()[:800]
            pages.append({"title": page["title"], "url": f"{CONFLUENCE_URL}/wiki{page['_links']['webui']}", "excerpt": text})
        return pages
    except Exception:
        return []

# ── Ask Gemini ─────────────────────────────────────────────────────────────────
def ask_gemini(question: str, confluence_docs: list[dict], history: list) -> str:
    client = get_client()

    context = ""
    if confluence_docs:
        context = "\n\nRelevant Confluence docs:\n"
        for doc in confluence_docs:
            context += f"\n--- {doc['title']} ---\n{doc['excerpt']}\n"

    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=question + context)]))

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=SYSTEM),
        contents=contents,
    )
    return response.text

# ── Parse sources ──────────────────────────────────────────────────────────────
def parse_response(raw: str):
    sources = []
    text = raw
    match = re.search(r"SOURCES:\s*\[([^\]]+)\]", raw, re.IGNORECASE)
    if match:
        sources = [s.strip() for s in match.group(1).split("|")]
        text = raw[:match.start()].strip()
    return text, sources

# ── Session state ──────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:28px;">🧠</span>
  <span class="sb-logo">Support Brain</span>
</div>
<div class="sb-tagline">
  AI knowledge assistant for Datadog PSEs &nbsp;·&nbsp;
  <span class="sb-badge live">● Confluence</span>
  <span class="sb-badge">Gemini 2.0 Flash</span>
</div>
""", unsafe_allow_html=True)

# ── Suggestions ────────────────────────────────────────────────────────────────
SUGGESTIONS = [
    "How do I troubleshoot DogStatsD packet loss?",
    "What is the P1 escalation process?",
    "How do I onboard a new customer to APM?",
    "What are common causes of Agent not reporting?",
]

if not st.session_state.history:
    st.markdown('<div class="sug-label">Try asking</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, sug in enumerate(SUGGESTIONS):
        if cols[i % 2].button(sug, key=f"sug_{i}", use_container_width=True):
            st.session_state.pending_question = sug
            st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# ── Chat history ───────────────────────────────────────────────────────────────
for turn in st.session_state.history:
    if turn["role"] == "user":
        st.markdown(f'<div class="msg-user"><div class="msg-label">You</div>{turn["content"]}</div>', unsafe_allow_html=True)
    else:
        sources_html = ""
        if turn.get("sources"):
            chips = "".join(f'<span class="source-chip">{s}</span>' for s in turn["sources"])
            sources_html = f'<div class="source-row">📄 {chips}</div>'
        st.markdown(f'<div class="msg-ai"><div class="msg-label">Support Brain</div>{turn["content"].replace(chr(10), "<br>")}{sources_html}</div>', unsafe_allow_html=True)

# ── Input ──────────────────────────────────────────────────────────────────────
with st.form("chat_form", clear_on_submit=True):
    question = st.text_input(
        "Your question",
        placeholder="Ask anything — runbooks, escalation steps, onboarding...",
        label_visibility="collapsed",
        value=st.session_state.pop("pending_question", ""),
    )
    submitted = st.form_submit_button("Ask →", use_container_width=True)

# ── Handle submission ──────────────────────────────────────────────────────────
if submitted and question.strip():
    with st.spinner("Thinking..."):
        try:
            confluence_docs = search_confluence(question)
            raw_answer = ask_gemini(question, confluence_docs, st.session_state.history)
            answer, sources = parse_response(raw_answer)
            st.session_state.history.append({"role": "user", "content": question})
            st.session_state.history.append({"role": "assistant", "content": answer, "sources": sources, "confluence": confluence_docs})
        except Exception as e:
            st.error(f"Error: {str(e)}")
    st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
if st.session_state.history:
    if st.button("Clear conversation", type="secondary"):
        st.session_state.history = []
        st.rerun()
