import streamlit as st
import pandas as pd
import os
import time
import subprocess
import json
from datetime import datetime
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# --- 1. KONFIGURATSIOON ---
st.set_page_config(page_title="Vibe Trader", layout="wide", initial_sidebar_state="expanded")

# --- 2. FAILIDE ASUKOHAD & API ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")

# Laeme API võtmed graafiku jaoks
load_dotenv(os.path.join(BASE_DIR, ".env"))
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

# --- 3. PÄIS JA GRAAFIK ---
st.title("🤖 Vibe Trader Dashboard")

# PORTFELLI GRAAFIK (TAGASI TOODUD!)
if api_key and secret_key:
    try:
        trade_client = TradingClient(api_key, secret_key, paper=True)
        # Võtame 1 kuu ajaloo
        history = trade_client.get_portfolio_history(period="1M", timeframe="1D")
        
        # Teeme andmed ilusaks graafikuks
        df = pd.DataFrame({
            "Equity": history.equity,
            "Date": [datetime.fromtimestamp(t) for t in history.timestamp]
        })
        df.set_index("Date", inplace=True)
        
        # Arvutame kasvu
        start_val = df["Equity"].iloc[0]
        end_val = df["Equity"].iloc[-1]
        profit = end_val - start_val
        color = "green" if profit >= 0 else "red"
        
        st.subheader(f"Portfelli Väärtus: ${end_val:,.2f} (:{color}[${profit:,.2f}])")
        st.line_chart(df["Equity"], height=250)
        
    except Exception as e:
        st.warning(f"Graafikut ei saanud laadida: {e}")

st.markdown("---")

# --- 4. KÜLGRIBA ---
with st.sidebar:
    st.header("🎮 Juhtimine")
    
    if st.button("🚀 KÄIVITA BOT (main.py)", type="primary", use_container_width=True):
        try:
            subprocess.Popen(["python3", "main.py"], cwd=BASE_DIR)
            st.toast("Käsk saadetud! Bot alustab...", icon="🚀")
            time.sleep(2)
            st.rerun()
        except Exception as e:
            st.error(f"Viga: {e}")

    if st.button("🔄 VÄRSKENDA", use_container_width=True):
        st.rerun()
        
    st.divider()
    st.caption("v31.5 Fixed Edition")

# --- 5. LOGID JA INFO ---
col1, col2 = st.columns([1.5, 1])

# LOGI (VASAKUL)
with col1:
    st.subheader("📜 Boti Tegevused (Live)")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Näitame viimast 100 rida
            st.code("".join(lines[-100:]), language="log")
    else:
        st.warning("Logifail puudub.")

# AI JA MÄLU (PAREMAL)
with col2:
    st.subheader("🤖 AI Otsused")
    if os.path.exists(AI_LOG_FILE):
        with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
            ai_lines = f.readlines()
            st.text_area("AI History", "".join(ai_lines[-100:]), height=300, label_visibility="collapsed")
    else:
        st.info("AI ajalugu puudub.")

    st.divider()
    
    # PEIDETUD MÄLU (Et ei risustaks pilti)
    with st.expander("🧠 Vaata Tehnilist Mälu (JSON)"):
        if os.path.exists(BRAIN_FILE):
            try:
                with open(BRAIN_FILE, "r") as f:
                    st.json(json.load(f))
            except: st.error("JSON katki")
        else: st.write("Tühi")