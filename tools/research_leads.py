"""
Tool: research_leads.py
Purpose: Research leads for a given sector and country using SerpAPI + Firecrawl.
         Outputs .tmp/leads_for_master.json in Master AI Growth System format.

Usage:
  python tools/research_leads.py
  python tools/research_leads.py --sector NGO --country Ghana
  python tools/research_leads.py --sector Business --country Nigeria
  python tools/research_leads.py --sector Investor --country Ghana

Sector options: Hotel | University | NGO | Investor | Sponsor | Business | Rural Community
Country options: Ghana | Nigeria | Tanzania | Kenya | Rwanda

Config defaults come from tools/config.py (TARGET_SECTOR, TARGET_COUNTRY).
CLI args override config when provided.
"""

import requests, json, os, re, sys, time, argparse
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))
import config as cfg

load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))

SERPAPI_KEY   = os.getenv('SERPAPI_API_KEY')
FIRECRAWL_KEY = os.getenv('FIRECRAWL_API_KEY')

os.makedirs(TMP_DIR, exist_ok=True)


# ── SerpAPI ───────────────────────────────────────────────────────────────────

def search_maps(query, country_code="gh"):
    """Google Maps — best for local businesses, hotels, offices."""
    params = {"engine": "google_maps", "q": query, "api_key": SERPAPI_KEY,
              "type": "search", "hl": "en"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        return resp.json().get("local_results", [])
    except Exception as e:
        print(f"    SerpAPI Maps error: {e}")
        return []


def search_web(query, country_code="gh"):
    """Organic Google search — best for NGOs, investors, sponsors, universities."""
    params = {"engine": "google", "q": query, "api_key": SERPAPI_KEY,
              "num": 10, "gl": country_code, "hl": "en"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        return resp.json().get("organic_results", [])
    except Exception as e:
        print(f"    SerpAPI Web error: {e}")
        return []


# ── Firecrawl ─────────────────────────────────────────────────────────────────

def scrape_url(url):
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {FIRECRAWL_KEY}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]}, timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("markdown", "")
    except Exception as e:
        print(f"    Scrape error: {e}")
    return ""


# ── Extractors ────────────────────────────────────────────────────────────────

EMAIL_BLOCKED = [
    'example', 'test', 'noreply', 'no-reply', 'sentry', 'placeholder',
    'wixpress', 'squarespace', 'wordpress', 'yoursite', 'domain',
    'mymail@mailservice', 'contactus@savvycfo', 'privacy@', 'unsubscribe',
    'support@firecrawl', 'hello@firecrawl',
]

def extract_emails(text):
    found = re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)
    return [e for e in set(found) if not any(b in e.lower() for b in EMAIL_BLOCKED)]

def extract_linkedin(text):
    m = re.search(r'https?://(?:www\.)?linkedin\.com/(?:company|in|school)/[A-Za-z0-9\-_%]+', text)
    return m.group() if m else ""


# ── Search query templates ─────────────────────────────────────────────────────

SECTOR_QUERIES = {
    "Hotel": [
        "hotels in {city} {country}",
        "luxury hotels {city} {country}",
        "business hotels {city} {country}",
        "airport hotel {city} {country}",
        "boutique hotels {country}",
        "4 star hotels {country}",
    ],
    "University": [
        "universities in {country}",
        "private universities {country}",
        "technical universities {country}",
        "universities in {city} {country}",
        "polytechnic {country}",
    ],
    "NGO": [
        "NGOs in {country} education technology",
        "education non-profit organisations {country}",
        "digital inclusion NGO {country}",
        "development NGOs {city} {country}",
        "NGO health education {country}",
        "international NGO {country} office",
        "civil society organisations {country}",
        "charities {country} digital",
    ],
    "Investor": [
        "impact investors Africa {country}",
        "venture capital firm {country}",
        "angel investors {country} tech",
        "investment fund West Africa",
        "private equity firm {country}",
        "seed fund startup {country}",
        "development finance institution {country}",
        "social impact investment {country}",
    ],
    "Sponsor": [
        "corporate social responsibility {country}",
        "CSR programme company {country}",
        "corporate foundation {country}",
        "technology sponsor {country}",
        "digital inclusion sponsor Africa",
        "multinational company {country} CSR",
        "bank foundation {country}",
    ],
    "Business": [
        "technology company {city} {country}",
        "fintech startup {country}",
        "logistics company {country}",
        "manufacturing company {country}",
        "retail company {city} {country}",
        "healthcare company {country}",
        "media company {country}",
        "real estate company {country}",
    ],
    "Rural Community": [
        "district assembly {country}",
        "rural development organisation {country}",
        "community development {country}",
        "rural electrification connectivity {country}",
        "district council {country}",
        "local government {country} rural",
        "community foundation {country}",
    ],
}

COUNTRY_CITIES = {
    "Ghana":    ["Accra", "Kumasi", "Takoradi", "Tamale", "Cape Coast", "Tema"],
    "Nigeria":  ["Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan"],
    "Tanzania": ["Dar es Salaam", "Arusha", "Dodoma", "Mwanza"],
    "Kenya":    ["Nairobi", "Mombasa", "Kisumu"],
    "Rwanda":   ["Kigali"],
}

COUNTRY_CODES = {
    "Ghana": "gh", "Nigeria": "ng", "Tanzania": "tz",
    "Kenya": "ke", "Rwanda": "rw",
}

