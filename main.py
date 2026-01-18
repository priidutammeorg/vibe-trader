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

print("--- VIBE TRADER: v16.0 (FRESH BRAINS) ---")

# STRATEEGIA
MIN_FINAL_SCORE = 75       
COOL_DOWN_HOURS = 12       
TRAILING_ACTIVATION_ATR = 2.0 
MIN_VOLUME_USD = 100000    
MAX_HOURLY_PUMP = 6.0      
MAX_AI_CALLS = 10          # Analüüsime kuni 10 münti tsüklis

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 1. MÄLU JA ABI ---

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
    except:
        pass

def update_position_metadata(symbol, atr_value):
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {
            "highest_price": 0, 
            "atr_at_entry": atr_value 
        }
    else:
        brain["positions"][symbol]["atr_at_entry"] = atr_value
        
    save_brain(brain)

def update_high_watermark(symbol, current_price):
    brain = load_brain()
    if "positions" not in brain: brain["positions"] = {}
    
    if symbol not in brain["positions"]:
        brain["positions"][symbol] = {"highest_price": current_price, "atr_at_entry": current_price * 0.05}
    else:
        if current_price > brain["positions"][symbol]["highest_price"]:
            brain["positions"][symbol]["highest_price"] = current_price
            save_brain(brain)
            return True
    save_brain(brain)
    return False

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

# --- 2. ANDMETÖÖTLUS (YAHOO) ---

