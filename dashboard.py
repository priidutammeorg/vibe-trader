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

# --- GRAAFIK & PROFIT (RAW REQUEST MODE) ---
if api_key and secret_key:
    try:
        # Pärime otse API-st, et vältida SDK vigu
        url = "https://paper-api.alpaca.markets/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key
        }
        # Küsime 1 kuu (1M) andmeid päevase (1D) sammuga
        params = {"period": "1M", "timeframe": "1D"}
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            # Kontrollime, kas andmeid tuli
            if "equity" in data and len(data["equity"]) > 0:
                timestamps = data["timestamp"]
                equities = data["equity"]
                
                # Teeme DataFrame
                df = pd.DataFrame({
                    "Equity": equities,
                    "Date": [datetime.fromtimestamp(t) for t in timestamps]
                })
                df.set_index("Date", inplace=True)
                
                # Arvutame kasumi
                start_val = df["Equity"].iloc[0] if len(df) > 0 else 0
                end_val = df["Equity"].iloc[-1] if len(df) > 0 else 0
                profit = end_val - start_val
                color = "green" if profit >= 0 else "red"
                
                st.subheader(f"Portfelli Väärtus: ${end_val:,.2f} (:{color}[${profit:,.2f}])")
                st.line_chart(df["Equity"], height=300)
            else:
                st.info("Portfelli ajalugu on veel tühi või liiga lühike.")
        else:
            st.error(f"Alpaca API viga: {response.status_code} - {response.text}")
            
    except Exception as e: 
        st.warning(f"Graafiku kuvamise viga: {e}")

st.markdown("---")

# --- JUHTIMINE ---
with st.sidebar:
    st.header("🎮 Juhtimine")
    if st.button("🚀 KÄIVITA BOT (main.py)", type="primary", use_container_width=True):
        try:
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.toast("Bot käivitatud! (Kontrolli logi)", icon="🚀")
            time.sleep(2)
            st.rerun()
        except Exception as e: st.error(f"Viga: {e}")
        
    if st.button("🔄 VÄRSKENDA LEHTE", use_container_width=True): 
        st.rerun()
        
    st.divider()
    st.caption("v33.0 Stable Release")

# --- LOGID ---
col1, col2 = st.columns([1.5, 1])

with col1:
    st.subheader("📜 Boti Logi (Live)")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # Näitame viimast 200 rida
            lines = f.readlines()
            st.code("".join(lines[-200:]), language="log")
    else:
        st.warning("Logifail puudub.")

with col2:
    st.subheader("🤖 AI Otsused")
    if os.path.exists(AI_LOG_FILE):
        with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            st.text_area("AI History", "".join(lines[-200:]), height=500, label_visibility="collapsed")
    else:
        st.info("AI ajalugu puudub.")