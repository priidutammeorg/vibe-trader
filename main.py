import os
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from openai import OpenAI

# 1. SEADISTUS
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not api_key or not secret_key:
    print("VIGA: Alpaca võtmed on puudu!")
    exit()

if not openai_key:
    print("HOIATUS: OpenAI võti puudub. Kasutan ainult lokaalset loogikat (kui oleks).")
    # Siin peaks tegelikult exit() tegema, kui tahame ainult AI-d
    
print("--- VIBE TRADER: AI POWERED (FIXED) ---")

# Ühendused
trading_client = TradingClient(api_key, secret_key, paper=True)
# Kontrollime, kas OpenAI võti on olemas enne kliendi loomist
ai_client = None
if openai_key:
    ai_client = OpenAI(api_key=openai_key)

# 2. LUGEJA (Reader)
def get_latest_news(symbol="BTC-USD"):
    print(f"\n1. LUGEJA: Otsin uudiseid sümbolile {symbol}...")
    try:
        ticker = yf.Ticker(symbol)
        news_list = ticker.news
        
        if not news_list:
            print("   - Uudiseid ei leitud.")
            return []
        
        print(f"   - Leidsin {len(news_list)} uudist.")
        # Võtame viimased 3
        return news_list[:3] 
    except Exception as e:
        print(f"   - Viga uudistega: {e}")
        return []

# 3. ANALÜÜTIK (The AI Brain)
def analyze_with_gpt(news_list):
    if not ai_client:
        print("   - OpenAI klienti pole. Jätan vahele.")
        return "WAIT"

    print("\n2. AI ANALÜÜTIK: Saadan uudised GPT-le analüüsimiseks...")
    
    news_text = ""
    for i, article in enumerate(news_list):
        # --- PARANDUS: Kasutame .get(), et vältida KeyError viga ---
        # Mõnikord on