import os
import sys
from datetime import datetime
import builtins
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI

# --- 0. JÕULINE LOGIMINE (Force Timestamp) ---
# See kirjutab vana print() funktsiooni üle.
# Nüüd on igal real ALATI kellaaeg ja see läheb KOHE faili.
def print(*args, **kwargs):
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    # Sunnime Pythonit väljundit kohe faili kirjutama (flush=True)
    kwargs['flush'] = True
    builtins.print(f"{now}", *args, **kwargs)

# --- 1. SEADISTUS ---
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key or not openai_key:
    print("VIGA: Võtmed puudu (.env)!")
    exit()

print("--- VIBE TRADER: RELOADED ---")

# REEGLID
TAKE_PROFIT_PCT = 10.0
STOP_LOSS_PCT = -5.0

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. ABIFUNKTSIOONID ---
def get_clean_positions():
    """Tagastab nimekirja sümbolitest, mis meil on (ilma / ja - märkideta)"""
    try:
        return [p.symbol.replace("/", "").replace("-", "") for p in trading_client.get_all_positions()]
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

# --- 4. SKANNER JA AI ---
def get_candidates():
    print("2. SKANNER: Otsin turu liikujaid...")
    search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
    assets = trading_client.get_all_assets(search_params)
    tradable = [a.symbol for a in assets if a.tradable and a.symbol.endswith("/USD")]
    
    ignore = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD"]
    
    try:
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=tradable))
    except:
        return []

    candidates = []
    for s, snap in snapshots.items():
        if s in ignore or not snap.daily_bar: continue
        change = ((snap.daily_bar.close - snap.daily_bar.open) / snap.daily_bar.open) * 100
        candidates.append({"symbol": s, "change": change, "abs_change": abs(change)})
    
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:5]

def analyze_coin(symbol):
    print(f"   -> Analüüsin: {symbol}...")
    try:
        ticker = yf.Ticker(symbol.replace("/", "-"))
        news = ticker.news[:2]
    except:
        return 0

    if not news:
        print("      Uudiseid pole.")
        return 40 # Neutraalne

    news_text = "\n".join([n.get('title', '') for n in news])
    prompt = f"Analüüsi krüptot {symbol}. Uudised:\n{news_text}\nHinda ostuskoor 0-100 (ainult number)."
    
    try:
        res = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        score = int(''.join(filter(str.isdigit, res.choices[0].message.content)))
        print(f"      AI HINNE: {score}/100")
        return score
    except:
        return 0

def trade(symbol):
    print(f"5. TEGIJA: Ostame {symbol} $50 eest.")
    try:
        req = MarketOrderRequest(symbol=symbol, notional=50, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        print("   -> TEHTUD! Ostetud.")
    except Exception as e:
        print(f"   -> Viga: {e}")

# --- 5. PEAMINE ---
def run_cycle():
    manage_existing_positions()
    
    my_positions = get_clean_positions()
    candidates = get_candidates()
    
    best_coin = None
    best_score = -1

    print("4. AI ANALÜÜS: Valime parima...")
    for c in candidates:
        sym = c['symbol']
        clean_sym = sym.replace("/", "").replace("-", "")
        
        if clean_sym in my_positions:
            print(f"   -> {sym} on juba olemas. Jätan vahele.")
            continue
            
        score = analyze_coin(sym)
        if score > best_score:
            best_score = score
            best_coin = c

    if best_coin and best_score >= 75:
        print(f"--- VÕITJA: {best_coin['symbol']} (Skoor: {best_score}) ---")
        trade(best_coin['symbol'])
    else:
        print(f"--- TULEMUS: Parim oli {best_coin['symbol'] if best_coin else '-'} ({best_score}p). Ei osta.")

if __name__ == "__main__":
    run_cycle()