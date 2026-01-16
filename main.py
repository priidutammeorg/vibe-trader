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

print("--- VIBE TRADER: AI POWERED (DEEP SEARCH) ---")

# Ühendused
trading_client = TradingClient(api_key, secret_key, paper=True)

ai_client = None
if openai_key:
    ai_client = OpenAI(api_key=openai_key)
else:
    print("HOIATUS: OpenAI võti puudub.")

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
        # --- PARANDUS: Otsime pealkirja sügavamalt ---
        title = article.get('title')
        
        # Kui pealkirja polnud, vaatame 'content' sisse
        if not title and 'content' in article:
            # Vahel on content ise sõnastik
            if isinstance(article['content'], dict):
                title = article['content'].get('title')
        
        # Kui ikka pole, proovime 'headline'
        if not title:
            title = article.get('headline')

        # Kui ikka pole, siis on mingi jama
        if not title:
            title = "Pealkiri puudub"

        # Debugime esimest uudist põhjalikumalt
        if i == 0:
            print(f"   [DEBUG] Esimene toores uudis: {article}")
            
        news_text += f"- Uudis {i+1}: {title}\n"

    print(f"   - Saadan AI-le info:\n{news_text}")

    prompt = f"""
    Oled kogenud krüptovaluuta kaupleja. Analüüsi neid pealkirju:
    {news_text}
    
    Hinda mõju hinnale. Vasta AINULT ühe sõnaga:
    - BUY (kui uudised on väga head)
    - SELL (kui uudised on halvad)
    - WAIT (kui neutraalne või info puudub)
    """

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        decision = response.choices[0].message.content.strip()
        print(f"   - AI VASTUS: {decision}")
        return decision
    except Exception as e:
        print(f"   - AI Viga: {e}")
        return "WAIT"

# 4. TEGIJA (Trader)
def execute_trade(decision):
    print(f"\n3. TEGIJA: Tegevus -> {decision}")
    
    if decision == "BUY":
        print("   -> AI andis rohelise tule! Ostame $50 eest.")
        try:
            market_order_data = MarketOrderRequest(
                symbol="BTC/USD",
                notional=50,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order_data=market_order_data)
            print("   -> OST SOORITATUD!")
        except Exception as e:
            print(f"   -> Viga ostmisel: {e}")
    else:
        print("   -> Tehingut ei toimu.")

# --- KÄIVITUS ---
uudised = get_latest_news("BTC-USD")
if uudised:
    otsus = analyze_with_gpt(uudised)
    execute_trade(otsus)
else:
    print("Ei saanud uudiseid.")