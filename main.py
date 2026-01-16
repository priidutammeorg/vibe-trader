import os
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# 1. SEADISTUS JA VÕTMED
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

if not api_key or not secret_key:
    print("VIGA: Võtmeid ei leitud .env failist!")
    exit()

print("--- VIBE TRADER: INTELLIGENT MODE ---")

# Ühendame Alpacaga (Paper Trading)
trading_client = TradingClient(api_key, secret_key, paper=True)

# 2. LUGEJA (Reader) - Hangib uudiseid
def get_latest_news(symbol="BTC-USD"):
    print(f"\n1. LUGEJA: Otsin uudiseid sümbolile {symbol}...")
    try:
        ticker = yf.Ticker(symbol)
        news_list = ticker.news
        
        if not news_list:
            print("   - Hetkel uudiseid ei leitud (Yahoo API piirang või vaikus).")
            return []
        
        print(f"   - Leidsin {len(news_list)} värsket uudist.")
        return news_list
    except Exception as e:
        print(f"   - Viga uudiste lugemisel: {e}")
        return []

# 3. ANALÜÜTIK (Brain) - Otsustab
def analyze_sentiment(news_list):
    print("\n2. ANALÜÜTIK: Analüüsin pealkirju...")
    
    # Lihtne "AI" - positiivsed märksõnad (inglise keeles, sest uudised on inglise k.)
    positive_keywords = ["soars", "surge", "jump", "record", "bull", "high", "etf", "approval", "gains"]
    score = 0
    
    for article in news_list:
        title = article.get('title', '').lower()
        # Kontrollime, kas pealkirjas on häid sõnu
        for word in positive_keywords:
            if word in title:
                print(f"   + POSITIIVNE LEID: '{word}' pealkirjas: {article['title']}")
                score += 1
    
    print(f"   - Kokkuvõte: Positiivse skoor on {score}")
    
    # OTSUS: Kui leidsime vähemalt ühe väga hea uudise, siis ostame
    if score >= 1:
        return "BUY"
    else:
        return "WAIT"

# 4. TEGIJA (Trader) - Teeb tehingu
def execute_trade(decision):
    print(f"\n3. TEGIJA: Otsus on {decision}")
    
    if decision == "BUY":
        account = trading_client.get_account()
        buying_power = float(account.buying_power)
        
        if buying_power < 100:
            print("   - Raha on otsas, ei saa osta.")
            return

        print("   -> ALUSTAN OSTU: Ostame $50 eest Bitcoini.")
        # Teeme $50 suuruse ostu (Notional - ostame summa, mitte koguse järgi)
        try:
            market_order_data = MarketOrderRequest(
                symbol="BTC/USD",
                notional=50,  # Ostame 50 dollari eest
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )
            order = trading_client.submit_order(order_data=market_order_data)
            print(f"   -> TEHTUD! Orderi ID: {order.id}")
        except Exception as e:
            print(f"   -> VIGA ostmisel: {e}")
            
    else:
        print("   -> Praegu ei osta. Ootan paremaid uudiseid.")

# --- PÕHIPROTSESS ---
# See paneb kõik tükid tööle
uudised = get_latest_news("BTC-USD")
otsus = analyze_sentiment(uudised)
execute_trade(otsus)