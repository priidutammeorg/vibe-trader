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
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest, StopLossRequest, TakeProfitRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from openai import OpenAI

# --- 0. SEADISTUS ---
LOG_FILE = "bot.log"
BRAIN_FILE = "brain.json"

def print(*args, **kwargs):
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    kwargs['flush'] = True
    builtins.print(f"{now}", *args, **kwargs)

load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key or not openai_key:
    print("VIGA: Võtmed puudu!")
    exit()

print("--- VIBE TRADER: v10.0 (PROFESSIONAL) ---")

# STRATEEGIA
MIN_FINAL_SCORE = 70
COOL_DOWN_HOURS = 12
HARD_STOP_LOSS_PCT = -5.0  # Algsne kaitse
TRAILING_ACTIVATION = 5.0  # Kui kasum > 5%, hakka jälitama
TRAILING_DISTANCE = 2.0    # Jälita hinda 2% kauguselt
MIN_VOLUME_USD = 500000    # Väldi münte, mille käive on alla 500k

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
        with open(BRAIN_FILE, 'w') as f: json.dump(brain_data, f, indent=4)
    except: pass

def update_high_watermark(symbol, current_price):
    """Salvestab positsiooni kõrgeima hinna Trailing Stopi jaoks"""
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    
    # Kui pole varem salvestatud, alusta praegusest
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {"highest_price": current_price}
    else:
        # Uuenda ainult siis, kui hind on kõrgem
        if current_price > brain["positions"][symbol]["highest_price"]:
            brain["positions"][symbol]["highest_price"] = current_price
            save_brain(brain)
            return True # Uus tipp!
    save_brain(brain)
    return False

def get_high_watermark(symbol):
    brain = load_brain()
    return brain.get("positions", {}).get(symbol, {}).get("highest_price", 0)

def is_cooled_down(symbol):
    brain = load_brain()
    last_sold = brain.get("cool_down", {}).get(symbol)
    if last_sold:
        if datetime.now() - datetime.fromtimestamp(last_sold) < timedelta(hours=COOL_DOWN_HOURS):
            print(f"   ❄️ {symbol} on jahutusel. Skip.")
            return False
    return True

def activate_cooldown(symbol):
    brain = load_brain()
    if "cool_down" not in brain: brain["cool_down"] = {}
    brain["cool_down"][symbol] = datetime.now().timestamp()
    # Kustutame positsiooni info mälust
    if "positions" in brain and symbol in brain["positions"]:
        del brain["positions"][symbol]
    save_brain(brain)

# --- 2. TURU TERVIS ---

def get_market_data(symbol, timeframe=TimeFrame.Hour, limit=200):
    try:
        req = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=timeframe, limit=limit)
        return data_client.get_crypto_bars(req).df
    except: return None