# Maps search for physical locations; web search for organisations
MAPS_SECTORS = {"Hotel", "Business"}


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_maps_result(r, sector, country):
    name = (r.get("title") or "").strip()
    if not name:
        return None
    address = r.get("address") or ""
    city = next((c for c in COUNTRY_CITIES.get(country, [])
                 if c.lower() in address.lower()), "")
    notes = " | ".join(filter(None, [
        f"Rating: {r['rating']}" if r.get("rating") else "",
        f"Reviews: {r['reviews']}" if r.get("reviews") else "",
        f"City: {city}" if city else "",
        f"Address: {address}" if address else "",
    ]))
    return {
        "organisation_name": name, "country": country, "sector": sector,
        "website": r.get("website") or "", "contact_name": "", "contact_email": "",
        "linkedin": "", "lead_source": "SerpAPI Google Maps", "notes": notes,
        "_city": city, "_phone": r.get("phone") or "",
        "_rating": r.get("rating") or "", "_reviews": r.get("reviews") or 0,
    }


def parse_web_result(r, sector, country):
    name = (r.get("title") or "").strip()
    if not name:
        return None
    name = re.split(r'\s*[\-\|]\s*', name)[0].strip()
    if len(name) > 80:
        name = name[:77] + "..."
    return {
        "organisation_name": name, "country": country, "sector": sector,
        "website": r.get("link") or "", "contact_name": "", "contact_email": "",
        "linkedin": "", "lead_source": "SerpAPI Google Search",
        "notes": (r.get("snippet") or "")[:200],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sector",  default=None, help="Override TARGET_SECTOR from config.py")
    parser.add_argument("--country", default=None, help="Override TARGET_COUNTRY from config.py")
    args = parser.parse_args()

    sector  = args.sector  or cfg.TARGET_SECTOR
    country = args.country or cfg.TARGET_COUNTRY
    cities  = COUNTRY_CITIES.get(country, [""])
    cc      = COUNTRY_CODES.get(country, "gh")
    use_maps = sector in MAPS_SECTORS

    print(f"=== Researching: {sector}s in {country} ===\n")

    leads = {}
    queries_template = SECTOR_QUERIES.get(sector, SECTOR_QUERIES["Business"])

    # Build query list
    queries = []
    for tmpl in queries_template:
        for city in (cities if "{city}" in tmpl else [""]):
            q = tmpl.format(sector=sector.lower(), country=country, city=city).strip()
            if q not in queries:
                queries.append(q)

    # Phase 1: Search
    print(f"Phase 1: Searching ({len(queries)} queries)...\n")
    for query in queries:
        print(f"  -> {query.encode('ascii','replace').decode()}")
        if use_maps:
            for r in search_maps(query, cc):
                lead = parse_maps_result(r, sector, country)
                if lead and lead["organisation_name"] not in leads:
                    leads[lead["organisation_name"]] = lead
        else:
            for r in search_web(query, cc):
                lead = parse_web_result(r, sector, country)
                if lead and lead["organisation_name"] not in leads:
                    leads[lead["organisation_name"]] = lead
        time.sleep(0.5)

    leads_list = list(leads.values())
    print(f"\nFound {len(leads_list)} unique leads.")

    raw_path = os.path.join(TMP_DIR, 'leads_raw_serpapi.json')
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(leads_list, f, indent=2, ensure_ascii=False)
    print(f"Checkpoint saved -> {raw_path}")

    # Phase 2: Scrape for emails
    print(f"\nPhase 2: Scraping for contact emails...\n")
    for i, lead in enumerate(leads_list):
        website = (lead.get("website") or "").strip()
        safe    = lead["organisation_name"].encode("ascii", "replace").decode()
        if not website:
            print(f"  [{i+1}/{len(leads_list)}] {safe} -- no website")
            continue

        base = website.split('?')[0].rstrip('/')
        for page in [website, base + '/contact', base + '/contact-us', base + '/about']:
            print(f"  [{i+1}/{len(leads_list)}] {safe} -- {page}")
            content = scrape_url(page)
            if not content:
                continue
            emails = extract_emails(content)
            if emails:
                lead["contact_email"] = emails[0]
                print(f"    + Email: {emails[0]}")
                if not lead.get("linkedin"):
                    lead["linkedin"] = extract_linkedin(content)
                break
        else:
            print(f"    - No email found")

        if (i + 1) % 10 == 0:
            with open(raw_path, 'w', encoding='utf-8') as f:
                json.dump(leads_list, f, indent=2, ensure_ascii=False)
            print(f"  [Checkpoint: {i+1}/{len(leads_list)}]")

        time.sleep(0.5)

    out_path = os.path.join(TMP_DIR, 'leads_for_master.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(leads_list, f, indent=2, ensure_ascii=False)

    with_email   = sum(1 for l in leads_list if l.get("contact_email"))
    with_website = sum(1 for l in leads_list if l.get("website"))
    print(f"\n=== Done: {sector}s in {country} ===")
    print(f"  Total:        {len(leads_list)}")
    print(f"  With website: {with_website}")
    print(f"  With email:   {with_email}")
    print(f"  No email:     {len(leads_list) - with_email}")
    print(f"\nNext: python tools/write_to_master_sheet.py")


if __name__ == "__main__":
    main()
