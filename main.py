import os
import sys
import time
import builtins
import re
import requests
from datetime import datetime
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI

# --- 0. LOGIMINE ---
def print(*args, **kwargs):
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    kwargs['flush'] = True
    builtins.print(f"{now}", *args, **kwargs)

# --- 1. SEADISTUS ---
load_dotenv()

api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key or not openai_key:
    print("VIGA: Põhivõtmed puudu!")
    exit()

print("--- VIBE TRADER: v7.1 (DEEP READ) ---")

TAKE_PROFIT_PCT = 10.0
STOP_LOSS_PCT = -5.0
MIN_SCORE_TO_BUY = 75

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. ABIFUNKTSIOONID ---

def get_clean_positions_list():
    try:
        positions = trading_client.get_all_positions()
        return [p.symbol.replace("/", "").replace("-", "") for p in positions]
    except:
        return []

def get_cryptocompare_news(symbol):
    """Küsib CryptoCompare API-st uudiseid koos sisuga"""
    
    clean_sym = symbol.split("/")[0]
    url = "https://min-api.cryptocompare.com/data/v2/news/"
    
    params = {
        "lang": "EN",
        "categories": clean_sym
    }
    
    try:
        headers = {'User-Agent': 'VibeTrader/1.0'}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        
        if res.status_code != 200:
            print(f"      CryptoCompare VIGA {res.status_code}")
            return []

        data = res.json()
        results = data.get('Data', [])
        
        news_items = []
        for item in results[:3]:
            # --- MUUDATUS: Loeme ka sisu (body) ---
            news_items.append({
                'title': item.get('title', ''),
                'body': item.get('body', ''), # <--- SIIN ON SISU
                'link': item.get('url', ''),
                'source': item.get('source', 'CryptoCompare')
            })
            
        return news_items

    except Exception as e:
        print(f"      Viga uudistega: {e}")
        return []

# --- 3. PEAMISED FUNKTSIOONID ---

def manage_existing_positions():
    print("1. PORTFELL: Kontrollin seisu...")
    try:
        positions = trading_client.get_all_positions()
    except:
        return

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
    except Exception as e:
        print(f"      Viga müügil: {e}")

def get_candidates():
    print("2. SKANNER: Otsin turu liikujaid...")
    try:
        search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        assets = trading_client.get_all_assets(search_params)
        
        ignore_list = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD", "WBTC/USD"]
        tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore_list]
        
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except:
        return []

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar: continue
        open_p = snap.daily_bar.open
        close_p = snap.daily_bar.close
        if open_p == 0: continue
        chg = ((close_p - open_p) / open_p) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:5]

def analyze_coin(symbol):
    print(f"   -> Analüüsin: {symbol}...")
    
    all_news = []
    cc_news = get_cryptocompare_news(symbol)
    if cc_news: all_news.extend(cc_news)

    # Backup Yahoo (lihtne struktuur)
    if len(all_news) < 2:
        try:
            ticker = yf.Ticker(symbol.replace("/", "-"))
            for n in ticker.news[:2]:
                all_news.append({
                    'title': n.get('title'), 
                    'body': '', # Yahoost bodyt kätte saada on keerulisem, jätame tühjaks
                    'link': n.get('link') or n.get('url'), 
                    'source': 'Yahoo'
                })
        except: pass

    news_text = ""
    if all_news:
        for n in all_news:
            title = n.get('title', 'N/A')
            body = n.get('body', '') # Võtame sisu
            link = n.get('link', '#')
            
            # Dashboardile läheb ikka pealkiri ja link
            print(f"      > UUDIS: {title} ||| {link}")
            
            # --- MUUDATUS: AI saab nüüd ka sisu ---
            news_text += f"PEALKIRI: {title}\nSISU: {body}\nALLIKAS: {n.get('source')}\n---\n"
            # --------------------------------------
    else:
        print("      Uudiseid pole (Neutraalne).")
        news_text = "Uudiseid ei leitud."

    prompt = f"""
    Analüüsi krüptovaluutat {symbol}.
    
    VIIMASED UUDISED:
    {news_text}
    
    Sinu ülesanne:
    Analüüsi uudiste sisu põhjalikult. Kui uudised on positiivsed (partnerlused, uuendused, ETF), anna kõrge skoor.
    Kui uudised on negatiivsed (häkkimised, kohtuasjad), anna madal skoor.
    
    Vasta AINULT formaadis:
    SKOOR: X
    (kus X on number 0-100).
    """
    
    try:
        res = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = res.choices[0].message.content.strip()
        
        match = re.search(r'SKOOR:\s*(\d+)', content, re.IGNORECASE)
        if match:
            score = min(int(match.group(1)), 100)
        else:
            fallback = re.search(r'\b(\d{1,3})\b', content)
            score = int(fallback.group(1)) if fallback else 0
            if score > 100: score = 0
            
        print(f"      AI HINNE: {score}/100")
        return score
    except:
        return 0

def trade(symbol):
    try:
        acc = trading_client.get_account()
        if float(acc.buying_power) < 55:
            print("   -> Raha otsas! Ei saa osta.")
            return
    except: pass

    print(f"5. TEGIJA: Ostame {symbol} $50 eest.")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=50, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga ostul: {e}")

def run_cycle():
    manage_existing_positions()
    my_pos = get_clean_positions_list()
    candidates = get_candidates()
    best_coin = None
    best_score = -1

    print("4. AI ANALÜÜS: Valime parima...")
    for c in candidates:
        s = c['symbol']
        clean = s.replace("/", "").replace("-", "")
        if clean in my_pos:
            print(f"   -> {s} olemas. Skip.")
            continue
            
        score = analyze_coin(s)
        if score > best_score:
            best_score = score
            best_coin = c

    if best_coin and best_score >= MIN_SCORE_TO_BUY:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_score}) ---")
        trade(best_coin['symbol'])
    else:
        w = best_coin['symbol'] if best_coin else "-"
        print(f"--- TULEMUS: Parim {w} ({best_score}p). Ei osta.")

if __name__ == "__main__":
    run_cycle()