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
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
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

print("--- VIBE TRADER: v9.0 (PRO EDITION) ---")

# --- STRATEEGIA PARAMEETRID ---
TAKE_PROFIT_PCT = 10.0       # Võtame kasumit
STOP_LOSS_PCT = -5.0         # Kaitseme kahjumi eest
MIN_FINAL_SCORE = 70         # Lävend ostmiseks (AI + Tehniline)
COOL_DOWN_HOURS = 12         # Kaua ootame pärast müüki
POSITION_SIZE_PCT = 0.05     # Panustame 5% portfelli väärtusest per tehing

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 1. MÄLU JA JAHUTUS ---

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

def is_cooled_down(symbol):
    """Kontrollib, kas münt on 'jahutusperioodil'"""
    brain = load_brain()
    cooldowns = brain.get("cool_down", {})
    last_sold = cooldowns.get(symbol)
    
    if last_sold:
        sold_time = datetime.fromtimestamp(last_sold)
        if datetime.now() - sold_time < timedelta(hours=COOL_DOWN_HOURS):
            print(f"   ❄️ {symbol} on jahutusel (müüdud {sold_time.strftime('%H:%M')}). Skip.")
            return False # Ei ole jahtunud (True = on jahtunud/vaba, False = blokeeritud)
    return True # On vaba kauplemiseks

def activate_cooldown(symbol):
    """Paneb mündi musta nimekirja"""
    brain = load_brain()
    if "cool_down" not in brain: brain["cool_down"] = {}
    brain["cool_down"][symbol] = datetime.now().timestamp()
    save_brain(brain)

# --- 2. TEHNILINE ANALÜÜS (UUS!) ---

def get_market_data(symbol, timeframe=TimeFrame.Hour, limit=200):
    """Tõmbab Alpaca kaudu ajaloolised andmed"""
    try:
        req = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=timeframe, limit=limit)
        bars = data_client.get_crypto_bars(req)
        df = bars.df
        return df
    except:
        return None

