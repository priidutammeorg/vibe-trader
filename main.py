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

# --- 0. JÕULINE LOGIMINE ---
# Sunnime Pythonit igale reale kellaaega lisama ja kohe faili kirjutama
def print(*args, **kwargs):
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    kwargs['flush'] = True
    builtins.print(f"{now}", *args, **kwargs)

# --- 1. SEADISTUS JA API VÕTMED ---
load_dotenv()

api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

# Puhastame CryptoPanic võtme tühikutest (tihti tekib copy-paste viga)
cp_key = os.getenv("CRYPTOPANIC_API_KEY")
if cp_key:
    cp_key = cp_key.strip()

if not api_key or not secret_key or not openai_key:
    print("VIGA: Põhivõtmed (.env) on puudu! Kontrolli faili.")
    exit()

print("--- VIBE TRADER: FINAL v5.0 (URL FIX) ---")

# REEGLID
TAKE_PROFIT_PCT = 10.0
STOP_LOSS_PCT = -5.0
MIN_SCORE_TO_BUY = 75

# KLIENDID
trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. ABIFUNKTSIOONID ---

def get_clean_positions_list():
    """Tagastab portfellis olevad sümbolid puhtal kujul (nt ['BTC', 'ETH'])"""
    try:
        positions = trading_client.get_all_positions()
        return [p.symbol.replace("/", "").replace("-", "") for p in positions]
    except:
        return []

def get_cryptopanic_news(symbol):
    """Küsib CryptoPanic API-st uudiseid (FIXED URL & HEADERS)"""
    if not cp_key: 
        return []
    
    clean_sym = symbol.split("/")[0] # Teeme BTC/USD -> BTC
    base_url = "https://cryptopanic.com/api/v1/posts/"
    
    # Parameetrid eraldi, et vältida URLi vigast ehitust
    params = {
        "auth_token": cp_key,
        "currencies": clean_sym,
        "kind": "news",
        "filter": "hot",
        "public": "true"
    }
    
    # Teeskleme brauserit, et vältida 403/404 vigu
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        res = requests.get(base_url, params=params, headers=headers, timeout=10)
        
        if res.status_code != 200:
            print(f"      CryptoPanic VIGA {res.status_code} (URL: {res.url})") 
            return []

        data = res.json()
        results = data.get('results', [])
        
        news_items = []
        for item in results[:3]:
            news_items.append({
                'title': item['title'],
                'link': item['url'], # CryptoPanic lühilink
                'source': 'CryptoPanic'
            })
        return news_items

    except Exception as e:
        print(f"      Viga ühenduses CryptoPanicuga: {e}")
        return []

# --- 3. PEAMISED FUNKTSIOONID ---

def manage_existing_positions():
    print("1. PORTFELL: Kontrollin seisu...")
    try:
        positions = trading_client.get_all_positions()
    except:
        print("   Viga portfelli lugemisel.")
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
        
        # Välistame stabiilsed mündid
        ignore_list = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD", "WBTC/USD"]
        tradable = [
            a.symbol for a in assets 
            if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore_list
        ]
        
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except Exception as e:
        print(f"   Viga turuandmete laadimisel: {e}")
        return []

    candidates = []
    for s, snap in snapshots.items():
        if not snap.daily_bar: continue
        
        open_p = snap.daily_bar.open
        close_p = snap.daily_bar.close
        
        if open_p == 0: continue
        
        chg = ((close_p - open_p) / open_p) * 100
        candidates.append({"symbol": s, "change": chg, "abs_change": abs(chg)})
    
    # Sorteerime suurima liikuja järgi
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:5]

def analyze_coin(symbol):
    print(f"   -> Analüüsin: {symbol}...")
    
    all_news = []

    # 1. Küsime CryptoPanicust
    cp_news = get_cryptopanic_news(symbol)
    if cp_news:
        all_news.extend(cp_news)

    # 2. Kui vähe uudiseid, küsime Yahoost lisa
    if len(all_news) < 2:
        try:
            yahoo_symbol = symbol.replace("/", "-")
            ticker = yf.Ticker(yahoo_symbol)
            y_news = ticker.news[:2]
            for n in y_news:
                all_news.append({
                    'title': n.get('title'),
                    'link': n.get('link') or n.get('url'),
                    'source': 'Yahoo'
                })
        except:
            pass

    news_text = ""
    if all_news:
        for n in all_news:
            title = n.get('title', 'Pealkiri puudub')
            link = n.get('link', '#')
            source = n.get('source', 'Unknown')
            
            # See rida on oluline Dashboardi jaoks (||| eraldaja)
            print(f"      > UUDIS: {title} ||| {link}")
            news_text += f"- {title} (Allikas: {source})\n"
    else:
        print("      Uudiseid pole (Neutraalne).")
        news_text = "Uudiseid ei leitud."

    # 3. AI Analüüs (Range režiim - ainult number)
    prompt = f"""
    Analüüsi krüptovaluutat {symbol}.
    Uudised:
    {news_text}
    
    Hinda ostupotentsiaali (0-100).
    OLULINE: Vasta AINULT järgmises vormingus:
    SKOOR: X
    (kus X on number). Ära lisa muud teksti.
    """
    
    try:
        res = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = res.choices[0].message.content.strip()
        
        # Otsime kindlat mustrit "SKOOR: 85"
        match = re.search(r'SKOOR:\s*(\d+)', content, re.IGNORECASE)
        
        if match:
            score = int(match.group(1))
            score = min(score, 100) # Kaitse "2023" vastu
        else:
            # Fallback: otsime üksikut numbrit
            fallback = re.search(r'\b(\d{1,3})\b', content)
            score = int(fallback.group(1)) if fallback else 0
            if score > 100: score = 0
            
        print(f"      AI HINNE: {score}/100")
        return score
    except Exception as e:
        print(f"      Viga AI päringus: {e}")
        return 0

def trade(symbol):
    try:
        acc = trading_client.get_account()
        if float(acc.buying_power) < 55:
            print("   -> Raha otsas! Ei saa osta.")
            return
    except: 
        pass

    print(f"5. TEGIJA: Ostame {symbol} $50 eest.")
    try:
        req = MarketOrderRequest(
            symbol=symbol,
            notional=50,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )
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
            print(f"   -> {s} on juba olemas. Jätan vahele.")
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