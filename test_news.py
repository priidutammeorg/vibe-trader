import os
import requests
from dotenv import load_dotenv

# Lae võtmed
load_dotenv()
api_key = os.getenv("CRYPTOPANIC_API_KEY")

print("--- CRYPTOPANIC API TEST ---")

if not api_key:
    print("VIGA: CRYPTOPANIC_API_KEY puudub .env failist!")
    exit()

print(f"Võti leitud: {api_key[:5]}...{api_key[-5:]}")

# Testime BTC uudiseid
url = f"https://cryptopanic.com/api/v1/posts/?auth_token={api_key}&currencies=BTC&kind=news"

# Oluline: Lisame User-Agent, et mitte välja näha nagu bot
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

try:
    print("Saadan päringu...")
    response = requests.get(url, headers=headers, timeout=10)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ ÜHENDUS ÕNNESTUS!")
        print(f"Leidsin {len(data.get('results', []))} uudist.")
        
        # Prindi esimene uudis
        if data['results']:
            first = data['results'][0]
            print(f"\nNäidispealkiri: {first['title']}")
            print(f"Allikas: {first['domain']}")
            print(f"URL: {first['url']}")
        else:
            print("Huvitav, tulemusi on 0, aga ühendus toimib.")
    elif response.status_code == 401:
        print("\n❌ VIGA: Vale API võti (Unauthorized). Kontrolli .env faili.")
    elif response.status_code == 429:
        print("\n❌ VIGA: Liiga palju päringuid (Rate Limit). Oota natuke.")
    else:
        print(f"\n❌ VIGA: Tundmatu vastus: {response.text}")

except Exception as e:
    print(f"\n❌ KRITILINE VIGA: {e}")