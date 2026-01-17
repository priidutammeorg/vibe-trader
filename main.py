import os
import sys
import time
import builtins
import re
from datetime import datetime
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI

# --- 0. SÜSTEEMI TÄIUSTUSED (Time & Flush) ---
# See funktsioon sunnib Pythonit igale reale kellaaega lisama
# ja kirjutab info KOHE faili, et Dashboard ei hilineks.
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
    print("VIGA: API võtmed puudu (.env failist)!")
    exit()

print("--- VIBE TRADER: FINAL VERSION ---")

# REEGLID
TAKE_PROFIT_PCT = 10.0
STOP_LOSS_PCT = -5.0
MIN_SCORE_TO_BUY = 75

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. ABIFUNKTSIOONID ---
def get_clean_positions_list():
    """Tagastab nimekirja sümbolitest, mis meil on (ilma / ja - märkideta)"""
    try:
        positions = trading_client.get_all_positions()
        return [p.symbol.replace("/", "").replace("-", "") for p in positions]
    except:
        return []

# --- 3. PORTFELLI HALDUR ---
def manage_existing_positions():
    print("1. PORTFELL: Kontrollin seisu...")
    try:
        positions = trading_client.get_all_positions()
    except Exception as e:
        print(f"   Viga lugemisel: {e}")
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

# --- 4. TURU SKANNER ---
def get_candidates():
    print("2. SKANNER: Otsin turu liikujaid...")
    search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
    assets = trading_client.get_all_assets(search_params)
    
    ignore_list = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD", "USDP/USD", "WBTC/USD"]
    
    tradable_symbols = [
        a.symbol for a in assets 
        if a.tradable and a.symbol.endswith("/USD") and a.symbol not in ignore_list
    ]
    
    try:
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable_symbols))
    except Exception as e:
        print(f"   Viga turuandmete laadimisel: {e}")
        return []

    candidates = []
    for symbol, snapshot in snapshots.items():
        if not snapshot.daily_bar: continue
        open_price = snapshot.daily_bar.open
        close_price = snapshot.daily_bar.close
        if open_price == 0: continue
        
        change_pct = ((close_price - open_price) / open_price) * 100
        candidates.append({
            "symbol": symbol,
            "change": change_pct,
            "abs_change": abs(change_pct)
        })
    
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:5]

# --- 5. AI ANALÜÜS (Uudistega) ---
def analyze_coin(symbol):
    print(f"   -> Analüüsin: {symbol}...")
    try:
        yahoo_symbol = symbol.replace("/", "-")
        ticker = yf.Ticker(yahoo_symbol)
        news = ticker.news[:3]
    except:
        return 0

    if not news:
        print("      Uudiseid pole (Neutraalne).")
        return 40 

    news_text = ""
    for n in news:
        title = n.get('title', 'Pealkiri puudub')
        link = n.get('link', '#')
        
        # --- LOGIME UUDISE LINGI ---
        # See rida on vajalik, et Dashboard saaks lingi kätte
        print(f"      > UUDIS: {title} {link}") 
        
        news_text += f"- {title}\n"

    prompt = f"""
    Analüüsi krüptovaluutat {symbol} lühiajaliselt (swing trade).
    Uudised:
    {news_text}
    
    Hinda ostupotentsiaali skaalal 0 kuni 100.
    Vasta AINULT numbriga.
    """
    
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        content = response.choices[0].message.content.strip()
        
        # --- TURVALINE PARSIMINE ---
        match = re.search(r'(\d+)', content)
        if match:
            score = int(match.group(1))
            score = min(score, 100) # Max 100
        else:
            score = 0
            
        print(f"      AI HINNE: {score}/100")
        return score
    except Exception as e:
        print(f"      Viga AI päringus: {e}")
        return 0

# --- 6. TEHINGU TEGEMINE ---
def trade(symbol):
    try:
        account = trading_client.get_account()
        if float(account.buying_power) < 55:
            print(f"   -> Raha otsas (${account.buying_power})! Ei saa osta.")
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

# --- 7. PEAMINE TÖÖVOOG ---
def run_cycle():
    manage_existing_positions()
    my_positions = get_clean_positions_list()
    candidates = get_candidates()
    
    best_coin = None
    best_score = -1

    print("4. AI ANALÜÜS: Valime parima...")
    for coin in candidates:
        sym = coin['symbol']
        clean_sym = sym.replace("/", "").replace("-", "")
        
        if clean_sym in my_positions:
            print(f"   -> {sym} on juba olemas. Jätan vahele.")
            continue
            
        score = analyze_coin(sym)
        if score > best_score:
            best_score = score
            best_coin = coin

    if best_coin and best_score >= MIN_SCORE_TO_BUY:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_score}) ---")
        trade(best_coin['symbol'])
    else:
        winner = best_coin['symbol'] if best_coin else "-"
        print(f"--- TULEMUS: Parim oli {winner} ({best_score}p). Ei osta.")

if __name__ == "__main__":
    run_cycle()