def check_btc_pulse():
    """Kontrollib turu tervist (Bitcoin). Kui BTC on haige, siis me ei kauple."""
    print("🔍 Tervisekontroll: Mõõdan BTC pulssi...")
    df = get_market_data("BTC/USD", TimeFrame.Day, 100)
    
    if df is None or df.empty:
        print("   ⚠️ Ei saanud BTC andmeid. Jätkan ettevaatlikult.")
        return True # Eeldame, et on ok, kui andmeid pole

    # Arvutame 50 päeva keskmise (SMA50)
    df['sma50'] = ta.trend.sma_indicator(df['close'], window=50)
    current_price = df['close'].iloc[-1]
    sma50 = df['sma50'].iloc[-1]
    
    # Arvutame tänase muutuse
    daily_change = ((current_price - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100

    print(f"   BTC Hind: ${current_price:.0f} | SMA50: ${sma50:.0f} | Muutus: {daily_change:.2f}%")

    # REEGEL: Kui BTC on kõvasti alla keskmise VÕI kukkunud täna üle 4%
    if current_price < (sma50 * 0.95) or daily_change < -4.0:
        print("   ⛔ TURG ON OHTLIK (BTC Pulss nõrk). Panen poe kinni.")
        return False
    
    print("   ✅ Turg on stabiilne.")
    return True

def get_technical_score(symbol):
    """Arvutab tehnilise skoori (RSI + Trend)"""
    df = get_market_data(symbol, TimeFrame.Hour, 100)
    if df is None or df.empty: return 50 # Neutraalne kui andmeid pole

    # RSI (Relative Strength Index)
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    
    # SMA (Moving Average) - Kas hind on üle 200 tunni keskmise?
    sma200 = ta.trend.sma_indicator(df['close'], window=200).iloc[-1] if len(df) >= 200 else 0
    price = df['close'].iloc[-1]

    score = 50 # Baas

    # RSI Loogika
    if rsi < 30: score += 40      # Väga odav (Osta!)
    elif rsi < 40: score += 20    # Odav
    elif rsi > 70: score -= 40    # Väga kallis (Ära osta!)
    elif rsi > 60: score -= 20    # Kallis

    # Trendi loogika
    if sma200 > 0 and price > sma200:
        score += 10 # Tõusutrend

    score = max(0, min(100, score)) # Hoiame 0-100 piires
    
    print(f"      📊 TEHNILINE: RSI={rsi:.1f}, Hind>{'SMA200' if price>sma200 else 'ALL'}. Skoor: {score}")
    return score

# --- 3. UUDISED JA AI (Vana hea + update) ---

def get_news_hash(news_items):
    if not news_items: return "no_news"
    combined = "".join([n['title'] for n in news_items])
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def get_cryptocompare_news(symbol):
    clean_sym = symbol.split("/")[0]
    try:
        res = requests.get(f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={clean_sym}", timeout=5)
        data = res.json()
        return [{'title': i.get('title'), 'body': i.get('body'), 'link': i.get('url')} for i in data.get('Data', [])[:3]]
    except: return []

def analyze_coin_ai(symbol):
    # 1. Uudised
    all_news = get_cryptocompare_news(symbol)
    
    # Mälu kontroll (Säästame raha)
    current_hash = get_news_hash(all_news)
    brain = load_brain()
    memory = brain.get(symbol)
    if memory and memory['news_hash'] == current_hash and (datetime.now() - datetime.fromtimestamp(memory['timestamp'])) < timedelta(hours=6):
        print(f"      🧠 MÄLU: Kasutan vana AI skoori: {memory['score']}")
        return memory['score']

    # AI Analüüs
    news_text = ""
    if all_news:
        for n in all_news:
            print(f"      > UUDIS: {n['title']} ||| {n['link']}")
            news_text += f"PEALKIRI: {n['title']}\nSISU: {n['body']}\n---\n"
    else:
        news_text = "Uudiseid pole."

    prompt = f"Analüüsi {symbol}. Uudised:\n{news_text}\nHinda ostupotentsiaali (0-100). Vasta: SKOOR: X"
    
    try:
        res = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        match = re.search(r'SKOOR:\s*(\d+)', res.choices[0].message.content)
        ai_score = int(match.group(1)) if match else 50
    except: ai_score = 50

    print(f"      🤖 AI HINNE: {ai_score}/100")
    
    # Salvestame mällu
    brain[symbol] = {"timestamp": datetime.now().timestamp(), "news_hash": current_hash, "score": ai_score}
    save_brain(brain)
    
    return ai_score

# --- 4. PEAMINE LOOGIKA ---

def manage_existing_positions():
    print("1. PORTFELL: Halduse ja stopppide kontroll...")
    try:
        positions = trading_client.get_all_positions()
    except: return

    if not positions:
        print("   -> Portfell on tühi.")
        return

    for p in positions:
        symbol = p.symbol
        profit_pct = float(p.unrealized_plpc) * 100
        print(f"   -> {symbol}: {profit_pct:.2f}%")

        # Kasumivõtt või Stop-Loss
        if profit_pct >= TAKE_PROFIT_PCT:
            print(f"      $$$ KASUM (+{profit_pct:.2f}%)! Müün {symbol}...")
            close_position(symbol)
        elif profit_pct <= STOP_LOSS_PCT:
            print(f"      !!! KAHJUM ({profit_pct:.2f}%)! Stop-loss {symbol}...")
            close_position(symbol)

def close_position(symbol):
    try:
        trading_client.close_position(symbol)
        activate_cooldown(symbol) # PANEB JAHUTUSELE!
        print(f"      TEHTUD! {symbol} müüdud ja pandud 12h jahutusele.")
    except Exception as e: print(f"Viga: {e}")

def get_account_cash():
    try:
        acc = trading_client.get_account()
        return float(acc.equity) # Kasutame equity (koguväärtust), et arvutada 5%
    except: return 0

def trade(symbol):
    equity = get_account_cash()
    if equity < 50: return # Liiga vähe raha
    
    amount = equity * POSITION_SIZE_PCT # 5% portfellist
    amount = max(amount, 10) # Minimaalselt $10
    
    print(f"5. TEGIJA: Ostame {symbol} ${amount:.2f} eest (Riskihaldus).")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=amount, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga ostul: {e}")

def run_cycle():
    # 1. KONTROLLI BITCOINI PULSSI
    if not check_btc_pulse():
        return # Kui BTC on katki, lõpetame tsükli kohe

    manage_existing_positions()
    
    # 2. LEIA KANDIDAADID
    print("2. SKANNER: Otsin turu liikujaid...")
    try:
        assets = trading_client.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE))
        ignore = ["USDT/USD", "USDC/USD", "DAI/USD", "WBTC/USD"]
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore]
        # Võtame snapshotid
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except: return

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar or snap.daily_bar.open == 0: continue
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    # 3. ANALÜÜSI PARIMAID
    my_pos = [p.symbol.replace("/", "").replace("-", "") for p in trading_client.get_all_positions()]
    
    best_coin = None
    best_final_score = -1

    print("3. ANALÜÜS (AI + TEHNILINE)...")
    for c in candidates[:5]: # Vaatame top 5
        s = c['symbol']
        clean = s.replace("/", "")
        
        # Filtrid
        if clean in my_pos: 
            print(f"   -> {s} olemas. Skip.")
            continue
        
        if not is_cooled_down(s): # Jahutuse kontroll
            continue

        print(f"   -> Analüüsin: {s}...")
        
        # A. Tehniline skoor (Kiire ja tasuta)
        tech_score = get_technical_score(s)
        
        # Kui tehniliselt on väga halb (nt RSI 90), siis ära raiska raha AI peale
        if tech_score < 30:
            print(f"      ❌ Tehniliselt nõrk (Skoor {tech_score}). Ei küsi AI-lt.")
            continue

        # B. AI skoor (Uudised)
        ai_score = analyze_coin_ai(s)
        
        # C. KOMBINEERITUD SKOOR (60% AI, 40% Tehniline)
        final_score = (ai_score * 0.6) + (tech_score * 0.4)
        print(f"      🏁 LÕPPHINNE: {final_score:.1f} (AI: {ai_score}, Tech: {tech_score})")

        if final_score > best_final_score:
            best_final_score = final_score
            best_coin = c

    # 4. OTSUS
    if best_coin and best_final_score >= MIN_FINAL_SCORE:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_final_score:.1f}) ---")
        trade(best_coin['symbol'])
    else:
        w = best_coin['symbol'] if best_coin else "-"
        print(f"--- TULEMUS: Parim {w} ({best_final_score:.1f}p). Ei ületanud lävendit ({MIN_FINAL_SCORE}).")

if __name__ == "__main__":
    run_cycle()