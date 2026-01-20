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

print("--- VIBE TRADER: v22.1 (AGGRESSIVE BEAR) ---")

# --- GLOBAL VARIABLES ---
MARKET_MODE = "NEUTRAL" 

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# STRATEEGIA KONSTANDID
MIN_VOLUME_USD = 10000     
MAX_AI_CALLS = 10          

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
        brain["positions"][symbol] = {
            "highest_price": 0, 
            "atr_at_entry": atr_value, 
            "is_risk_free": False,
            "entry_mode": MARKET_MODE
        }
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
    
    # Kui turg on karune, tahame kiiremini uuesti proovida, kui hind veel kukub
    cooldown_time = 6 
    
    if last_sold:
        if datetime.now() - datetime.fromtimestamp(last_sold) < timedelta(hours=cooldown_time):
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

def determine_market_mode():
    global MARKET_MODE
    print("🔍 Analüüsin turu režiimi (BTC)...")
    df = get_yahoo_data("BTC/USD", period="6mo", interval="1d")
    
    if df is None or len(df) < 50:
        print("   ⚠️ BTC andmed puuduvad. Jään NEUTRAL.")
        MARKET_MODE = "NEUTRAL"
        return
        
    current_price = df['close'].iloc[-1]
    sma50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
    
    if pd.isna(sma50): sma50 = current_price

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

    hourly_change = ((current_price - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
    
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    macd_diff = ta.trend.macd_diff(df['close']).iloc[-1]
    adx = ta.trend.adx(df['high'], df['low'], df['close'], window=14).iloc[-1]
    atr = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
    
    if pd.isna(rsi): return 0, 0, 0, 0, 0

    # --- DÜNAAMILINE SKOORIMINE ---
    score = 50
    
    if MARKET_MODE == "BULL":
        if rsi < 30: score += 30
        elif rsi < 55: score += 15 
        
        if macd_diff > 0: score += 10
        if adx > 25: score += 10

    elif MARKET_MODE == "BEAR":
        # AGRESSIIVSEM KARUTURU SKOORIMINE
        # Anname rohkem punkte madalale RSI-le, et ületada 75 lävendit
        if rsi < 25: score += 45     # Väga tugev ost
        elif rsi < 35: score += 25   # Tugev ost
        elif rsi < 40: score += 10   # Nõrk ost
        elif rsi > 45: score -= 50   # Keelatud tsoon
        
        # Volüüm on tähtis
        if final_vol_usd > 1000000: score += 10
        
        if macd_diff > 0: score += 15 # Pööre toimumas

    if final_vol_usd < 10000: score = 0

    if score >= 60:
        print(f"      📊 {symbol} ({MARKET_MODE}): RSI={rsi:.1f}, Vol=${final_vol_usd/1000:.0f}k. Skoor: {score}")
    
    return max(0, min(100, score)), hourly_change, atr, rsi, final_vol_usd

# --- 3. AI (NO MEMORY) ---

def get_cryptocompare_news(symbol):
    try:
        clean = symbol.split("/")[0]
        res = requests.get(f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={clean}", timeout=5)
        return [{'title': i.get('title'), 'body': i.get('body'), 'link': i.get('url')} for i in res.json().get('Data', [])[:3]]
    except: return []

def analyze_coin_ai(symbol):
    all_news = get_cryptocompare_news(symbol)
    news_text = ""
    if all_news:
        for n in all_news:
            news_text += f"PEALKIRI: {n['title']}\n"
    else: news_text = "Uudiseid pole."

    context = "Turg on languses. Otsime AINULT lühiajalist põrget (scalp)." if MARKET_MODE == "BEAR" else "Turg on tõusus. Otsime head sisenemist."

    prompt = f"Analüüsi {symbol}. {context} Uudised:\n{news_text}\nHinda 0-100. Ole realistlik. Vasta AINULT: SKOOR: X"
    try:
        res = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        match = re.search(r'SKOOR:\s*(\d+)', res.choices[0].message.content)
        score = int(match.group(1)) if match else 50
    except: score = 50

    print(f"      🤖 AI HINNE: {score}/100")
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
        time.sleep(1.0)
        
        entry_price = float(p.avg_entry_price)
        current_price = float(p.current_price)
        profit_pct = float(p.unrealized_plpc) * 100
        
        df = get_yahoo_data(symbol, period="5d", interval="1h")
        
        if df is None:
            # Hädaabi stop, kui andmeid pole ja hind kukub
            if current_price < entry_price * 0.93: 
                 print(f"   ⚠️ {symbol} PIME STOP! Hind kukkus -7%. Müün.")
                 close_position(symbol)
            continue

        current_rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
        
        pos_data = get_position_data(symbol)
        hw = pos_data.get("highest_price", 0)
        atr = pos_data.get("atr_at_entry", 0)
        is_risk_free = pos_data.get("is_risk_free", False)
        
        if hw == 0: hw = entry_price
        if atr == 0: atr = current_price * 0.05 
        
        if current_price > hw:
            update_high_watermark(symbol, current_price, current_rsi)
            hw = current_price
        
        # --- DÜNAAMILINE VÄLJUMINE ---
        if MARKET_MODE == "BEAR":
            # Karuturul võtame kasumi kiirelt (scalping)
            trailing_stop = hw - (1.5 * atr)
            breakeven_trigger = 1.0 # Juba 1% kasumis paneme stopi nulli
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
    
    size_pct = 0.04 if MARKET_MODE == "BEAR" else 0.07
    amount = round(equity * size_pct, 2)
    amount = max(amount, 10)
    
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
    print(f"========== TSÜKKEL START ==========") 
    
    determine_market_mode()
    manage_existing_positions()
    
    # Karuturul ei bloki täielikult, vaid nõuame kõrget kvaliteeti
    if MARKET_MODE == "BEAR":
        print("   ⚠️ TURG ON LANGUSES. Otsin ainult sügavaid põhju (RSI < 35).")

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
    
    # Karuturul lävend 75, Pulliturul 75 (aga skoorimine on erinev)
    MIN_SCORE_REQ = 75 
    
    print(f"   -> Leidsin {len(candidates)} münti.")

    for i, c in enumerate(candidates):
        s = c['symbol']
        clean = s.replace("/", "")
        alpaca_vol = c['vol_usd']
        
        if clean in my_pos: continue
        if not is_cooled_down(s): continue

        if alpaca_vol < 10000: continue
             
        time.sleep(1.5)
        print(f"   [{i+1}] Kontrollin: {s}...")
        
        tech_score, hourly_chg, atr, rsi, final_vol = get_technical_analysis(s, alpaca_vol)
        
        if tech_score == 0:
             print(f"      ❌ {s} - Andmed puuduvad. SKIP.")
             continue

        # Eelfilter: Kui tehniline pilt on nõrk, ära küsi AI-lt
        if tech_score < 55:
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

    if best_coin and best_final_score >= MIN_SCORE_REQ:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_final_score:.1f}) ---")
        trade(best_coin['symbol'], best_final_score, best_atr)
    else:
        print(f"--- TULEMUS: Parim {best_coin['symbol'] if best_coin else '-'} ei ületanud lävendit ({MIN_SCORE_REQ}).")
    
    print(f"========== TSÜKKEL LÕPP ==========")

if __name__ == "__main__":
    run_cycle()