import os
import time
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest
from openai import OpenAI

# --- 1. SEADISTUS ---
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key or not openai_key:
    print("VIGA: Võtmed puudu (.env)!")
    exit()

print("--- VIBE TRADER: COMPLETE CYCLE (BUY & SELL) ---")

# REEGLID MÜÜGIKS
TAKE_PROFIT_PCT = 10.0  # Müüme, kui kasum on 10%
STOP_LOSS_PCT = -5.0    # Müüme, kui kahjum on 5%

trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. PORTFELLI HALDUR (MÜÜGI LOOGIKA) ---
def manage_existing_positions():
    print("\n1. PORTFELL: Kontrollin olemasolevaid positsioone...")
    
    try:
        positions = trading_client.get_all_positions()
    except Exception as e:
        print(f"   Viga positsioonide lugemisel: {e}")
        return

    if not positions:
        print("   -> Portfell on tühi. Midagi pole müüa.")
        return

    for p in positions:
        symbol = p.symbol
        # Alpaca annab kasumi kümnendkohana (nt 0.05 on 5%)
        profit_pct = float(p.unrealized_plpc) * 100
        current_price = float(p.current_price)
        qty = float(p.qty)
        
        print(f"   -> {symbol}: {profit_pct:.2f}% (Kogus: {qty})")

        # KASUMIVÕTT
        if profit_pct >= TAKE_PROFIT_PCT:
            print(f"      $$$ KASUM KÄES! (+{profit_pct:.2f}%) Müün {symbol}...")
            close_position(symbol)
            
        # KAHJUMI PEATAMINE
        elif profit_pct <= STOP_LOSS_PCT:
            print(f"      !!! KAHJUM LIIGA SUUR ({profit_pct:.2f}%) Müün {symbol}, et päästa mis annab...")
            close_position(symbol)
        
        else:
            print("      ...Hojan edasi (Jääb vahemikku -5% kuni +10%)")

def close_position(symbol):
    try:
        trading_client.close_position(symbol)
        print(f"      TEHTUD! {symbol} müüdud.")
    except Exception as e:
        print(f"      Viga müümisel: {e}")

# --- 3. SKANNER (OSTU LOOGIKA) ---
def get_all_tradable_coins():
    print("\n2. SKANNER: Laen alla turuinfo...")
    search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
    assets = trading_client.get_all_assets(search_params)
    tradable_symbols = [
        asset.symbol for asset in assets 
        if asset.tradable and asset.symbol.endswith("/USD")
    ]
    return tradable_symbols

def find_top_movers(all_symbols, limit=5):
    print("3. FILTER: Otsin 'actionit'...")
    try:
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=all_symbols))
    except Exception as e:
        print(f"   Viga andmete pärimisel: {e}")
        return []

    candidates = []
    ignore_list = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD", "USDP/USD"]

    for symbol, snapshot in snapshots.items():
        if symbol in ignore_list or not snapshot.daily_bar: continue
            
        open_price = snapshot.daily_bar.open
        current_price = snapshot.daily_bar.close
        if open_price == 0: continue
            
        change_pct = ((current_price - open_price) / open_price) * 100
        
        candidates.append({
            "symbol": symbol,
            "change": change_pct,
            "abs_change": abs(change_pct),
            "price": current_price
        })

    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    return candidates[:limit]

def analyze_coin(symbol):
    yahoo_symbol = symbol.replace("/", "-")
    print(f"\n   -> Analüüsin: {yahoo_symbol}...")
    
    try:
        ticker = yf.Ticker(yahoo_symbol)
        news_list = ticker.news[:3]
    except:
        return 0

    if not news_list:
        print("      Uudiseid polnud.")
        return 0

    news_text = ""
    for article in news_list:
        title = article.get('title')
        if not title and 'content' in article and isinstance(article['content'], dict):
            title = article['content'].get('title')
        if not title: title = article.get('headline', '')
        news_text += f"- {title}\n"

    prompt = f"""
    Oled professionaalne krüptokaupleja. Analüüsi valuutat {symbol}.
    Uudised:
    {news_text}
    
    Hinda "Trading Opportunity Score" (0-100).
    - Hea tõusu potentsiaal -> 80-100.
    - Halb sentiment -> 0-20.
    - Neutraalne/Vana info -> 40-60.
    
    NB! Osta dipist (skoor 75+), kui hind on maas aga uudised ei ole katastroofilised.
    Vasta AINULT numbriga.
    """

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        score_str = response.choices[0].message.content.strip()
        score = int(''.join(filter(str.isdigit, score_str)))
        print(f"      AI HINNE: {score}/100")
        return score
    except:
        return 0

def trade_decision(symbol):
    account = trading_client.get_account()
    if float(account.buying_power) < 50:
        print("   -> Raha otsas! Ei saa osta.")
        return

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

# --- 4. PEAMINE TÖÖVOOG ---
def run_cycle():
    # SAMM 1: Korista portfell (Müü kasum või kahjum)
    manage_existing_positions()
    
    # SAMM 2: Otsi uusi võimalusi
    all_coins = get_all_tradable_coins()
    if not all_coins: return

    candidates = find_top_movers(all_coins, limit=5)
    
    best_coin = None
    best_score = -1

    print("\n4. AI ANALÜÜS: Valime parima...")
    for coin_data in candidates:
        score = analyze_coin(coin_data['symbol'])
        if score > best_score:
            best_score = score
            best_coin = coin_data

    # SAMM 3: Osta võitja
    if best_coin and best_score >= 75:
        print(f"\n--- VÕITJA: {best_coin['symbol']} (Skoor: {best_score}) ---")
        trade_decision(best_coin['symbol'])
    else:
        print(f"\n--- TULEMUS: Parim oli {best_coin['symbol'] if best_coin else '-'} ({best_score}p). Ei osta.")

if __name__ == "__main__":
    run_cycle()