import streamlit as st
import pandas as pd
import os
import time
import subprocess
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# --- SEADISTUS ---
st.set_page_config(page_title="Vibe Trader", layout="wide", initial_sidebar_state="expanded")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")

load_dotenv(os.path.join(BASE_DIR, ".env"))
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

st.title("🤖 Vibe Trader Dashboard")

# --- KÜLGRIBA ---
with st.sidebar:
    st.header("🎮 Juhtimine")
    if st.button("🚀 KÄIVITA BOT", type="primary", use_container_width=True):
        try:
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.toast("Bot käivitatud!", icon="🚀")
        except Exception as e: st.error(f"Viga: {e}")
    
    if st.button("🔄 VÄRSKENDA LEHTE", use_container_width=True): 
        st.rerun()
    
    st.divider()
    
    # --- LIVE LÜLITI ---
    st.write("### 📺 Live Terminal")
    is_live = st.toggle("Käivita Live Vaade", value=False)
    if is_live:
        st.caption("⚠️ Kui see on sees, jookseb logi reaalajas. Peata see, et näha graafikut.")

# --- GRAAFIK (Ainult siis, kui LIVE on VÄLJAS) ---
# Me peidame graafiku live ajal, et säästa ressursse ja vältida virvendust
if not is_live:
    if api_key and secret_key:
        try:
            url = "https://paper-api.alpaca.markets/v2/account/portfolio/history"
            headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
            params = {"period": "1M", "timeframe": "1D"}
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if "equity" in data:
                    df = pd.DataFrame({"Equity": data["equity"], "Date": [datetime.fromtimestamp(t) for t in data["timestamp"]]})
                    df.set_index("Date", inplace=True)
                    
                    curr_eq = df["Equity"].iloc[-1]
                    start_eq = df["Equity"].iloc[0]
                    diff = curr_eq - start_eq
                    color = "green" if diff >= 0 else "red"
                    
                    st.metric(label="Portfelli Väärtus", value=f"${curr_eq:,.2f}", delta=f"{diff:,.2f}")
                    st.line_chart(df["Equity"], height=250)
        except Exception as e:
            st.warning(f"Graafiku viga: {e}")
    st.markdown("---")

# --- LOGIDE ALA ---
log_placeholder = st.empty()
ai_placeholder = st.empty()

def read_logs():
    log_content = "Logi puudub."
    ai_content = "AI info puudub."
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            log_content = "".join(lines[-50:]) # Viimased 50 rida
            
    if os.path.exists(AI_LOG_FILE):
        with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            ai_content = "".join(lines[-50:])
            
    return log_content, ai_content

# --- LOOGIKA: LIVE vs STATIC ---
if is_live:
    # LIVE REŽIIM: Jookseb tsüklis ja uuendab ekraani
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.subheader("🔴 LIVE LOGI")
        log_box = st.empty()
    with col2:
        st.subheader("🤖 AI LIVE")
        ai_box = st.empty()
        
    while True:
        logs, ai = read_logs()
        log_box.code(logs, language="log")
        ai_box.text_area("AI", ai, height=400, key=time.time()) # Key muudatus sunnib redraw
        time.sleep(1) # Värskenda iga 1 sekundi tagant
        
else:
    # TAVALINE REŽIIM
    logs, ai = read_logs()
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.subheader("📜 Boti Logi")
        st.code(logs, language="log")
    with col2:
        st.subheader("🤖 AI Otsused")
        st.text_area("AI", ai, height=400)