def check_btc_pulse():
    print("🔍 Tervisekontroll: BTC Pulss...")
    df = get_market_data("BTC/USD", TimeFrame.Day, 60)
    if df is None or df.empty: return True
    
    current = df['close'].iloc[-1]
    sma50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
    change = ((current - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
    
    print(f"   BTC: ${current:.0f} | SMA50: ${sma50:.0f} | 24h: {change:.2f}%")
    
    if current < (sma50 * 0.96) or change < -4.5:
        print("   ⛔ TURG ON OHTLIK. Ootan paremaid aegu.")
        return False
    return True

def get_technical_analysis(symbol):
    df = get_market_data(symbol, TimeFrame.Hour, 100)
    if df is None or df.empty: return 50, 0 # Score, Volume
    
    # 1. Volume Check
    volume_24h = (df['volume'] * df['close']).sum() / (len(df)/24) # Approx daily val
    
    # 2. RSI
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    
    # 3. SMA Trend
    sma200 = ta.trend.sma_indicator(df['close'], window=200).iloc[-1] if len(df) >= 200 else 0
    price = df['close'].iloc[-1]

    score = 50
    if rsi < 30: score += 40
    elif rsi < 40: score += 20
    elif rsi > 75: score -= 40
    elif rsi > 65: score -= 20
    
    if sma200 > 0 and price > sma200: score += 10

    print(f"      📊 TECH: RSI={rsi:.1f}, Hind>{'SMA' if price>sma200 else 'ALL'}. Vol=${volume_24h/1000:.0f}k")
    return max(0, min(100, score)), volume_24h

# --- 3. AI & UUDISED ---

def get_news_hash(news_items):
    if not news_items: return "no_news"
    return hashlib.md5("".join([n['title'] for n in news_items]).encode('utf-8')).hexdigest()

def get_cryptocompare_news(symbol):
    try:
        clean = symbol.split("/")[0]
        res = requests.get(f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={clean}", timeout=5)
        return [{'title': i.get('title'), 'body': i.get('body'), 'link': i.get('url')} for i in res.json().get('Data', [])[:3]]
    except: return []

def analyze_coin_ai(symbol):
    all_news = get_cryptocompare_news(symbol)
    curr_hash = get_news_hash(all_news)
    brain = load_brain()
    
    mem = brain.get("ai_memory", {}).get(symbol)
    if mem and mem['hash'] == curr_hash and (datetime.now().timestamp() - mem['ts']) < (3600 * 6):
        print(f"      🧠 MÄLU: Vana AI skoor: {mem['score']}")
        return mem['score']

    news_text = ""
    if all_news:
        for n in all_news:
            print(f"      > UUDIS: {n['title']} ||| {n['link']}")
            news_text += f"PEALKIRI: {n['title']}\nSISU: {n['body']}\n---\n"
    else: news_text = "Uudiseid pole."

    prompt = f"Analüüsi {symbol}. Uudised:\n{news_text}\nHinda ostupotentsiaali (0-100). Vasta: SKOOR: X"
    try:
        res = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        match = re.search(r'SKOOR:\s*(\d+)', res.choices[0].message.content)
        score = int(match.group(1)) if match else 50
    except: score = 50

    print(f"      🤖 AI HINNE: {score}/100")
    
    if "ai_memory" not in brain: brain["ai_memory"] = {}
    brain["ai_memory"][symbol] = {"ts": datetime.now().timestamp(), "hash": curr_hash, "score": score}
    save_brain(brain)
    return score

# --- 4. HALDUS (TRAILING STOP) ---

def manage_existing_positions():
    print("1. PORTFELL: Trailing Stop loogika...")
    try:
        positions = trading_client.get_all_positions()
    except: return

    if not positions:
        print("   -> Portfell on tühi.")
        return

    for p in positions:
        symbol = p.symbol
        entry_price = float(p.avg_entry_price)
        current_price = float(p.current_price)
        profit_pct = float(p.unrealized_plpc) * 100
        
        # 1. Uuenda "High Watermark" (Tipphinda)
        # Kui mälu on tühi, alusta entry hinnast
        hw = get_high_watermark(symbol)
        if hw == 0: hw = entry_price
        
        if current_price > hw:
            update_high_watermark(symbol, current_price)
            hw = current_price # Uus tipp
        
        # 2. Arvuta Trailing Stop tase
        # Kui kasum > 5%, siis stop on tipust 2% allpool
        # Kui kasum < 5%, siis stop on fikseeritud -5% entryst (Hard Stop)
        
        if profit_pct >= TRAILING_ACTIVATION:
            stop_price = hw * (1 - (TRAILING_DISTANCE / 100))
            stop_type = "TRAILING 🎢"
        else:
            stop_price = entry_price * (1 + (HARD_STOP_LOSS_PCT / 100))
            stop_type = "HARD 🛡️"

        print(f"   -> {symbol}: {profit_pct:.2f}% (Hind: ${current_price:.2f} | Tipp: ${hw:.2f} | Stop: ${stop_price:.2f} {stop_type})")

        # 3. Kontrolli müüki
        if current_price <= stop_price:
            print(f"      !!! STOP HIT ({stop_type})! Müün {symbol}...")
            close_position(symbol)

def close_position(symbol):
    try:
        trading_client.close_position(symbol)
        activate_cooldown(symbol)
        print(f"      TEHTUD! {symbol} müüdud.")
    except Exception as e: print(f"Viga: {e}")

def trade(symbol, score):
    try:
        equity = float(trading_client.get_account().equity)
    except: return

    if equity < 50: return
    
    # SMART SIZING (POKER PLAYER)
    if score >= 90: size_pct = 0.08   # 8%
    elif score >= 80: size_pct = 0.06 # 6%
    else: size_pct = 0.04             # 4%
    
    amount = equity * size_pct
    amount = max(amount, 10)
    
    print(f"5. TEGIJA: Ostame {symbol} ${amount:.2f} eest (Skoor {score} -> {size_pct*100}% portfellist).")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=amount, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        update_high_watermark(symbol, 0.000001) # Init memory
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga ostul: {e}")

def run_cycle():
    if not check_btc_pulse(): return
    manage_existing_positions()
    
    print("2. SKANNER: Otsin turu liikujaid...")
    try:
        assets = trading_client.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE))
        ignore = ["USDT/USD", "USDC/USD", "DAI/USD", "WBTC/USD"]
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore]
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except: return

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar or snap.daily_bar.open == 0: continue
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    my_pos = [p.symbol.replace("/", "").replace("-", "") for p in trading_client.get_all_positions()]
    best_coin = None
    best_final_score = -1

    print("3. ANALÜÜS (AI + TECH + VOLUME)...")
    for c in candidates[:6]:
        s = c['symbol']
        clean = s.replace("/", "")
        
        if clean in my_pos: 
            print(f"   -> {s} olemas. Skip.")
            continue
        
        if not is_cooled_down(s): continue

        print(f"   -> Analüüsin: {s}...")
        
        # A. Tehniline + Volume
        tech_score, volume = get_technical_analysis(s)
        
        # Likviidsuskontroll (Anti-Scam)
        if volume < MIN_VOLUME_USD:
            print(f"      ❌ Liiga väike maht (${volume/1000:.0f}k). Riskantne.")
            continue

        if tech_score < 30:
            print(f"      ❌ Tehniliselt nõrk ({tech_score}). Skip.")
            continue

        # B. AI
        ai_score = analyze_coin_ai(s)
        
        # C. Lõpphinne
        final_score = (ai_score * 0.6) + (tech_score * 0.4)
        print(f"      🏁 LÕPPHINNE: {final_score:.1f}")

        if final_score > best_final_score:
            best_final_score = final_score
            best_coin = c

    if best_coin and best_final_score >= MIN_FINAL_SCORE:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_final_score:.1f}) ---")
        trade(best_coin['symbol'], best_final_score)
    else:
        print(f"--- TULEMUS: Parim {best_coin['symbol'] if best_coin else '-'} ei ületanud lävendit.")

if __name__ == "__main__":
    run_cycle()