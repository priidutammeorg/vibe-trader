import streamlit as st
import pandas as pd
import os
import time

# --- SEADISTUS ---
CSV_FILE = "trade_archive.csv"
LOG_FILE = "bot.log"
PAGE_TITLE = "🤖 Vibe Trader Live Dashboard"

# Lehe seadistus (lai vaade)
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
        return lines[-100:][::-1] # Viimased 100 rida, tagurpidi
    except:
        return ["Viga logide lugemisel."]

# --- LEHE SISU ---

st.title(f"🚀 {PAGE_TITLE}")
st.markdown("---")

# Nupp käsitsi värskendamiseks
if st.button('🔄 Värskenda andmeid'):
    st.rerun()

# 1. STATISTIKA ARVUTAMINE
df = load_data()

col1, col2, col3, col4 = st.columns(4)

if not df.empty:
    total_profit = df['Profit USD'].sum()
    win_count = len(df[df['Profit USD'] > 0])
    loss_count = len(df[df['Profit USD'] <= 0])
    total_trades = len(df)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    
    last_trade = df.iloc[-1]
    
    # KUVAME MEETRIKAD
    col1.metric("💰 Kogukasum (PnL)", f"${total_profit:.2f}", delta_color="normal")
    col2.metric("🎯 Võiduprotsent", f"{win_rate:.1f}%", f"{win_count}W / {loss_count}L")
    col3.metric("📊 Tehingute arv", f"{total_trades}")
    
    last_pnl = last_trade['Profit USD']
    last_color = "normal" if last_pnl == 0 else "off" # Streamlit hack värvideks
    col4.metric(
        "⏱ Viimane tehing", 
        f"{last_trade['Symbol']}", 
        f"${last_pnl:.2f} ({last_trade['Reason']})"
    )
    
    # 2. GRAAFIKUD
    st.subheader("📈 Kasumikõver (Equity Curve)")
    
    # Arvutame jooksva kasumi
    df = df.sort_values(by='Time')
    df['Cumulative Profit'] = df['Profit USD'].cumsum()
    
    st.line_chart(df, x='Time', y='Cumulative Profit')
    
    # 3. TABEL
    with st.expander("📂 Vaata tehingute ajalugu (Detailid)"):
        st.dataframe(df.sort_values(by='Time', ascending=False).style.format({
            'Profit USD': '${:.2f}',
            'Profit %': '{:.2f}%',
            'Entry Price': '${:.4f}',
            'Exit Price': '${:.4f}'
        }))

else:
    st.warning("📭 Ajalugu on tühi. Oota esimest tehingut (müüki).")

st.markdown("---")

# 4. LIVE LOGID
st.subheader("📟 Boti Aju (Live Logid)")
logs = load_logs()
log_text = "".join(logs)
st.text_area("Logi väljund:", log_text, height=400)

# Automaatne värskendus (iga 30 sekundi tagant)
time.sleep(30)
st.rerun()