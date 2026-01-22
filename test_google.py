import requests
import xml.etree.ElementTree as ET

def get_google_news(symbol):
    print(f"--- Otsin uudiseid: {symbol} ---")
    try:
        clean_ticker = symbol.split("/")[0] # nt 'BTC'
        # Google News RSS URL: Otsime "MÜNT crypto", viimased 24h
        url = f"https://news.google.com/rss/search?q={clean_ticker}+crypto+when:1d&hl=en-US&gl=US&ceid=US:en"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        print(f"Päring URL-ile: {url}")
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            news_items = []
            # Võtame 3 esimest uudist
            for item in root.findall('.//item')[:3]:
                title = item.find('title').text
                pub_date = item.find('pubDate').text
                link = item.find('link').text
                print(f"   ✅ LEITUD: {title}")
                print(f"      Aeg: {pub_date}")
                news_items.append(title)
            
            if not news_items:
                print("   ⚠️ Ühtegi uudist ei leitud (RSS on tühi).")
            return news_items
            
        else:
            print(f"   ❌ Viga! Status code: {res.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Kriitiline viga: {e}")
        return []

# Testime 3 erineva mündiga
if __name__ == "__main__":
    get_google_news("BTC/USD")
    print("\n")
    get_google_news("PEPE/USD")
    print("\n")
    get_google_news("SOL/USD")