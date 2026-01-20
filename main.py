import os
import sys
import time
import builtins
import re
import requests
import json
import hashlib
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

# --- 0. SEADISTUS ---
LOG_FILE = "bot.log"
BRAIN_FILE = "brain.json"

def print(*args, **kwargs):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kwargs['flush'] = True
    msg = " ".join(map(str, args))
    builtins.print(f"[{now}] {msg}", **kwargs)

load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key or not openai_key:
    print("VIGA: Võtmed puudu!")
    exit()

print("--- VIBE TRADER: v21.1 (REAL-TIME INTELLIGENCE) ---")

# --- STRATEEGIA ---
MIN_FINAL_SCORE = 80       # Kõrge lävend
COOL_DOWN_HOURS = 2        # Lühem jahutus, kuna me ei kasuta enam mälu
TRAILING_ACTIVATION = 3.0  
BREAKEVEN_TRIGGER = 1.5    
MIN_VOLUME_USD = 10000     
MAX_HOURLY_PUMP = 5.0      
MAX_AI_CALLS = 10          

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 1. MÄLU JA ABI ---

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

def update_position_metadata(symbol, atr_value):
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {"highest_price": 0, "atr_at_entry": atr_value, "is_risk_free": False}
    else:
        if "atr_at_entry" not in brain["positions"][symbol]:
            brain["positions"][symbol]["atr_at_entry"] = atr_value
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
    if last_sold:
        if datetime.now() - datetime.fromtimestamp(last_sold) < timedelta(hours=COOL_DOWN_HOURS):
            return False
    return True

def activate_cooldown(symbol):
    brain = load_brain()
    if "cool_down" not in brain: brain["cool_down"] = {}
    brain["cool_down"][symbol] = datetime.now().timestamp()
    if "positions" in brain and symbol in brain["positions"]:
        del brain["positions"][symbol]
    save_brain(brain)

# --- 2. ANDMETÖÖTLUS ---

def format_symbol_for_yahoo(symbol):
    s = symbol.replace("/", "")
    if "PEPE" in s: return "PEPE24478-USD"
    if "UNI" in s and "UNIVERSE" not in s: return "UNI7083-USD"
    if "GRT" in s: return "GRT6719-USD"
    if "SHIB" in s: return "SHIB-USD"
    if "WIF" in s: return "WIF-USD"
    if "BONK" in s: return "BONK-USD"
    if s.endswith("USD"): return s[:-3] + "-USD"
    return s + "-USD"

def get_yahoo_data(symbol, period="1mo", interval="1h"):
    try:
        y_symbol = format_symbol_for_yahoo(symbol)
        df = yf.download(y_symbol, period=period, interval=interval, progress=False, timeout=10)
        
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if 'close' not in df.columns: return None
        return df.dropna()
    except: return None

def check_market_health():
    """
    KONTROLLIB TURU ÜLDSEISUNDIT (BTC).
    """
    print("🔍 Tervisekontroll: BTC Trend...")
    df = get_yahoo_data("BTC/USD", period="6mo", interval="1d")
    
    if df is None or len(df) < 50:
        print("   ⚠️ BTC andmed puuduvad. Ettevaatusabinõuna: EI OSTA.")
        return False
        
    current_price = df['close'].iloc[-1]
    sma50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
    
    if pd.isna(sma50): sma50 = current_price

    dist_sma = ((current_price - sma50) / sma50) * 100
    print(f"   BTC: ${current_price:.0f} | SMA50: ${sma50:.0f} | Dist: {dist_sma:.2f}%")
    
    # Kui BTC on alla SMA50, siis on keelatud osta
    if current_price < sma50:
        print("   ⛔ TURG ON LANGUSES (BTC < SMA50). Ostmine blokeeritud.")
        return False
        
    return True

