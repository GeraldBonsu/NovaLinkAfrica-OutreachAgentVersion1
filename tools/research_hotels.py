"""
Tool: research_hotels.py
Purpose: Search for hotels in Ghana using SerpAPI + Firecrawl.
Output: .tmp/hotels_raw.json
"""

import requests
import json
import os
import re
import time
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

SERPAPI_KEY = os.getenv('SERPAPI_API_KEY')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = os.path.join(BASE_DIR, '.tmp')

GHANA_REGIONS = [
    'Greater Accra', 'Ashanti', 'Western', 'Eastern', 'Central',
    'Northern', 'Upper East', 'Upper West', 'Volta', 'Bono', 'Oti'
]
GHANA_CITIES = [
    'Accra', 'Kumasi', 'Takoradi', 'Tamale', 'Cape Coast',
    'Sunyani', 'Koforidua', 'Ho', 'Wa', 'Bolgatanga', 'Tema'
]

def search_maps(query):
    params = {
        "engine": "google_maps",
        "q": query,
        "ll": "@7.9527254,-1.0307548,7z",
        "api_key": SERPAPI_KEY,
        "type": "search",
        "hl": "en",
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    data = resp.json()
    return data.get("local_results", [])

def search_web(query):
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 10,
        "gl": "gh",
        "hl": "en",
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    data = resp.json()
    return data.get("organic_results", [])

FIRECRAWL_KEY = os.getenv('FIRECRAWL_API_KEY')

def scrape_url(url):
    """Scrape a URL using the Firecrawl REST API."""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {FIRECRAWL_KEY}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]},
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("markdown", "")
    except Exception as e:
        print(f"    Scrape error: {e}")
    return ""

def extract_emails(text):
    pattern = r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
    emails = re.findall(pattern, text)
    blocked = ['example', 'test', 'noreply', 'no-reply', 'sentry', 'placeholder',
               'wixpress', 'squarespace', 'wordpress', 'yoursite', 'domain']
    return list(set(e for e in emails if not any(b in e.lower() for b in blocked)))

def extract_phone(text):
    patterns = [
        r'\+233[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{4}',
        r'\+233[\s\-]?\d{9}',
        r'0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}',
        r'0\d{9}',
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group().strip()
    return ""

def extract_city_region(address):
    city, region = "", ""
    for c in GHANA_CITIES:
        if c.lower() in address.lower():
            city = c
            break
    for r in GHANA_REGIONS:
        if r.lower() in address.lower():
            region = r
            break
    if not region and city == 'Accra':
        region = 'Greater Accra'
    elif not region and city == 'Kumasi':
        region = 'Ashanti'
    elif not region and city == 'Takoradi':
        region = 'Western'
    return city, region

def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    hotels = {}

    search_queries = [
        "hotels in Accra Ghana",
        "hotels in Kumasi Ghana",
        "hotels in Takoradi Ghana",
        "hotels in Cape Coast Ghana",
        "hotels in Tema Ghana",
        "luxury hotels Accra Ghana",
        "business hotels Accra Ghana",
        "airport hotel Accra Ghana",
        "boutique hotels Ghana",
        "4 star hotels Ghana",
    ]

    print("=== Phase 1: Searching for hotels via SerpAPI ===\n")
    for query in search_queries:
        print(f"  Searching: {query}")
        results = search_maps(query)
        for r in results:
            name = r.get("title", "").strip()
            if not name or name in hotels:
                continue
            address = r.get("address", "")
            city, region = extract_city_region(address)
            hotels[name] = {
                "hotel_name": name,
                "city": city,
                "region": region,
                "country": "Ghana",
                "phone": r.get("phone", ""),
                "email": "",
                "website": r.get("website", ""),
                "contact_person": "",
                "contact_role": "",
                "source_url": f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(name + ' Ghana')}",
                "address": address,
                "rating": r.get("rating", ""),
                "reviews": r.get("reviews", 0),
                "notes": "",
            }
        time.sleep(0.5)

    print(f"\nFound {len(hotels)} unique hotels.")
    hotels_list = list(hotels.values())

    # Save SerpAPI results immediately before scraping
    raw_path = os.path.join(TMP_DIR, 'hotels_raw.json')
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(hotels_list, f, indent=2, ensure_ascii=False)
    print(f"  Saved SerpAPI data -> {raw_path}")

    print("\n=== Phase 2: Scraping websites for emails (Firecrawl API) ===\n")

    for i, hotel in enumerate(hotels_list):
        website = hotel.get("website", "").strip()
        if not website:
            print(f"  [{i+1}/{len(hotels_list)}] {hotel['hotel_name']} — no website, skipping")
            continue

        # Clean URL — strip query params for contact page construction
        base_url = website.split('?')[0].rstrip('/')
        pages = [website, base_url + '/contact', base_url + '/contact-us']

        found_email = False
        for page_url in pages:
            print(f"  [{i+1}/{len(hotels_list)}] {hotel['hotel_name']} — scraping {page_url}")
            content = scrape_url(page_url)
            if not content:
                continue
            emails = extract_emails(content)
            if emails:
                hotel['email'] = emails[0]
                print(f"    + Email: {emails[0]}")
                found_email = True
                break
            if not hotel['phone']:
                phone = extract_phone(content)
                if phone:
                    hotel['phone'] = phone
                    print(f"    + Phone: {phone}")

        if not found_email:
            print(f"    — No email found")

        # Save progress after every 10 hotels
        if (i + 1) % 10 == 0:
            with open(raw_path, 'w', encoding='utf-8') as f:
                json.dump(hotels_list, f, indent=2, ensure_ascii=False)
            print(f"  [Progress saved — {i+1}/{len(hotels_list)}]")

        time.sleep(0.5)

    out_path = os.path.join(TMP_DIR, 'hotels_raw.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(hotels_list, f, indent=2, ensure_ascii=False)

    with_email = sum(1 for h in hotels_list if h['email'])
    with_phone = sum(1 for h in hotels_list if h['phone'])
    with_website = sum(1 for h in hotels_list if h['website'])

    print(f"\n=== Research Complete ===")
    print(f"  Total hotels:     {len(hotels_list)}")
    print(f"  With website:     {with_website}")
    print(f"  With email:       {with_email}")
    print(f"  With phone:       {with_phone}")
    print(f"  Output:           {out_path}")

if __name__ == "__main__":
    main()
