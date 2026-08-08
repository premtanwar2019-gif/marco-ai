import streamlit as st
import sqlite3
import os
import base64
import requests
import urllib.parse
from PIL import Image
from groq import Groq
from duckduckgo_search import DDGS

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

# --- APP CONFIGURATION ---
st.set_page_config(page_title="MARCO AI", page_icon=favicon_data_url, layout="wide")

# --- CUSTOM CSS ---
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
        button[title="View source"] {display: none !important;}
        [data-testid="stHeader"] {display: none !important;}
        [data-testid="stToolbar"] {display: none !important;}
        
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
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
2. ZERO DISCLAIMERS: Bold (**bold**) key terms and concepts when giving technical answers.
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

def generate_image_url(prompt):
    encoded_prompt = urllib.parse.quote(prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&model=flux&nologo=true&seed={os.urandom(4).hex()}"
    return image_url

def analyze_image_for_style(image_bytes, user_style_prompt):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": (
                                "Analyze this image accurately. Count the exact number of people, their genders, hairstyles, clothing colors, poses, and facial expressions. "
                                "Create a highly specific image generation prompt that recreates these EXACT subjects, their count, and clothing in the following artistic style: "
                                f"'{user_style_prompt}'. "
                                "Make sure to preserve subject genders, number of people in frame, facial features, and clothing colors accurately. "
                                "Output ONLY the prompt text without any preambles."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.3
        )
        vision_prompt = response.choices[0].message.content.strip()
        return f"{vision_prompt}, 8k resolution, highly detailed, masterpieces, masterpiece anime render"
    except Exception:
        return f"A boy wearing green t-shirt and a girl wearing brown top together, anime 4k style, high quality portrait"

# --- SIDEBAR UI ---
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

# SESSION MANAGEMENT
if "session_id" not in st.session_state:
    st.session_state["session_id"] = "default_session"

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state["session_id"] = os.urandom(8).hex()
        st.session_state["messages"] = []
        st.rerun()
with col_btn2:
    if st.button("🎨 Image Studio", use_container_width=True):
        st.session_state["session_id"] = "image_studio_channel"
        st.session_state["messages"] = load_chat("image_studio_channel")
        st.rerun()

is_image_channel = (st.session_state["session_id"] == "image_studio_channel")

if is_image_channel:
    st.sidebar.info("🖼️ **Mode:** Image Studio (Prompt ya Image attach karke convert karein)")
else:
    enable_search = st.sidebar.checkbox("🌐 Enable Real-Time Web Search", value=True)
    ai_mode = st.sidebar.selectbox("🎯 AI Mode", ["Default (Adaptive)", "Concise", "Detailed"])

st.sidebar.divider()
st.sidebar.subheader("📜 Chat History (RECENTS)")

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute("SELECT DISTINCT session_id FROM messages")
sessions = [row[0] for row in c.fetchall()]
conn.close()

for s_id in sessions:
    if s_id == "image_studio_channel":
        continue
    col1, col2 = st.sidebar.columns([4, 1])
    with col1:
        if st.button(f"👉 Chat {s_id[:6]}", key=f"load_{s_id}"):
            st.session_state["session_id"] = s_id
            st.session_state["messages"] = load_chat(s_id)
            st.rerun()
    with col2:
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
    title_text = "Welcome to Image Studio Boss, Describe or attach photo to convert!" if is_image_channel else "Welcome Boss, What shall MARCO solve today?"
    entrance_html = f'''
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50vh; text-align: center;">
        {large_logo}
        <div style="font-size: 28px; font-weight: 700; color: #1a202c; margin-top: 20px;">
            {title_text}
        </div>
    </div>
    '''
    st.markdown(entrance_html, unsafe_allow_html=True)

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

placeholder_text = "Attach photo + prompt or enter prompt to generate..." if is_image_channel else "Ask MARCO AI anything..."
user_input = st.chat_input(placeholder_text, accept_file=True, file_type=["jpg", "jpeg", "png"])

if user_input:
    input_text = user_input.text if hasattr(user_input, "text") and user_input.text else ""
    uploaded_files = user_input.files if hasattr(user_input, "files") and user_input.files else []
    
    if input_text or uploaded_files:
        display_msg = input_text if input_text else "Uploaded Image for transformation"
        st.session_state["messages"].append({"role": "user", "content": display_msg})
        save_message(st.session_state["session_id"], "user", display_msg)

        with st.chat_message("assistant"):
            with st.spinner("Processing..."):
                input_lower = input_text.lower()
                image_keywords = ["generate image", "make image", "draw", "create image", "image of", "picture of", "photo of", "/image", "anime", "4k", "convert"]
                
                # RULE 1: IF USER IS IN IMAGE STUDIO CHANNEL
                if is_image_channel:
                    user_style = input_text if input_text else "High quality 4k anime style transformation"
                    
                    if uploaded_files:
                        img_bytes = uploaded_files[0].getvalue()
                        final_prompt = analyze_image_for_style(img_bytes, user_style)
                    else:
                        img_prompt = input_text
                        for kw in ["generate image", "make image", "create image", "/image"]:
                            img_prompt = img_prompt.lower().replace(kw, "").strip()
                        final_prompt = f"{img_prompt}, 4k ultra detailed anime" if img_prompt else "futuristic anime 4k boss portrait"
                        
                    img_url = generate_image_url(final_prompt)
                    bot_reply = f"Here is your converted 4K Anime Image Boss:\n\n![Generated Image]({img_url})"
                    
                    st.markdown(bot_reply)
                    st.session_state["messages"].append({"role": "assistant", "content": bot_reply})
                    save_message(st.session_state["session_id"], "assistant", bot_reply)

                # RULE 2: IF USER ASKS FOR IMAGE IN NORMAL CHAT
                elif any(kw in input_lower for kw in image_keywords):
                    bot_reply = "⚠️ **Image Generation is restricted to the Image Studio channel.**\n\nSidebar mein **🎨 Image Studio** button par click karke wahan photo attach karke prompt bhejo!"
                    st.markdown(bot_reply)
                    st.session_state["messages"].append({"role": "assistant", "content": bot_reply})
                    save_message(st.session_state["session_id"], "assistant", bot_reply)

                # RULE 3: NORMAL CHAT RESPONSE
                else:
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
                
                st.rerun()