def get_technical_analysis(symbol, alpaca_volume_usd):
    df = get_yahoo_data(symbol, period="1mo", interval="1h")
    
    if df is None or len(df) < 30: 
        return 0, 0, 0, 0, 0
    
    current_price = df['close'].iloc[-1]
    
    yahoo_vol_usd = 0
    if 'volume' in df.columns:
        yahoo_vol_usd = df['volume'].iloc[-1] * current_price
    
    final_vol_usd = max(alpaca_volume_usd, yahoo_vol_usd)

    hourly_change = ((current_price - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
    
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    macd_diff = ta.trend.macd_diff(df['close']).iloc[-1]
    adx = ta.trend.adx(df['high'], df['low'], df['close'], window=14).iloc[-1]
    
    atr = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
    
    if pd.isna(rsi) or pd.isna(adx): return 0, 0, 0, 0, 0

    score = 50
    
    if rsi < 30: score += 25
    elif rsi < 40: score += 10
    elif rsi > 65: score -= 30 
    
    if macd_diff > 0: score += 15
    else: score -= 15 
    
    if adx > 25: score += 10
    else: score -= 5
    
    if final_vol_usd < MIN_VOLUME_USD: score = 0

    if score >= 50:
        macd_str = "POS" if macd_diff > 0 else "NEG"
        print(f"      📊 {symbol} TECH: RSI={rsi:.1f}, MACD={macd_str}, ADX={adx:.1f}. Skoor: {score}")
    
    return max(0, min(100, score)), hourly_change, atr, rsi, final_vol_usd

# --- 3. AI & UUDISED (NO MEMORY) ---

def get_cryptocompare_news(symbol):
    try:
        clean = symbol.split("/")[0]
        res = requests.get(f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={clean}", timeout=5)
        return [{'title': i.get('title'), 'body': i.get('body'), 'link': i.get('url')} for i in res.json().get('Data', [])[:3]]
    except: return []

def analyze_coin_ai(symbol):
    # Eemaldasime mälu kontrolli täielikult.
    # Iga kord teeme uue päringu, et saada värskeim hinnang.
    
    all_news = get_cryptocompare_news(symbol)
    
    news_text = ""
    if all_news:
        for n in all_news:
            news_text += f"PEALKIRI: {n['title']}\n"
    else: news_text = "Uudiseid pole."

    prompt = f"Analüüsi {symbol} lühiajalist (24h) potentsiaali. Turg on ebakindel. Ole kriitiline. Uudised:\n{news_text}\nHinda 0-100. Vasta AINULT: SKOOR: X"
    try:
        res = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        match = re.search(r'SKOOR:\s*(\d+)', res.choices[0].message.content)
        score = int(match.group(1)) if match else 50
    except: score = 50

    print(f"      🤖 AI HINNE (VÄRSKE): {score}/100")
    # Me ei salvesta enam mällu, sest me ei kasuta seda
    return score

# --- 4. HALDUS ---

def manage_existing_positions():
    print("1. PORTFELL: Risk-Free & Profit Lock...")
    try: positions = trading_client.get_all_positions()
    except: return

    if not positions:
        print("   -> Portfell on tühi.")
        return

    for p in positions:
        symbol = p.symbol
        time.sleep(2.0)
        
        entry_price = float(p.avg_entry_price)
        current_price = float(p.current_price)
        profit_pct = float(p.unrealized_plpc) * 100
        
        df = get_yahoo_data(symbol, period="5d", interval="1h")
        
        current_rsi = 50
        if df is not None:
             current_rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
             if pd.isna(current_rsi): current_rsi = 50
        
        pos_data = get_position_data(symbol)
        hw = pos_data.get("highest_price", 0)
        atr = pos_data.get("atr_at_entry", 0)
        is_risk_free = pos_data.get("is_risk_free", False)
        
        if hw == 0: hw = entry_price
        if atr == 0: atr = current_price * 0.05 
        
        if current_price > hw:
            update_high_watermark(symbol, current_price, current_rsi)
            hw = current_price
            
        atr_multiplier = 1.5 if current_rsi > 70 else 2.5
        trailing_stop = hw - (atr_multiplier * atr)
        breakeven_stop = entry_price * 1.01
        
        hard_stop = entry_price * 0.93 
        
        if profit_pct >= TRAILING_ACTIVATION:
            final_stop = trailing_stop
            stop_type = "TRAILING 🔥"
        elif profit_pct >= BREAKEVEN_TRIGGER or is_risk_free:
            final_stop = max(breakeven_stop, hard_stop)
            stop_type = "RISK-FREE 🛡️"
            if not is_risk_free: set_risk_free_status(symbol)
        else:
            final_stop = hard_stop
            stop_type = "HARD 🛑"
            
        dist_to_stop = ((current_price - final_stop) / current_price) * 100
        
        print(f"   -> {symbol}: {profit_pct:.2f}% (RSI:{current_rsi:.0f} | Stop: ${final_stop:.2f} | {stop_type} | Puhver: {dist_to_stop:.2f}%)")

        if current_price <= final_stop:
            print(f"      !!! STOP HIT ({stop_type})! Müün {symbol}...")
            close_position(symbol)

def close_position(symbol):
    try:
        trading_client.close_position(symbol)
        activate_cooldown(symbol)
        print(f"      TEHTUD! {symbol} müüdud.")
    except Exception as e: print(f"Viga: {e}")

def trade(symbol, score, atr):
    try: equity = float(trading_client.get_account().equity)
    except: return
    if equity < 50: return
    
    size_pct = 0.05
    amount = round(equity * size_pct, 2)
    amount = max(amount, 10)
    
    print(f"5. TEGIJA: Ostame {symbol} ${amount:.2f} eest (Skoor {score}).")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=amount, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        update_position_metadata(symbol, atr)
        update_high_watermark(symbol, 0.000001)
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga ostul: {e}")

def run_cycle():
    print(f"========== TSÜKKEL START ==========") 
    manage_existing_positions()
    
    market_is_safe = check_market_health()
    
    if not market_is_safe:
        print("   ⚠️ TURG ON OHTLIK. OSTMISELE SKIP.")
        print("========== TSÜKKEL LÕPP ==========")
        return 

    print(f"2. SKANNER: Laen KÕIK turu varad...")
    try:
        assets = trading_client.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE))
        ignore = ["USDT/USD", "USDC/USD", "DAI/USD", "WBTC/USD"]
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore]
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except: return

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar or snap.daily_bar.open == 0: continue
        vol_usd = snap.daily_bar.volume * snap.daily_bar.close
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg), "vol_usd": vol_usd})
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    my_pos = [p.symbol.replace("/", "").replace("-", "") for p in trading_client.get_all_positions()]
    best_coin = None
    best_final_score = -1
    best_atr = 0
    ai_calls_made = 0
    total_coins = len(candidates)
    
    print(f"   -> Leidsin {total_coins} münti. Alustan analüüsi (Top 10 AI)...")

    for i, c in enumerate(candidates):
        s = c['symbol']
        clean = s.replace("/", "")
        alpaca_vol = c['vol_usd']
        
        if clean in my_pos:
            print(f"   [{i+1}/{total_coins}] [SKIP] {s} - Juba olemas.")
            continue
        if not is_cooled_down(s):
            print(f"   [{i+1}/{total_coins}] [SKIP] {s} - Jahutusel.")
            continue

        if alpaca_vol < MIN_VOLUME_USD: 
             continue
             
        time.sleep(2.0)
        print(f"   [{i+1}/{total_coins}] Kontrollin: {s}...")
        
        tech_score, hourly_chg, atr, rsi, final_vol = get_technical_analysis(s, alpaca_vol)
        
        if tech_score == 0:
             print(f"      ❌ {s} - Andmed puuduvad. SKIP.")
             continue

        if final_vol < MIN_VOLUME_USD:
             print(f"      [SKIP] {s} - Maht ikkagi liiga väike (${final_vol/1000:.1f}k).")
             continue

        if hourly_chg > MAX_HOURLY_PUMP: 
             print(f"      ⛔ FOMO: Liiga suur pump ({hourly_chg:.1f}%).")
             continue
        if tech_score < 50: 
             print(f"      ❌ Nõrk tehnika ({tech_score}).")
             continue
        if ai_calls_made >= MAX_AI_CALLS:
            print("   ⚠️ AI limiit täis.")
            break
            
        print(f"   🔥 LEID: {s} on kuum (Tech: {tech_score}). Küsin AI-lt...")
        ai_score = analyze_coin_ai(s)
        ai_calls_made += 1
        
        final_score = (ai_score * 0.4) + (tech_score * 0.6)
        print(f"      🏁 {s} LÕPPHINNE: {final_score:.1f}")

        if final_score > best_final_score:
            best_final_score = final_score
            best_coin = c
            best_atr = atr

    if best_coin and best_final_score >= MIN_FINAL_SCORE:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_final_score:.1f}) ---")
        trade(best_coin['symbol'], best_final_score, best_atr)
    else:
        print(f"--- TULEMUS: Parim {best_coin['symbol'] if best_coin else '-'} ei ületanud lävendit.")
    
    print(f"========== TSÜKKEL LÕPP ==========")

if __name__ == "__main__":
    run_cycle()