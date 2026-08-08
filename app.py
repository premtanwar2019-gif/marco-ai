import streamlit as st
import sqlite3
import os
import base64
import io
from PIL import Image
from groq import Groq
from duckduckgo_search import DDGS
from gtts import gTTS
from streamlit_mic_recorder import mic_recorder

# --- MARCO AI SVG LOGO ---
MARCO_LOGO_SVG = """<svg width="45" height="45" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M50 5 L90 27.5 L90 72.5 L50 95 L10 72.5 L10 27.5 Z" stroke="url(#marco_glow)" stroke-width="6" fill="#0d1117"/>
    <path d="M30 68 L30 32 L50 52 L70 32 L70 68" stroke="url(#marco_core)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="50" cy="52" r="4" fill="#00f2fe"/>
    <defs>
        <linearGradient id="marco_glow" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#00f2fe"/>
            <stop offset="100%" stop-color="#4facfe"/>
        </linearGradient>
        <linearGradient id="marco_core" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#00f2fe"/>
            <stop offset="50%" stop-color="#00c6ff"/>
            <stop offset="100%" stop-color="#0072ff"/>
        </linearGradient>
    </defs>
</svg>"""

svg_bytes = MARCO_LOGO_SVG.encode('utf-8')
svg_base64 = base64.b64encode(svg_bytes).decode('utf-8')
favicon_data_url = f"data:image/svg+xml;base64,{svg_base64}"

st.set_page_config(page_title="MARCO AI", page_icon=favicon_data_url, layout="wide")

# --- CUSTOM CSS: DISABLE PULL TO REFRESH & ALIGN MIC WITH CHAT INPUT AT BOTTOM ---
st.markdown(
    """
    <style>
        html, body, .stApp {
            overscroll-behavior-y: contain !important;
            overflow-y: auto !important;
        }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stAppHeader {display: none !important;}
        [data-testid="stHeader"] {display: none !important;}
        [data-testid="stToolbar"] {display: none !important;}
        
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 6rem !important;
        }

        /* POSITION MIC ICON EXACTLY NEXT TO CHAT INPUT AT THE BOTTOM */
        div[data-testid="stCustomComponentV1"] {
            position: fixed !important;
            bottom: 22px !important;
            right: 40px !important;
            z-index: 999999 !important;
        }
        
        /* Make space inside Chat Input so text/send button don't overlap mic */
        div[data-testid="stChatInput"] {
            padding-right: 60px !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- DATABASE SETUP ---
DB_NAME = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  session_id TEXT, 
                  role TEXT, 
                  content TEXT)''')
    conn.commit()
    conn.close()

def load_chat(session_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
    messages = [{"role": row[0], "content": row[1]} for row in c.fetchall()]
    conn.close()
    return messages

def save_message(session_id, role, content):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
    conn.commit()
    conn.close()

def delete_chat(session_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

init_db()

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are MARCO AI, a smart, direct, and authentic AI collaborator.

STRICT LANGUAGE & TONE RULES:
1. MATCH THE USER'S LANGUAGE EXACTLY: 
   - If user speaks Hinglish (Roman Hindi), respond ONLY in pure casual Hinglish.
   - If user speaks Hindi, respond ONLY in Hindi.
   - If user speaks English, respond ONLY in English.
2. MATCH THE USER'S VIBE: Be casual, witty, and peer-like when the user is casual.
3. ZERO DISCLAIMERS: Bold (**bold**) key terms and concepts when giving technical answers.
"""

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
client = Groq(api_key=GROQ_API_KEY)

def perform_web_search(query):
    query_lower = query.strip().lower()
    greetings = ["hi", "hello", "hey", "kaise ho", "kya haal hai", "kya kar rahe ho"]
    if any(query_lower == g or query_lower.startswith(g + " ") for g in greetings):
        return ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                search_data = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
                return f"\n\n[REAL-TIME SEARCH CONTEXT]:\n{search_data}"
    except Exception:
        return ""
    return ""

# --- SIDEBAR ---
sidebar_header = f'''
<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
    {MARCO_LOGO_SVG}
    <span style="font-size: 24px; font-weight: 800; letter-spacing: 1px; color: #1a202c;">MARCO AI</span>
</div>
'''
st.sidebar.markdown(sidebar_header, unsafe_allow_html=True)

passcode = st.sidebar.text_input("🔑 Boss Passcode", type="password")
if passcode == "1234":
    st.sidebar.success("Authenticated")
else:
    st.sidebar.warning("Enter correct Passcode")
    st.stop()

if st.sidebar.button("➕ New Chat"):
    st.session_state["session_id"] = os.urandom(8).hex()
    st.session_state["messages"] = []
    st.session_state["last_processed_audio"] = None
    st.rerun()

if "session_id" not in st.session_state:
    st.session_state["session_id"] = "default_session"

enable_search = st.sidebar.checkbox("🌐 Enable Real-Time Web Search", value=True)
enable_tts = st.sidebar.checkbox("🔊 Voice Reply (Speech Output)", value=True)
ai_mode = st.sidebar.selectbox("🎯 AI Mode", ["Default (Adaptive)", "Concise", "Detailed"])

st.sidebar.divider()
st.sidebar.subheader("📜 Chat History (RECENTS)")

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute("SELECT DISTINCT session_id FROM messages")
sessions = [row[0] for row in c.fetchall()]
conn.close()

for s_id in sessions:
    col1_hist, col2_hist = st.sidebar.columns([4, 1])
    with col1_hist:
        if st.button(f"👉 Chat {s_id[:6]}", key=f"load_{s_id}"):
            st.session_state["session_id"] = s_id
            st.session_state["messages"] = load_chat(s_id)
            st.session_state["last_processed_audio"] = None
            st.rerun()
    with col2_hist:
        if st.button("🗑️", key=f"del_{s_id}"):
            delete_chat(s_id)
            if st.session_state["session_id"] == s_id:
                st.session_state["session_id"] = os.urandom(8).hex()
                st.session_state["messages"] = []
            st.rerun()

# --- MAIN CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state["messages"] = load_chat(st.session_state["session_id"])

if not st.session_state["messages"]:
    large_logo = MARCO_LOGO_SVG.replace('width="45"', 'width="85"').replace('height="45"', 'height="85"')
    entrance_html = f'''
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50vh; text-align: center;">
        {large_logo}
        <div style="font-size: 30px; font-weight: 700; color: #1a202c; margin-top: 20px;">
            Welcome Boss, What shall MARCO solve today?
        </div>
    </div>
    '''
    st.markdown(entrance_html, unsafe_allow_html=True)

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT HANDLING ---
input_text = ""

# Floating Mic Component (Placed at bottom via CSS)
audio_data = mic_recorder(
    start_prompt="🎙️",
    stop_prompt="⏹️",
    key="gemini_mic_btn",
    just_once=True
)

# Prevent Spam Loop: Process audio only once
if "last_processed_audio" not in st.session_state:
    st.session_state["last_processed_audio"] = None

if audio_data and "bytes" in audio_data and audio_data["id"] != st.session_state["last_processed_audio"]:
    st.session_state["last_processed_audio"] = audio_data["id"]
    with st.spinner("Processing Voice..."):
        try:
            audio_bytes = audio_data["bytes"]
            audio_file = ("audio.wav", audio_bytes, "audio/wav")
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file
            )
            input_text = transcription.text
        except Exception as e:
            st.error(f"Voice Error: {e}")

