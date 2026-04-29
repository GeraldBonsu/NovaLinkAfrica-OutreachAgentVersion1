"""
Tool: research_leads.py
Purpose: Research leads for a given sector and country using SerpAPI + Firecrawl.
         Outputs .tmp/leads_for_master.json in Master AI Growth System format.

Configuration is in tools/config.py:
  - TARGET_SECTOR  (Hotel, University, NGO, Investor, Sponsor, Business)
  - TARGET_COUNTRY (Ghana, Nigeria, Tanzania, ...)
  - DAILY_LEAD_LIMIT

Run: python tools/research_leads.py
Then: python tools/write_to_master_sheet.py
"""

import requests, json, os, re, sys, time
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


# ── SerpAPI search ────────────────────────────────────────────────────────────

def search_maps(query, country_code="gh"):
    """Google Maps search — best for local businesses (hotels, schools, offices)."""
    params = {
        "engine":  "google_maps",
        "q":       query,
        "api_key": SERPAPI_KEY,
        "type":    "search",
        "hl":      "en",
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        return resp.json().get("local_results", [])
    except Exception as e:
        print(f"    SerpAPI Maps error: {e}")
        return []


def search_web(query, country_code="gh"):
    """Organic Google search — useful for NGOs, investors, sponsors."""
    params = {
        "engine":  "google",
        "q":       query,
        "api_key": SERPAPI_KEY,
        "num":     10,
        "gl":      country_code,
        "hl":      "en",
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        return resp.json().get("organic_results", [])
    except Exception as e:
        print(f"    SerpAPI Web error: {e}")
        return []


# ── Firecrawl scrape ──────────────────────────────────────────────────────────

def scrape_url(url):
    """Scrape a page via Firecrawl REST API and return markdown text."""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {FIRECRAWL_KEY}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]},
            timeout=30
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
    'mymail@mailservice', 'contactus@savvycfo', 'privacy@',
]

def extract_emails(text):
    pattern = r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
    found = re.findall(pattern, text)
    return [e for e in set(found)
            if not any(b in e.lower() for b in EMAIL_BLOCKED)]


def extract_linkedin(text):
    m = re.search(r'https?://(?:www\.)?linkedin\.com/(?:company|in|school)/[A-Za-z0-9\-_]+', text)
    return m.group() if m else ""


# ── Search query templates per sector ─────────────────────────────────────────

SECTOR_QUERIES = {
    "Hotel": [
        "{sector}s in {city} {country}",
        "luxury {sector}s {city} {country}",
        "business {sector}s {city} {country}",
        "airport {sector} {city} {country}",
        "boutique {sector}s {country}",
        "4 star {sector}s {country}",
    ],
    "University": [
        "universities in {country}",
        "private universities {country}",
        "technical universities {country}",
        "universities in {city} {country}",
    ],
    "NGO": [
        "NGOs in {country}",
        "non-governmental organisations {country}",
        "development NGOs {country}",
        "education NGOs {country}",
        "technology NGOs {country}",
    ],
    "Investor": [
        "impact investors {country}",
        "venture capital {country}",
        "private equity {country}",
        "angel investors {country}",
    ],
    "Sponsor": [
        "corporate sponsors {country}",
        "corporate social responsibility companies {country}",
        "event sponsors {country}",
    ],
    "Business": [
        "SMEs {country}",
        "medium enterprises {country}",
        "tech companies {country}",
        "startups {country}",
    ],
}

# Cities per country for multi-city searches
COUNTRY_CITIES = {
    "Ghana":    ["Accra", "Kumasi", "Takoradi", "Tamale", "Cape Coast", "Tema"],
    "Nigeria":  ["Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan"],
    "Tanzania": ["Dar es Salaam", "Arusha", "Dodoma", "Mwanza"],
    "Kenya":    ["Nairobi", "Mombasa", "Kisumu"],
    "Rwanda":   ["Kigali"],
}

# Country code for SerpAPI gl param
COUNTRY_CODES = {
    "Ghana": "gh", "Nigeria": "ng", "Tanzania": "tz",
    "Kenya": "ke", "Rwanda": "rw",
}

# Whether this sector uses Maps search (local businesses) or Web search (orgs)
MAPS_SECTORS = {"Hotel", "Business"}


# ── Sector-specific parsers ───────────────────────────────────────────────────

def parse_maps_result(r, sector, country):
    """Parse a SerpAPI google_maps result into master sheet lead format."""
    name = (r.get("title") or "").strip()
    if not name:
        return None
    address = r.get("address") or ""
    city = ""
    cities = COUNTRY_CITIES.get(country, [])
    for c in cities:
        if c.lower() in address.lower():
            city = c
            break

    notes_parts = []
    if r.get("rating"):
        notes_parts.append(f"Rating: {r['rating']}")
    if r.get("reviews"):
        notes_parts.append(f"Reviews: {r['reviews']}")
    if city:
        notes_parts.append(f"City: {city}")
    if address:
        notes_parts.append(f"Address: {address}")

    return {
        "organisation_name": name,
        "country":           country,
        "sector":            sector,
        "website":           r.get("website") or "",
        "contact_name":      "",
        "contact_email":     "",
        "linkedin":          "",
        "lead_source":       "SerpAPI Google Maps",
        "notes":             " | ".join(notes_parts),
        "_phone":            r.get("phone") or "",
        "_address":          address,
        "_city":             city,
    }


