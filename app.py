import streamlit as st
from google import genai
from google.genai import types
from atlassian import Confluence
import re

st.set_page_config(page_title="Support Brain", page_icon="🧠", layout="centered")

GEMINI_API_KEY       = st.secrets.get("GEMINI_API_KEY", "")
CONFLUENCE_URL       = st.secrets.get("CONFLUENCE_URL", "")
CONFLUENCE_USERNAME  = st.secrets.get("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "")
CONFLUENCE_SPACE     = st.secrets.get("CONFLUENCE_SPACE", "")

SYSTEM = """You are Support Brain, an AI assistant for Datadog Premier Support Engineers.
Answer questions about runbooks, escalation processes, and onboarding.
Be concise and practical. Use numbered lists for steps.
End with: SOURCES: [source1 | source2]"""

def ask_gemini(question, history):
    client = genai.Client(api_key=GEMINI_API_KEY)
    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    response = client.models.generate_content(
       model="gemini-1.5-flash",
        config=types.GenerateContentConfig(system_instruction=SYSTEM),
        contents=contents,
    )
    return response.text

if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🧠 Support Brain")
st.caption("AI knowledge assistant for Datadog PSEs · Gemini 2.0 Flash")
st.divider()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Ask anything — runbooks, escalation steps, onboarding..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                answer = ask_gemini(prompt, st.session_state.messages[:-1])
                st.write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"Error: {str(e)}")