# Native Chat Input (Includes Send Button)
user_input = st.chat_input("Ask MARCO AI anything or attach a screenshot...", accept_file=True, file_type=["jpg", "jpeg", "png"])

if user_input and not input_text:
    input_text = user_input.text if hasattr(user_input, "text") and user_input.text else str(user_input)

# --- PROCESS RESPONSE ---
if input_text:
    st.session_state["messages"].append({"role": "user", "content": input_text})
    save_message(st.session_state["session_id"], "user", input_text)

    with st.chat_message("assistant"):
        with st.spinner("MARCO is thinking..."):
            web_context = ""
            if enable_search:
                web_context = perform_web_search(input_text)

            final_system_prompt = SYSTEM_PROMPT
            if ai_mode == "Concise":
                final_system_prompt += "\nKEEP RESPONSE UNDER 3 SENTENCES."
            elif ai_mode == "Detailed":
                final_system_prompt += "\nPROVIDE IN-DEPTH EXPLANATIONS WITH EXAMPLES."

            api_messages = [{"role": "system", "content": final_system_prompt}]
            for m in st.session_state["messages"]:
                api_messages.append({"role": m["role"], "content": m["content"]})

            if web_context:
                api_messages[-1]["content"] += web_context

            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=api_messages,
                    temperature=0.6
                )
                bot_reply = response.choices[0].message.content
            except Exception as e:
                bot_reply = f"Error generating response: {str(e)}"

            st.markdown(bot_reply)
            st.session_state["messages"].append({"role": "assistant", "content": bot_reply})
            save_message(st.session_state["session_id"], "assistant", bot_reply)

            if enable_tts:
                try:
                    tts = gTTS(text=bot_reply.replace("*", ""), lang='hi' if any(ord(c) > 127 for c in bot_reply) else 'en')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    st.audio(fp, format="audio/mp3", autoplay=True)
                except Exception:
                    pass

            st.rerun()
