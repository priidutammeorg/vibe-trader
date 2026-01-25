import streamlit as st
import pandas as pd
import os
import time

# --- SEADISTUS ---
CSV_FILE = "trade_archive.csv"
LOG_FILE = "bot.log"
AI_LOG_FILE = "ai_history.log"
PAGE_TITLE = "🤖 Vibe Trader Live Dashboard"

# Lehe seadistus
st.set_page_config(page_title=PAGE_TITLE, layout="wide")

# --- FUNKTSIOONID ---

def load_data():
    """Loeb ajaloo CSV-st"""
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    except:
        return pd.DataFrame()

def load_logs():
    """Loeb viimased logid"""
    if not os.path.exists(LOG_FILE):
        return ["Logifail puudub."]
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        return lines[-100:][::-1] # Viimased 100 rida
    except:
        return ["Viga logide lugemisel."]

def load_ai_logs():
    """Loeb AI mõttekäigu logi"""
    if not os.path.exists(AI_LOG_FILE):
        return "AI pole veel ühtegi analüüsi teinud või fail puudub."
    try:
        with open(AI_LOG_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except: return "Viga AI logi lugemisel."

# --- LEHE SISU ---

st.title(f"🚀 {PAGE_TITLE}")
st.markdown("---")

# Nupp käsitsi värskendamiseks
if st.button('🔄 Värskenda andmeid'):
    st.rerun()

# 1. STATISTIKA
df = load_data()

col1, col2, col3, col4 = st.columns(4)

if not df.empty:
    total_profit = df['Profit USD'].sum()
    win_count = len(df[df['Profit USD'] > 0])
    loss_count = len(df[df['Profit USD'] <= 0])
    total_trades = len(df)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    
    last_trade = df.iloc[-1]
    
    col1.metric("💰 Kogukasum", f"${total_profit:.2f}")
    col2.metric("🎯 Võiduprotsent", f"{win_rate:.1f}%", f"{win_count}W / {loss_count}L")
    col3.metric("📊 Tehingute arv", f"{total_trades}")
    col4.metric("⏱ Viimane tehing", f"{last_trade['Symbol']}", f"${last_trade['Profit USD']:.2f}")
    
    # 2. GRAAFIKUD
    st.subheader("📈 Kasumikõver")
    df = df.sort_values(by='Time')
    df['Cumulative Profit'] = df['Profit USD'].cumsum()
    st.line_chart(df, x='Time', y='Cumulative Profit')
    
    # 3. TABEL
    with st.expander("📂 Vaata tehingute ajalugu (Detailid)"):
        st.dataframe(df.sort_values(by='Time', ascending=False).style.format({'Profit USD': '${:.2f}'}))

else:
    st.warning("📭 Ajalugu on tühi. Oota esimest tehingut.")

st.markdown("---")

# --- UUS: AI MÕTTEKÄIK ---
st.subheader("🧠 Tehisintellekti Aju")
with st.expander("Vaata, mida AI tegelikult mõtles (Prompt & Vastus)"):
    ai_logs = load_ai_logs()
    # Näitame viimast 10000 tähemärki, et pilti mitte umbe ajada
    st.text_area("AI Logi:", ai_logs[-10000:], height=400)

st.markdown("---")

# 4. TAVALISED LOGID
st.subheader("📟 Süsteemi Logid")
logs = load_logs()
log_text = "".join(logs)
st.text_area("Logi väljund:", log_text, height=300)

# Automaatne värskendus
time.sleep(30)
st.rerun()