import os
from dotenv import load_dotenv
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest
from alpaca.trading.client import TradingClient

# 1. Laeme võtmed
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

# Kontrollime, kas võtmed on olemas
if not api_key or not secret_key:
    print("VIGA: Võtmeid ei leitud .env failist!")
    exit()

print("--- VIBE TRADER: CRYPTO EDITION ---")

# 2. Ühendame kauplemiskontoga (Paper Trading)
try:
    trading_client = TradingClient(api_key, secret_key, paper=True)
    account = trading_client.get_account()
    
    # Arvutame vaba raha
    balance = float(account.buying_power)
    print(f"Konto seis: ${balance:,.2f}")

except Exception as e:
    print(f"Viga kontoga ühendamisel: {e}")
    exit()

# 3. Küsime Bitcoini hinda
try:
    # Alpaca Crypto API klient
    crypto_client = CryptoHistoricalDataClient()
    
    # Küsime BTC/USD hinda
    request_params = CryptoLatestQuoteRequest(symbol_or_symbols="BTC/USD")
    quote = crypto_client.get_crypto_latest_quote(request_params)
    
    # Võtame 'ask' hinna
    btc_price = quote["BTC/USD"].ask_price
    
    print(f"Bitcoini hind: ${btc_price:,.2f}")
    
    # 4. Lihtne arvutus
    max_btc = balance / btc_price
    print(f"Saaksid praegu osta maksimaalselt: {max_btc:.4f} BTC")

except Exception as e:
    print(f"Viga hinna saamisel: {e}")