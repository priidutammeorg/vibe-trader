import os
import sys
import time
import builtins
import traceback
import requests
import json
import csv
import random 
import xml.etree.ElementTree as ET
import pandas as pd
import ta
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI
import trafilatura
from ddgs import DDGS

# --- 0. SEADISTUS JA KONSTANDID ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(BASE_DIR, "bot.log")
BRAIN_FILE = os.path.join(BASE_DIR, "brain.json")
ARCHIVE_FILE = os.path.join(BASE_DIR, "trade_archive.csv") 
AI_LOG_FILE = os.path.join(BASE_DIR, "ai_history.log")     

# Kasutame seda, et vältida DDG blokeerimist, kui see juba juhtus
USE_BACKUP_SOURCE = False

# --- LOGIMISE SÜSTEEM ---
def print(*args, **kwargs):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kwargs.pop('flush', None)
    
    msg = " ".join(map(str, args))
    formatted_msg = f"[{now}] {msg}"
    
    # 1. LOGIFAILI (ALATI)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        builtins.print(f"[SYSTEM ERROR] Logi viga: {e}")

    # 2. EKRAANILE (AINULT TERMINALIS)
    if sys.stdout.isatty():
        builtins.print(formatted_msg, flush=True, **kwargs)

# --- CRASH CATCHER (STARTUP) ---
try:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not api_key or not secret_key or not openai_key:
        print("CRITICAL: .env failist on võtmed puudu!")
        exit()

    print("--- VIBE TRADER: v34.0 (GRAND RESTORATION) ---")

    # GLOBAL VARIABLES
    MARKET_MODE = "NEUTRAL" 

    trading_client = TradingClient(api_key, secret_key, paper=True)
    data_client = CryptoHistoricalDataClient()
    ai_client = OpenAI(api_key=openai_key)

    # STRATEEGIA KONSTANDID
    MIN_VOLUME_USD = 10000     
    MAX_AI_CALLS = 10          

except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}")
    print(traceback.format_exc())
    exit()

# --- 1. MÄLU JA ANDMEHALDUS ---

def load_brain():
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_brain(brain_data):
    try: 
        with open(BRAIN_FILE, 'w') as f: 
            json.dump(brain_data, f, indent=4)
    except: pass

def log_trade_to_csv(symbol, entry_price, exit_price, qty, reason):
    try:
        entry_price = float(entry_price)
        exit_price = float(exit_price)
        qty = float(qty)
        profit_usd = (exit_price - entry_price) * qty
        profit_pct = ((exit_price - entry_price) / entry_price) * 100
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        file_exists = os.path.isfile(ARCHIVE_FILE)
        with open(ARCHIVE_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Time", "Symbol", "Entry Price", "Exit Price", "Qty", "Profit USD", "Profit %", "Reason"])
            writer.writerow([timestamp, symbol, round(entry_price, 4), round(exit_price, 4), round(qty, 4), round(profit_usd, 2), round(profit_pct, 2), reason])
        print(f"   📝 AJALUGU SALVESTATUD: {symbol} PnL: ${profit_usd:.2f} ({profit_pct:.2f}%)")
    except Exception as e:
        print(f"   ❌ Viga CSV salvestamisel: {e}")

def log_ai_prompt(symbol, prompt_text, response_text):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] 🧠 ANALÜÜS: {symbol}\n")
            f.write("👇 --- INPUT ---\n")
            f.write(prompt_text.strip()[:500] + "...\n") # Hoiame logi puhtama
            f.write("👆 --- OUTPUT ---\n")
            f.write(response_text.strip() + "\n")
            f.write("="*60 + "\n\n")
    except Exception as e:
        print(f"Viga AI logimisel: {e}")

def update_position_metadata(symbol, atr_value):
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {"highest_price": 0, "atr_at_entry": atr_value, "is_risk_free": False}
    save_brain(brain)

def update_high_watermark(symbol, current_price, current_rsi=50):
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {"highest_price": current_price, "atr_at_entry": current_price * 0.05, "is_risk_free": False, "last_rsi": current_rsi}
    else:
        brain["positions"][symbol]["last_rsi"] = current_rsi
        if current_price > brain["positions"][symbol]["highest_price"]:
            brain["positions"][symbol]["highest_price"] = current_price
            save_brain(brain)
            return True
    save_brain(brain)
    return False

def set_risk_free_status(symbol):
    brain = load_brain()
    if "positions" in brain and symbol in brain["positions"]:
        brain["positions"][symbol]["is_risk_free"] = True
        save_brain(brain)

def get_position_data(symbol):
    brain = load_brain()
    return brain.get("positions", {}).get(symbol, {})

