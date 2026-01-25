import streamlit as st
import pandas as pd
import os
import time
import subprocess

# --- 1. KONFIGURATSIOON (PEAB OLEMA ALATI ESIMENE) ---
st.set_page_config(
    page_title="Vibe Trader",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. FAILIDE ASUKOHAD ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")

# --- 3. STIIL JA PÄIS ---
st.title("🤖 Vibe Trader Dashboard")
st.markdown("---")

# --- 4. KÜLGRIBA (NUPUD) ---
with st.sidebar:
    st.header("🎮 Juhtimine")
    
    # KÄIVITUSNUPP
    if st.button("🚀 KÄIVITA BOT (main.py)", use_container_width=True):
        try:
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.toast("✅ Bot on käivitatud taustal!", icon="🚀")
            time.sleep(1) # Ootame hetke
            st.rerun()    # Värskendame kohe
        except Exception as e:
            st.error(f"Viga: {e}")

    st.divider()

    # VÄRSKENDUSNUPP
    if st.button("🔄 VÄRSKENDA ANDMEID", use_container_width=True):
        st.rerun()

# --- 5. PEAMINE SISU (VEERUD) ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📜 Boti Logi (Live)")
    # Loeme logifaili ohutult
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Näitame viimast 30 rida tagurpidi (uusim üleval)
            last_lines = lines[-30:]
            log_text = "".join(last_lines)
        
        # Kuvame koodiplokina parema loetavuse huvides
        st.code(log_text, language="log")
    else:
        st.warning("⚠️ Logifaili (bot.log) ei leitud.")

with col2:
    st.subheader("🧠 Boti Mälu")
    # Loeme mälufaili
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, "r") as f:
                import json
                brain_data = json.load(f)
            st.json(brain_data)
        except:
            st.error("Brain.json on vigane.")
    else:
        st.info("Mälu tühi.")

# --- 6. AI AJALUGU (ALL) ---
st.markdown("---")
st.subheader("🤖 AI Otsused (Viimased)")
if os.path.exists(AI_LOG_FILE):
    with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
        ai_lines = f.readlines()
        # Filtreerime tühjad read ja näitame viimaseid
        clean_ai = "".join(ai_lines[-50:])
    st.text_area("AI Logi", clean_ai, height=300)
else:
    st.caption("AI ajalugu puudub.")