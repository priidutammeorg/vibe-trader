import os
import requests
import json
from dotenv import load_dotenv

# Lae ja PUHASTA võti (eemalda tühikud)
load_dotenv()
raw_key = os.getenv("CRYPTOPANIC_API_KEY")
if not raw_key:
    print("VIGA: Võti puudub .env failist")
    exit()

api_key = raw_key.strip() # See on ülioluline!

print("--- CRYPTOPANIC API TEST v2 ---")
print(f"Võti (puhastatud): {api_key[:5]}...{api_key[-5:]}")

# Baas-URL ja parameetrid eraldi
url = "https://cryptopanic.com/api/v1/posts/"
params = {
    "auth_token": api_key,
    "currencies": "BTC",
    "kind": "news",
    "filter": "important",
    "public": "true"
}

try:
    print(f"Saadan päringu aadressile: {url}")
    # Las requests paneb ise URLi kokku
    response = requests.get(url, params=params, timeout=10)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ ÜHENDUS KORRAS!")
        results = data.get('results', [])
        print(f"Leidsin {len(results)} uudist.")
        
        if results:
            print(f"\nViimane uudis: {results[0]['title']}")
            print(f"Allikas: {results[0]['domain']}")
    else:
        print("\n❌ VIGA SERVERILT:")
        print(response.text[:500]) # Näita veateate algust

except Exception as e:
    print(f"\n❌ SKRIPTI VIGA: {e}")