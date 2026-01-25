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

# --- KÜLGRIBA JA JUHTIMINE ---
with st.sidebar:
    st.header("🎮 Juhtimine")
    
    # 1. KÄIVITA
    if st.button("🚀 KÄIVITA BOT", type="primary", use_container_width=True):
        try:
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.toast("Bot käivitatud!", icon="🚀")
        except Exception as e: st.error(f"Viga: {e}")
        
    # 2. VÄRSKENDA MANUAALSELT
    if st.button("🔄 VÄRSKENDA (Manual)", use_container_width=True): 
        st.rerun()
    
    st.divider()
    
    # --- UUS: LIVE REFRESH TOGGLE ---
    # See sunnib lehte ennast uuesti laadima
    auto_refresh = st.toggle("🔴 LIVE LOGI (2s)", value=False)
    
    st.caption("v34.1 Auto-Refresh")

# --- GRAAFIK ---
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
                st.metric(label="Portfelli Väärtus", value=f"${curr_eq:,.2f}")
                st.line_chart(df["Equity"], height=250)
    except: pass

st.markdown("---")

# --- LOGID (AUTOMAATSELT KERIVAD LÕPPU) ---
col1, col2 = st.columns([1.5, 1])

with col1:
    st.subheader("📜 Boti Logi")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Näitame viimast 50 rida, et pilt oleks selge
            log_content = "".join(lines[-50:])
            st.code(log_content, language="log")
    else:
        st.warning("Logifail puudub.")

with col2:
    st.subheader("🤖 AI Otsused")
    if os.path.exists(AI_LOG_FILE):
        with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            st.text_area("AI", "".join(lines[-50:]), height=400)

# --- AUTOMAATNE VÄRSKENDUS ---
# See koodijupp peab olema faili lõpus
if auto_refresh:
    time.sleep(2) # Oota 2 sekundit
    st.rerun()    # Lae leht uuesti