def is_cooled_down(symbol):
    brain = load_brain()
    last_sold = brain.get("cool_down", {}).get(symbol)
    if last_sold and datetime.now() - datetime.fromtimestamp(last_sold) < timedelta(hours=6):
        return False
    return True

def activate_cooldown(symbol):
    brain = load_brain()
    if "cool_down" not in brain: brain["cool_down"] = {}
    brain["cool_down"][symbol] = datetime.now().timestamp()
    if "positions" in brain and symbol in brain["positions"]:
        del brain["positions"][symbol]
    save_brain(brain)

# --- 2. TEHNILINE ANALÜÜS (TÄISMAHUS) ---

def format_symbol_for_yahoo(symbol):
    s = symbol.replace("/", "")
    if "PEPE" in s: return "PEPE24478-USD"
    if "UNI" in s and "UNIVERSE" not in s: return "UNI7083-USD"
    if "GRT" in s: return "GRT6719-USD"
    if s.endswith("USD"): return s[:-3] + "-USD"
    return s + "-USD"

def get_yahoo_data(symbol, period="1mo", interval="1h"):
    try:
        # Kiirem timeout, et mitte passida
        time.sleep(0.2)
        y_symbol = format_symbol_for_yahoo(symbol)
        df = yf.download(y_symbol, period=period, interval=interval, progress=False, timeout=10)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if 'close' not in df.columns: return None
        return df.dropna()
    except: return None

def determine_market_mode():
    global MARKET_MODE
    print("🔍 Analüüsin turu režiimi (BTC)...")
    df = get_yahoo_data("BTC/USD", period="6mo", interval="1d")
    if df is None or len(df) < 50:
        MARKET_MODE = "NEUTRAL"
        return
    current_price = df['close'].iloc[-1]
    sma50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
    
    if current_price > sma50:
        MARKET_MODE = "BULL"
        print(f"   🟢 TURG ON TUGEV (BULL). BTC ${current_price:.0f} > SMA50 ${sma50:.0f}")
    else:
        MARKET_MODE = "BEAR"
        print(f"   🔴 TURG ON NÕRK (BEAR). BTC ${current_price:.0f} < SMA50 ${sma50:.0f}")

def get_technical_analysis(symbol, alpaca_volume_usd):
    df = get_yahoo_data(symbol, period="1mo", interval="1h")
    if df is None or len(df) < 30: return 0, 0, 0, 0, 0 
    
    current_price = df['close'].iloc[-1]
    yahoo_vol_usd = df['volume'].iloc[-1] * current_price if 'volume' in df.columns else 0
    final_vol_usd = max(alpaca_volume_usd, yahoo_vol_usd)

    # Indikaatorid
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    macd_diff = ta.trend.macd_diff(df['close']).iloc[-1]
    adx = ta.trend.adx(df['high'], df['low'], df['close'], window=14).iloc[-1]
    atr = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
    
    if pd.isna(rsi): return 0, 0, 0, 0, 0

    score = 50
    if MARKET_MODE == "BULL":
        if rsi < 30: score += 30
        elif rsi < 55: score += 15 
        if macd_diff > 0: score += 10
        if adx > 25: score += 10
    elif MARKET_MODE == "BEAR":
        # Konservatiivne loogika
        if rsi < 25: score += 45     
        elif rsi < 30: score += 25  
        elif rsi > 45: score -= 50   
        if final_vol_usd > 1000000: score += 10
        if macd_diff > 0: score += 15 

    if final_vol_usd < 10000: score = 0
    if score >= 60:
        print(f"      📊 {symbol} ({MARKET_MODE}): RSI={rsi:.1f}, Vol=${final_vol_usd/1000:.0f}k. Skoor: {score}")
    
    return max(0, min(100, score)), atr, rsi

# --- 3. UUDISTE MOOTOR (HYBRID: DDG + YAHOO + GOOGLE) ---

