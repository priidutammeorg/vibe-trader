import streamlit as st
import pandas as pd
import os
import time
import subprocess
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

st.set_page_config(page_title="Vibe Trader", layout="wide", initial_sidebar_state="expanded")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")

load_dotenv(os.path.join(BASE_DIR, ".env"))
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

st.title("🤖 Vibe Trader Dashboard (Grand Restoration)")

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
                st.subheader(f"Equity: ${df['Equity'].iloc[-1]:,.2f}")
                st.line_chart(df["Equity"], height=300)
    except: st.warning("Graafik pole saadaval")

st.markdown("---")

with st.sidebar:
    if st.button("🚀 KÄIVITA BOT", type="primary"):
        subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
        st.toast("Bot käivitatud!")
    if st.button("🔄 VÄRSKENDA"): st.rerun()

col1, col2 = st.columns([1.5, 1])
with col1:
    st.subheader("📜 Logi")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f: st.code("".join(f.readlines()[-200:]), language="log")
with col2:
    st.subheader("🤖 AI")
    if os.path.exists(AI_LOG_FILE):
        with open(AI_LOG_FILE, "r") as f: st.text_area("AI", "".join(f.readlines()[-200:]), height=500)