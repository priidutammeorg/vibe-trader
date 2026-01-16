import os
import yfinance as yf
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from openai import OpenAI  # <--- UUS AJU

# 1. SEADISTUS
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")
openai_key = os.getenv("OPENAI_API_KEY") # <--- Loeme OpenAI võtme

if not api_key or not secret_key or not openai_key:
    print("VIGA: Mõni võti on puudu .env failist!")
    exit()

print("--- VIBE TRADER: AI POWERED ---")

# Ühendused
trading_client = TradingClient(api_key, secret_key, paper=True)
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
        # Võtame viimased 3 uudist, et mitte liiga palju raha kulutada
        return news_list[:3] 
    except Exception as e:
        print(f"   - Viga uudistega: {e}")
        return []

# 3. ANALÜÜTIK (The AI Brain)
def analyze_with_gpt(news_list):
    print("\n2. AI ANALÜÜTIK: Saadan uudised GPT-le analüüsimiseks...")
    
    # Valmistame uudised ette tekstina
    news_text = ""
    for article in news_list:
        news_text += f"- Pealkiri: {article['title']}\n"

    print(f"   - Analüüsin {len(news_list)} artiklit...")

    # See on prompt (käsklus) AI-le
    prompt = f"""
    Oled kogenud krüptovaluuta kaupleja. Sinu ülesanne on analüüsida neid uudiste pealkirju Bitcoini kohta:
    
    {news_text}
    
    Hinda nende mõju hinnale. Vasta AINULT ühe sõnaga:
    - BUY (kui uudised on selgelt väga positiivsed)
    - SELL (kui uudised on halvad)
    - WAIT (kui on neutraalne või ebaselge)
    """

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini", # Kasutame kiiret ja odavat mudelit
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
            
    elif decision == "SELL":
        print("   -> AI soovitab müüa (aga praegu meil pole loogikat müügiks, seega ootame).")
    else:
        print("   -> AI soovitab oodata. Turg on ebaselge.")

# --- KÄIVITUS ---
uudised = get_latest_news("BTC-USD")
if uudised:
    otsus = analyze_with_gpt(uudised)
    execute_trade(otsus)
else:
    print("Ei saanud uudiseid, ei saa analüüsida.")