def scrape_with_trafilatura(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            return text[:3000] if text else None
    except: pass
    return None

def get_google_rss_fallback(symbol):
    try:
        clean_ticker = symbol.split("/")[0] 
        url = f"https://news.google.com/rss/search?q={clean_ticker}+crypto+when:1d&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall('.//item')[:3]
            full_report = []
            for item in items:
                title = item.find('title').text
                pub = item.find('pubDate').text
                full_report.append(f"--- GOOGLE RSS ---\nTITLE: {title}\nDATE: {pub}\n")
            return "\n".join(full_report)
    except: pass
    return "No news found."

def get_yahoo_finance_news(symbol):
    try:
        y_symbol = format_symbol_for_yahoo(symbol)
        ticker = yf.Ticker(y_symbol)
        news = ticker.news
        report = []
        if news:
            for n in news[:3]:
                title = n.get('title', '')
                link = n.get('link', '')
                content = scrape_with_trafilatura(link)
                if not content: content = "Content unavailable."
                report.append(f"--- YAHOO ---\nTITLE: {title}\nLINK: {link}\nCONTENT: {content[:1000]}\n")
            return "\n".join(report)
    except: pass
    return None

def get_news_hybrid(symbol):
    global USE_BACKUP_SOURCE
    
    # 1. Kui DDG on juba katki, kasuta otse Yahoo/Google
    if USE_BACKUP_SOURCE:
        print(f"      ⚡ (Backup Mode) Kasutan Yahoo/Google...")
        res = get_yahoo_finance_news(symbol)
        if not res: res = get_google_rss_fallback(symbol)
        return res

    # 2. Proovi DuckDuckGo-d
    try:
        # Lühem paus (3-6s), et mitte "hanguda"
        sleep_time = random.uniform(3, 6)
        print(f"      ⏳ DDG: ootan {sleep_time:.1f}s...")
        time.sleep(sleep_time)

        clean_ticker = symbol.split("/")[0]
        keywords = f"{clean_ticker} crypto news"
        
        results = DDGS().news(keywords=keywords, region="wt-wt", safesearch="off", max_results=3)
        
        if not results: 
            return get_yahoo_finance_news(symbol) or get_google_rss_fallback(symbol)

        full_report = []
        for item in results:
            title = item.get('title', 'No Title')
            link = item.get('url', '')
            date = item.get('date', 'Today')
            content = scrape_with_trafilatura(link)
            if not content: content = item.get('body', '')
            full_report.append(f"--- ARTICLE ---\nTITLE: {title}\nDATE: {date}\nLINK: {link}\nCONTENT:\n{content[:2000]}\n")
            
        return "\n".join(full_report)

    except Exception as e:
        print(f"      ⚠️ DDG Viga! Lülitun Backup režiimile (Yahoo/Google).")
        USE_BACKUP_SOURCE = True # Edaspidi kasuta kohe backupi
        return get_yahoo_finance_news(symbol) or get_google_rss_fallback(symbol)

def analyze_coin_ai(symbol):
    news_text = get_news_hybrid(symbol)
    
    market_context = "BEAR MARKET (Trend is DOWN). Use EXTREME CAUTION." if MARKET_MODE == "BEAR" else "BULL MARKET. Look for MOMENTUM."

    prompt = f"""
    You are an Elite Crypto Trader.
    Analyze the following NEWS for {symbol} to decide on an immediate (24h) entry.
    
    MARKET CONTEXT: {market_context}
    
    === NEWS REPORT ===
    {news_text}
    
    === SCORING ===
    - 0-30: BAD NEWS. Sell.
    - 31-49: Bearish/Weak.
    - 50: Neutral / No real news.
    - 51-79: Good vibes.
    - 80-100: STRONG BUY.
    
    RESPONSE FORMAT (JSON):
    {{"score": X, "reason": "Detailed reason citing specific facts"}}
    """
    
    score = 50
    reason = "Analysis failed"

    try:
        res = ai_client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        full_response = res.choices[0].message.content
        data = json.loads(full_response)
        score = int(data.get("score", 50))
        reason = data.get("reason", "No reason provided")
    except Exception as e:
        reason = f"Error: {e}"
        score = 50

    print(f"      🤖 AI ANALÜÜS: {score}/100 | {reason[:100]}...")
    log_ai_prompt(symbol, prompt, f"SCORE: {score}\nREASON: {reason}")
    return score

# --- 4. HALDUS JA OSTMINE ---

# !!! SEE FUNKTSIOON OLI PUUDU, NÜÜD TAGASI !!!
def close_position(symbol, reason="UNKNOWN"):
    try:
        pos = trading_client.get_open_position(symbol)
        qty = float(pos.qty)
        entry = float(pos.avg_entry_price)
        curr = float(pos.current_price)
        
        trading_client.close_position(symbol)
        
        log_trade_to_csv(symbol, entry, curr, qty, reason)
        activate_cooldown(symbol)
        print(f"      ✅ TEHTUD! {symbol} müüdud. (Põhjus: {reason})")
    except Exception as e: 
        print(f"      ❌ Viga sulgemisel: {e}")

def manage_existing_positions():
    print("1. PORTFELL: Risk-Free & Profit Lock...")
    try: positions = trading_client.get_all_positions()
    except: return

    if not positions:
        print("   -> Portfell on tühi.")
        return

    for p in positions:
        symbol = p.symbol
        # time.sleep(0.5) # Eemaldame liigse ootamise
        
        entry_price = float(p.avg_entry_price)
        current_price = float(p.current_price)
        profit_pct = float(p.unrealized_plpc) * 100
        
        pos_data = get_position_data(symbol)
        hw = pos_data.get("highest_price", entry_price)
        atr = pos_data.get("atr_at_entry", current_price * 0.05)
        is_risk_free = pos_data.get("is_risk_free", False)
        
        if current_price > hw:
            update_high_watermark(symbol, current_price)
            hw = current_price
        
        if MARKET_MODE == "BEAR":
            trailing_stop = hw - (1.5 * atr)
            breakeven_trigger = 1.0 
            hard_stop = entry_price * 0.94
        else:
            trailing_stop = hw - (2.5 * atr)
            breakeven_trigger = 2.5
            hard_stop = entry_price * 0.92

        breakeven_price = entry_price * 1.005
        if profit_pct >= breakeven_trigger or is_risk_free:
            final_stop = max(breakeven_price, hard_stop)
            if trailing_stop > final_stop: final_stop = trailing_stop
            stop_type = "PROFIT 🛡️"
            if not is_risk_free: set_risk_free_status(symbol)
        else:
            final_stop = hard_stop
            stop_type = "HARD 🛑"
            
        print(f"   -> {symbol}: {profit_pct:.2f}% (Stop: ${final_stop:.2f} | {stop_type})")

        if current_price <= final_stop:
            print(f"      !!! STOP HIT ({stop_type})! Müün {symbol}...")
            close_position(symbol, stop_type)

def trade(symbol, score, atr):
    try: equity = float(trading_client.get_account().equity)
    except: return
    if equity < 50: return
    size_pct = 0.04 if MARKET_MODE == "BEAR" else 0.07
    amount = max(round(equity * size_pct, 2), 10)
    
    print(f"5. TEGIJA ({MARKET_MODE}): Ostame {symbol} ${amount:.2f} eest (Skoor {score}).")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=amount, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        update_position_metadata(symbol, atr)
        update_high_watermark(symbol, 0.000001)
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga ostul: {e}")

def run_cycle():
    print(f"========== TSÜKKEL START: {datetime.now()} ==========") 
    
    # Prindi konto seis alguses
    try:
        acct = trading_client.get_account()
        print(f"💰 KONTO: Equity ${float(acct.equity):,.2f} | Cash ${float(acct.cash):,.2f}")
    except: pass

    determine_market_mode()
    manage_existing_positions()
    
    if MARKET_MODE == "BEAR":
        print("   ⚠️ TURG ON LANGUSES. Otsin ainult sügavaid põhju (RSI < 30).")

    print(f"2. SKANNER: Laen KÕIK turu varad...")
    try:
        assets = trading_client.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE))
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ["USDT/USD", "USDC/USD", "DAI/USD", "WBTC/USD"]]
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except: return

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar or snap.daily_bar.open == 0: continue
        vol_usd = snap.daily_bar.volume * snap.daily_bar.close
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg), "vol_usd": vol_usd})
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    my_pos = [p.symbol for p in trading_client.get_all_positions()]
    ai_calls_made = 0
    
    print(f"   -> Leidsin {len(candidates)} münti.")

    for i, c in enumerate(candidates[:30]):
        s = c['symbol']
        alpaca_vol = c['vol_usd']
        
        if s in my_pos: continue
        if not is_cooled_down(s): continue
        if alpaca_vol < 10000: continue
             
        tech_score, atr, rsi = get_technical_analysis(s, alpaca_vol)
        
        if tech_score < 55:
             # print(f"      ❌ Nõrk tehnika ({tech_score}). SKIP.") # Liiga palju müra
             continue
             
        if ai_calls_made >= MAX_AI_CALLS:
            print("   ⚠️ AI limiit täis. Lõpetan tsükli.")
            break
            
        print(f"   🔥 LEID: {s} (Tech: {tech_score}). Analüüsin (Hybrid)...")
        ai_score = analyze_coin_ai(s)
        ai_calls_made += 1
        
        final_score = (ai_score * 0.4) + (tech_score * 0.6)
        print(f"      🏁 {s} LÕPPHINNE: {final_score:.1f}")

        if final_score > 75:
            print(f"   🚀 OSTMINE: {s}")
            trade(s, final_score, atr)
            break # Üks tehing tsükli kohta on turvaline

    print(f"========== TSÜKKEL LÕPP ==========")
    print("="*40 + "\n")

# --- KÄIVITUS ---
if __name__ == "__main__":
    try:
        run_cycle()
    except Exception as e:
        print(f"CRITICAL RUN ERROR: {e}")
        print(traceback.format_exc())