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

print("--- VIBE TRADER: FULL MARKET SCANNER ---")

# Ühendused
trading_client = TradingClient(api_key, secret_key, paper=True)
data_client = CryptoHistoricalDataClient()
ai_client = OpenAI(api_key=openai_key)

# --- 2. VARADE LEIDJA (Leiab kõik, mida üldse kaubelda saab) ---
def get_all_tradable_coins():
    print("\n1. SKANNER: Laen alla kõik Alpaca krüptovaluutad...")
    
    # Küsime Alpacalt kõik aktiivsed krüptod
    search_params = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
    assets = trading_client.get_all_assets(search_params)
    
    # Filtreerime välja need, mis pole kaubeldavad (tradable=True)
    tradable_symbols = [asset.symbol for asset in assets if asset.tradable]
    
    print(f"   -> Leidsin {len(tradable_symbols)} kaubeldavat münti.")
    return tradable_symbols

# --- 3. MATEMAATILINE FILTER (Leiab suurimad liikujad) ---
def find_top_movers(all_symbols, limit=5):
    print("2. FILTER: Otsin suurimaid liikujaid (Volume & Volatility)...")
    
    # Küsime kõigi nende müntide hetkeseisu korraga
    # Alpaca API tahab sümboleid kujul "BTC/USD"
    
    try:
        snapshots = data_client.get_crypto_snapshot(CryptoSnapshotRequest(symbol_or_symbols=all_symbols))
    except Exception as e:
        print(f"   Viga andmete pärimisel: {e}")
        return []

    candidates = []
    
    # Need on stabiilsed mündid, mis ei liigu (pole mõtet analüüsida)
    ignore_list = ["USDT/USD", "USDC/USD", "DAI/USD", "TUSD/USD", "PAXG/USD"]

    for symbol, snapshot in snapshots.items():
        if symbol in ignore_list:
            continue
            
        daily_bar = snapshot.daily_bar
        if not daily_bar:
            continue
            
        # Arvutame protsentuaalse muutuse (avamine vs praegune hind)
        open_price = daily_bar.open
        current_price = daily_bar.close
        
        if open_price == 0: 
            continue
            
        change_pct = ((current_price - open_price) / open_price) * 100
        
        # Lisame nimekirja: (Sümbol, Muutus%, Hind)
        candidates.append({
            "symbol": symbol,
            "change": change_pct,
            "abs_change": abs(change_pct), # Jälgime liikumise suurust, suund pole alguses tähtis
            "price": current_price
        })

    # Sorteerime suurima liikumise järgi (Top Movers)
    candidates.sort(key=lambda x: x['abs_change'], reverse=True)
    
    top_picks = candidates[:limit]
    
    print(f"   -> Valisin välja {len(top_picks)} kõige kuumemat:")
    for coin in top_picks:
        print(f"      * {coin['symbol']}: {coin['change']:.2f}% (Hind: ${coin['price']:.4f})")
        
    return top_picks

# --- 4. LUGEJA JA HINDAJA (AI) ---
def analyze_coin(symbol):
    # Teeme sümboli Yahoo jaoks sobivaks: "BTC/USD" -> "BTC-USD"
    yahoo_symbol = symbol.replace("/", "-")
    print(f"\n   -> Analüüsin uudiseid: {yahoo_symbol}...")
    
    try:
        ticker = yf.Ticker(yahoo_symbol)
        news_list = ticker.news[:3] # 3 värsket uudist
    except:
        return 0

    if not news_list:
        print("      Uudiseid polnud.")
        return 0

    # Valmistame teksti ette
    news_text = ""
    for article in news_list:
        title = article.get('title')
        if not title and 'content' in article and isinstance(article['content'], dict):
            title = article['content'].get('title')
        if not title: title = article.get('headline', '')
        news_text += f"- {title}\n"

    # AI Prompt
    prompt = f"""
    Oled halastamatu krüptokaupleja. Analüüsi valuutat {symbol}.
    Uudised:
    {news_text}
    
    Anna hinnang "Short-term Trading Score" (0-100).
    - Kui uudised räägivad suurest tõusust/partnerlusest -> 80-100.
    - Kui uudised on halvad/hirm -> 0-20.
    - Kui uudised on vanad või igavad -> 40-60.
    
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

# --- 5. TÖÖVOOG ---
def run_scanner():
    # 1. Kõik mündid
    all_coins = get_all_tradable_coins()
    if not all_coins:
        print("Viga: Ei leidnud Alpacast münte.")
        return

    # 2. Leia kuumad
    candidates = find_top_movers(all_coins, limit=5)
    
    # 3. AI Analüüs
    best_coin = None
    best_score = -1

    print("\n3. AI ANALÜÜS: Sukeldume detailidesse...")
    for coin_data in candidates:
        score = analyze_coin(coin_data['symbol'])
        
        # Väike loogika: Kui hind on kukkunud (-10%) aga skoor on kõrge (80+), 
        # siis on see "Buy the Dip" võimalus!
        
        if score > best_score:
            best_score = score
            best_coin = coin_data

    # 4. Otsus
    if best_coin and best_score >= 75:
        print(f"\n--- VÕITJA SELGUNUD ---")
        print(f"Münt: {best_coin['symbol']}")
        print(f"Skoor: {best_score}/100")
        print(f"Turu liikumine: {best_coin['change']:.2f}%")
        
        trade_decision(best_coin['symbol'])
    else:
        print(f"\n--- TULEMUS ---")
        print(f"Parim oli {best_coin['symbol'] if best_coin else 'Puudub'} skooriga {best_score}.")
        print("Turg on liiga ebakindel. Täna ei riski.")

def trade_decision(symbol):
    account = trading_client.get_account()
    if float(account.buying_power) < 50:
        print("Raha otsas!")
        return

    print(f"4. TEGIJA: Ostame ${symbol} $50 eest.")
    try:
        req = MarketOrderRequest(
            symbol=symbol,
            notional=50,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )
        trading_client.submit_order(req)
        print("TEHTUD! Oled nüüd selle omanik.")
    except Exception as e:
        print(f"Viga ostul: {e}")

if __name__ == "__main__":
    run_scanner()