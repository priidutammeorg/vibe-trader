import streamlit as st
import pandas as pd
import os
import json
import subprocess
import time

# --- SEADISTUS ---
st.set_page_config(page_title="Vibe Trader Dashboard", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")

# --- KÄIVITA BOT NUPP (UUS FUNKTSIOON) ---
with st.sidebar:
    st.header("🎮 Juhtimispult")
    
    # See nupp käivitab main.py päriselt
    if st.button("🚀 KÄIVITA BOT KOHE"):
        try:
            # Käivitame boti taustal, et dashboard kinni ei kiiluks
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.success("Käsk saadetud! Bot alustab tööd...")
            time.sleep(2)
            st.rerun() # Värskendame lehte, et näha uut logi
        except Exception as e:
            st.error(f"Viga käivitamisel: {e}")

    st.divider()

st.title("🤖 Vibe Trader Dashboard")

# --- 1. AJU JA STATUS ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📜 Boti Tegevused (Logi)")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Näitame viimast 30 rida
            recent_lines = lines[-30:]
            log_text = "".join(recent_lines)
            st.text_area("Live Log", log_text, height=400)
    else:
        st.warning("Logifaili ei leitud.")

with col2:
    st.subheader("🧠 Tehisintellekti Aju")
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, "r") as f:
                brain = json.load(f)
            st.json(brain)
        except:
            st.error("Brain fail on katki või tühi.")
    else:
        st.info("Brain faili pole veel loodud.")

# --- 2. AI ANALÜÜSI AJALUGU ---
st.subheader("🤖 AI Uudiste Analüüs")
if os.path.exists(AI_LOG_FILE):
    with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
        ai_lines = f.readlines()
        # Filtreerime välja tühjad read ja kuvame viimased kirjed
        clean_ai = [l for l in ai_lines if l.strip()]
        st.text_area("Viimased AI otsused", "".join(clean_ai[-40:]), height=300)
else:
    st.info("AI pole veel ühtegi analüüsi teinud.")

# --- AUTOMAATNE VÄRSKENDUS ---
# Värskendab lehte iga 30 sekundi tagant
time.sleep(30)
st.rerun()