def parse_web_result(r, sector, country):
    """Parse a SerpAPI organic web result into master sheet lead format."""
    name = (r.get("title") or "").strip()
    if not name:
        return None
    # Strip site name from title (e.g. "Ashesi University - Home | Ashesi" -> "Ashesi University")
    name = re.split(r'\s*[\-\|]\s*', name)[0].strip()

    return {
        "organisation_name": name,
        "country":           country,
        "sector":            sector,
        "website":           r.get("link") or "",
        "contact_name":      "",
        "contact_email":     "",
        "linkedin":          "",
        "lead_source":       "SerpAPI Google Search",
        "notes":             (r.get("snippet") or "")[:200],
        "_snippet":          r.get("snippet") or "",
    }


# ── Main research flow ────────────────────────────────────────────────────────

def main():
    sector  = cfg.TARGET_SECTOR
    country = cfg.TARGET_COUNTRY
    cities  = COUNTRY_CITIES.get(country, [""])
    cc      = COUNTRY_CODES.get(country, "")
    use_maps = sector in MAPS_SECTORS

    queries_template = SECTOR_QUERIES.get(sector, SECTOR_QUERIES["Hotel"])

    print(f"=== Phase 1: Searching for {sector}s in {country} via SerpAPI ===\n")

    leads = {}  # keyed by name (dedup within this run)

    # Build search queries
    queries = []
    for tmpl in queries_template:
        for city in cities:
            q = tmpl.format(sector=sector.lower(), country=country,
                            city=city).strip()
            if q not in queries:
                queries.append(q)

    for query in queries:
        safe_q = query.encode("ascii", "replace").decode()
        print(f"  Searching: {safe_q}")
        if use_maps:
            results = search_maps(query, cc)
            for r in results:
                lead = parse_maps_result(r, sector, country)
                if lead and lead["organisation_name"] not in leads:
                    leads[lead["organisation_name"]] = lead
        else:
            results = search_web(query, cc)
            for r in results:
                lead = parse_web_result(r, sector, country)
                if lead and lead["organisation_name"] not in leads:
                    leads[lead["organisation_name"]] = lead
        time.sleep(0.5)

    leads_list = list(leads.values())
    print(f"\nFound {len(leads_list)} unique {sector.lower()}s.")

    # Save raw SerpAPI results immediately (checkpoint)
    raw_path = os.path.join(TMP_DIR, 'leads_raw_serpapi.json')
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(leads_list, f, indent=2, ensure_ascii=False)
    print(f"SerpAPI checkpoint saved -> {raw_path}")

    # ── Phase 2: Firecrawl website scraping for emails ──────────────────────
    print(f"\n=== Phase 2: Scraping websites for emails (Firecrawl) ===\n")

    for i, lead in enumerate(leads_list):
        website = lead.get("website", "").strip()
        if not website:
            safe = lead["organisation_name"].encode("ascii","replace").decode()
            print(f"  [{i+1}/{len(leads_list)}] {safe} -- no website, skipping")
            continue

        base_url  = website.split('?')[0].rstrip('/')
        pages     = [website, base_url + '/contact', base_url + '/contact-us']
        found_email = False

        for page_url in pages:
            safe = lead["organisation_name"].encode("ascii","replace").decode()
            print(f"  [{i+1}/{len(leads_list)}] {safe} -- scraping {page_url}")
            content = scrape_url(page_url)
            if not content:
                continue

            emails = extract_emails(content)
            if emails:
                lead["contact_email"] = emails[0]
                print(f"    + Email: {emails[0]}")
                found_email = True

                # Try to pick up LinkedIn too
                if not lead.get("linkedin"):
                    lead["linkedin"] = extract_linkedin(content)

                break

        if not found_email:
            print(f"    - No email found")

        # Save progress every 10 leads
        if (i + 1) % 10 == 0:
            with open(raw_path, 'w', encoding='utf-8') as f:
                json.dump(leads_list, f, indent=2, ensure_ascii=False)
            print(f"  [Progress saved -- {i+1}/{len(leads_list)}]")

        time.sleep(0.5)

    # ── Save final output ─────────────────────────────────────────────────────
    out_path = os.path.join(TMP_DIR, 'leads_for_master.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(leads_list, f, indent=2, ensure_ascii=False)

    with_email   = sum(1 for l in leads_list if l.get("contact_email"))
    with_website = sum(1 for l in leads_list if l.get("website"))
    no_email     = [l["organisation_name"] for l in leads_list if not l.get("contact_email")]

    print(f"\n=== Research Complete ===")
    print(f"  Total found:    {len(leads_list)}")
    print(f"  With website:   {with_website}")
    print(f"  With email:     {with_email}")
    print(f"  Missing email:  {len(no_email)}")
    if no_email:
        print(f"  No-email leads (will be added as 'No Email - Review'):")
        for name in no_email[:10]:
            print(f"    - {name.encode('ascii','replace').decode()}")
        if len(no_email) > 10:
            print(f"    ... and {len(no_email)-10} more")
    print(f"\n  Output -> {out_path}")
    print(f"\nNext step: python tools/write_to_master_sheet.py")


if __name__ == "__main__":
    main()
