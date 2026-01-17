import os
import sys
import time
import builtins
import re
import requests
import json
import hashlib
from datetime import datetime, timedelta
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI

# --- 0. SEADISTUS JA MÄLU ---
LOG_FILE = "bot.log"
BRAIN_FILE = "brain.json" # Siia salvestame mälu

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

print("--- VIBE TRADER: v8.0 (BRAIN EDITION) ---")

TAKE_PROFIT_PCT = 10.0
STOP_LOSS_PCT = -5.0
MIN_SCORE_TO_BUY = 75
MEMORY_HOURS = 6 # Kui kaua me vana analüüsi mäletame

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 1. MÄLU FUNKTSIOONID (UUS!) ---

def load_brain():
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_brain(brain_data):
    try:
        with open(BRAIN_FILE, 'w') as f:
            json.dump(brain_data, f, indent=4)
    except Exception as e:
        print(f"Viga mälu salvestamisel: {e}")

def get_news_hash(news_items):
    """Teeb uudistest unikaalse 'sõrmejälje'. Kui uudised muutuvad, muutub ka hash."""
    if not news_items: return "no_news"
    # Ühendame pealkirjad kokku ja teeme hash-i
    combined = "".join([n['title'] for n in news_items])
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

# --- 2. ABIFUNKTSIOONID ---

def get_clean_positions_list():
    try:
        positions = trading_client.get_all_positions()
        return [p.symbol.replace("/", "").replace("-", "") for p in positions]
    except:
        return []

def get_cryptocompare_news(symbol):
    clean_sym = symbol.split("/")[0]
    url = "https://min-api.cryptocompare.com/data/v2/news/"
    params = {"lang": "EN", "categories": clean_sym}
    try:
        res = requests.get(url, params=params, headers={'User-Agent': 'VibeTrader/1.0'}, timeout=10)
        if res.status_code != 200: return []
        data = res.json()
        news_items = []
        for item in data.get('Data', [])[:3]:
            news_items.append({
                'title': item.get('title', ''),
                'body': item.get('body', ''),
                'link': item.get('url', ''),
                'source': item.get('source', 'CryptoCompare')
            })
        return news_items
    except:
        return []

# --- 3. TUUMIK ---

def manage_existing_positions():
    print("1. PORTFELL: Kontrollin seisu...")
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

        if profit_pct >= TAKE_PROFIT_PCT:
            print(f"      $$$ KASUM (+{profit_pct:.2f}%)! Müün {symbol}...")
            close_position(symbol)
        elif profit_pct <= STOP_LOSS_PCT:
            print(f"      !!! KAHJUM ({profit_pct:.2f}%)! Stop-loss {symbol}...")
            close_position(symbol)

def close_position(symbol):
    try:
        trading_client.close_position(symbol)
        print(f"      TEHTUD! {symbol} müüdud.")
    except: pass

def get_candidates():
    print("2. SKANNER: Otsin turu liikujaid...")
    try:
        search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        assets = trading_client.get_all_assets(search_params)
        ignore = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD", "WBTC/USD"]
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore]
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except: return []

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar or snap.daily_bar.open == 0: continue
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:5]

def analyze_coin(symbol):
    print(f"   -> Analüüsin: {symbol}...")
    
    # 1. Hangi uudised
    all_news = []
    cc_news = get_cryptocompare_news(symbol)
    if cc_news: all_news.extend(cc_news)
    
    if len(all_news) < 2:
        try:
            ticker = yf.Ticker(symbol.replace("/", "-"))
            for n in ticker.news[:2]:
                all_news.append({'title': n.get('title'), 'body': '', 'link': n.get('link'), 'source': 'Yahoo'})
        except: pass

    # 2. Arvuta uudiste hash (sõrmejälg)
    current_news_hash = get_news_hash(all_news)
    
    # 3. KONTROLLI MÄLU (BRAIN)
    brain = load_brain()
    memory = brain.get(symbol)
    
    # Kui mälu on olemas
    if memory:
        last_time = datetime.fromtimestamp(memory['timestamp'])
        # Kas uudised on samad JA analüüs on piisavalt värske?
        if memory['news_hash'] == current_news_hash and (datetime.now() - last_time) < timedelta(hours=MEMORY_HOURS):
            print(f"      🧠 MÄLU: Kasutan vana analüüsi ({last_time.strftime('%H:%M')}). Säästame token-eid.")
            print(f"      > Eelmised uudised on ikka jõus.")
            # Prindime ikka lingid logisse, et dashboard oleks ilus
            for n in all_news:
                print(f"      > UUDIS: {n.get('title')} ||| {n.get('link')}")
            
            print(f"      AI HINNE: {memory['score']}/100 (Cached)")
            return memory['score']

    # --- KUI MÄLU EI AIDANUD, KÜSIME AI-LT ---
    
    news_text = ""
    if all_news:
        for n in all_news:
            title = n.get('title', 'N/A')
            print(f"      > UUDIS: {title} ||| {n.get('link')}")
            news_text += f"PEALKIRI: {title}\nSISU: {n.get('body')}\n---\n"
    else:
        print("      Uudiseid pole (Neutraalne).")
        news_text = "Uudiseid ei leitud."

    prompt = f"""
    Analüüsi krüptovaluutat {symbol}.
    Uudised:
    {news_text}
    
    Hinda ostupotentsiaali (0-100).
    Vasta AINULT formaadis: SKOOR: X
    """
    
    score = 0
    try:
        res = ai_client.chat.completions.create(