def get_yahoo_data(symbol, period="1mo", interval="1h"):
    try:
        y_symbol = symbol.replace("/", "-")
        df = yf.download(y_symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if 'close' not in df.columns: return None
        return df.dropna()
    except:
        return None

def check_btc_pulse():
    print("🔍 Tervisekontroll: BTC Pulss...")
    df = get_yahoo_data("BTC/USD", period="6mo", interval="1d")
    
    if df is None or len(df) < 50:
        print("   ⚠️ BTC andmed puuduvad. Jätkan ettevaatlikult.")
        return True
    
    current = df['close'].iloc[-1]
    sma50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
    if pd.isna(sma50): sma50 = current
    
    change = ((current - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
    
    print(f"   BTC: ${current:.0f} | SMA50: ${sma50:.0f} | 24h: {change:.2f}%")
    
    if current < (sma50 * 0.95) or change < -5.0:
        print("   ⛔ TURG ON OHTLIK. Ootan.")
        return False
    return True

def get_technical_analysis(symbol):
    df = get_yahoo_data(symbol, period="1mo", interval="1h")
    
    if df is None or len(df) < 30:
        return 50, 0, 0, 0 
    
    current_price = df['close'].iloc[-1]
    last_24h = df.tail(24)
    volume_24h = (last_24h['volume'] * last_24h['close']).sum()
    
    hourly_change = ((current_price - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
    
    # --- INDIKAATORID ---
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    if pd.isna(rsi): rsi = 50
    
    macd_diff = ta.trend.macd_diff(df['close']).iloc[-1]
    
    sma200 = ta.trend.sma_indicator(df['close'], window=200).iloc[-1]
    if pd.isna(sma200): sma200 = current_price

    adx = ta.trend.adx(df['high'], df['low'], df['close'], window=14).iloc[-1]
    if pd.isna(adx): adx = 20

    bb_high = ta.volatility.bollinger_hband(df['close']).iloc[-1]
    bb_low = ta.volatility.bollinger_lband(df['close']).iloc[-1]
    
    atr = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
    if pd.isna(atr): atr = current_price * 0.05

    # --- SKOORIMINE ---
    score = 50
    
    if rsi < 30: score += 25
    elif rsi < 45: score += 10
    elif rsi > 70: score -= 30
    
    if macd_diff > 0: score += 15
    else: score -= 10
    
    if current_price > sma200: score += 10
    
    if adx > 25: score += 5
    elif adx < 15: score -= 5 
    
    if current_price <= (bb_low * 1.01): score += 15 
    elif current_price >= (bb_high * 0.99): score -= 15 

    if score >= 45:
        macd_str = "POS" if macd_diff > 0 else "NEG"
        print(f"      📊 {symbol} TECH: RSI={rsi:.1f}, MACD={macd_str}, ADX={adx:.1f}. Vol=${volume_24h/1000:.0f}k. Skoor: {score}")
    
    return max(0, min(100, score)), volume_24h, hourly_change, atr

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
    
    # --- MÄLU KESTVUS: 2 TUNDI (Värskem info) ---
    if mem and mem['hash'] == curr_hash and (datetime.now().timestamp() - mem['ts']) < (3600 * 2):
        print(f"      🧠 {symbol} MÄLU: Kasutan vana AI skoori: {mem['score']}")
        return mem['score']

    news_text = ""
    if all_news:
        for n in all_news:
            print(f"      > UUDIS: {n['title']} ||| {n['link']}")
            news_text += f"PEALKIRI: {n['title']}\nSISU: {n['body']}\n---\n"
    else: news_text = "Uudiseid pole."

    prompt = f"""
    Analüüsi krüptoraha {symbol} 24h potentsiaali.
    Uudised:
    {news_text}
    Hinda 0-100.
    85-100: Väga tugev signaal (Partnerlus, Upgrade, Listing).
    50-84: Positiivne.
    0-49: Neutraalne/Negatiivne.
    Vasta AINULT: SKOOR: X
    """
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

# --- 4. HALDUS ---

def manage_existing_positions():
    print("1. PORTFELL: Dünaamiline ATR haldus...")
    try: positions = trading_client.get_all_positions()
    except: return

    if not positions:
        print("   -> Portfell on tühi.")
        return

    for p in positions:
        symbol = p.symbol
        entry_price = float(p.avg_entry_price)
        current_price = float(p.current_price)
        profit_pct = float(p.unrealized_plpc) * 100
        
        pos_data = get_position_data(symbol)
        hw = pos_data.get("highest_price", 0)
        if hw == 0: hw = entry_price
        
        atr = pos_data.get("atr_at_entry", 0)
        if atr == 0: atr = current_price * 0.05 
        
        if current_price > hw:
            update_high_watermark(symbol, current_price)
            hw = current_price
            
        stop_price = hw - (2.0 * atr)
        hard_stop = entry_price * 0.95
        final_stop = max(stop_price, hard_stop)
        
        dist_to_stop = ((current_price - final_stop) / current_price) * 100
        
        print(f"   -> {symbol}: {profit_pct:.2f}% (Hind: ${current_price:.2f} | Stop: ${final_stop:.2f} | Puhver: {dist_to_stop:.2f}%)")

        if current_price <= final_stop:
            print(f"      !!! ATR STOP HIT! Müün {symbol}...")
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
    
    if score >= 90: size_pct = 0.08
    elif score >= 80: size_pct = 0.06
    else: size_pct = 0.04
    
    amount = equity * size_pct
    amount = max(amount, 10)
    amount = round(amount, 2)
    
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
    if not check_btc_pulse(): return
    manage_existing_positions()
    
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
        chg = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    my_pos = [p.symbol.replace("/", "").replace("-", "") for p in trading_client.get_all_positions()]
    best_coin = None
    best_final_score = -1
    best_atr = 0
    ai_calls_made = 0
    
    total_coins = len(candidates)
    print(f"   -> Leidsin {total_coins} münti. Alustan Hedge Fund analüüsi...")

    for i, c in enumerate(candidates):
        s = c['symbol']
        clean = s.replace("/", "")
        
        if clean in my_pos or not is_cooled_down(s): continue

        time.sleep(0.5) 
        
        print(f"   [{i+1}/{total_coins}] Kontrollin: {s}...")

        tech_score, volume, hourly_chg, atr = get_technical_analysis(s)
        
        if volume < MIN_VOLUME_USD: continue 
        if hourly_chg > MAX_HOURLY_PUMP: continue
        if tech_score < 45: continue 

        if ai_calls_made >= MAX_AI_CALLS:
            print("   ⚠️ AI limiit täis.")
            break
            
        print(f"   🔥 LEID: {s} on kuum (Tech: {tech_score}). Küsin AI-lt...")
        ai_score = analyze_coin_ai(s)
        ai_calls_made += 1
        
        final_score = (ai_score * 0.5) + (tech_score * 0.5)
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

if __name__ == "__main__":
    run_cycle()