"""
Tool: generate_messages.py
Purpose: Generate personalised Email Subject + Email Body for every lead in the
         Master AI Growth System Leads tab that does not yet have one.

Run after research_leads.py + write_to_master_sheet.py to fill in messaging
so leads are ready for outreach approval.

Usage:
  python tools/generate_messages.py
  python tools/generate_messages.py --sector NGO       (only fill NGO rows)
  python tools/generate_messages.py --dry-run          (preview without writing)

Rules:
  - Only fills rows where Email Subject AND Email Body are both blank
  - Skips rows with missing email (can't send anyway)
  - Skips 'Previously Contacted' and 'Sent' rows
  - Never overwrites existing messages
"""

import json, os, sys, re, requests, argparse, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))
import config as cfg

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

# Column indices in Leads tab (0-based)
COL_NAME    = 1
COL_COUNTRY = 2
COL_SECTOR  = 3
COL_WEBSITE = 4
COL_EMAIL   = 6
COL_STATUS  = 9
COL_NOTES   = 14
COL_SUBJECT = 16
COL_BODY    = 17
COL_LETTER  = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

SKIP_STATUSES = {"Previously Contacted", "Sent", "No Email - Review", "Research Needed"}


# ── Google Sheets helpers ─────────────────────────────────────────────────────

def get_token():
    path = os.path.join(TMP_DIR, cfg.CREDS_SHEETS)
    with open(path) as f:
        creds = json.load(f)
    resp = requests.post(TOKEN_URL, data={
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"], "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def sheets_get(token, range_):
    r = requests.get(
        f"{SHEETS_API}/{cfg.MASTER_SHEET_ID}/values/{requests.utils.quote(range_, safe='')}",
        headers={"Authorization": f"Bearer {token}"}, timeout=30
    )
    r.raise_for_status()
    return r.json().get("values", [])


def sheets_batch_update(token, data):
    """Write multiple cell ranges in one API call."""
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    r = requests.post(
        f"{SHEETS_API}/{cfg.MASTER_SHEET_ID}/values:batchUpdate",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=60
    )
    if not r.ok:
        raise RuntimeError(f"Batch update failed {r.status_code}: {r.text[:200]}")


# ── Message templates per sector ──────────────────────────────────────────────

def shorten(name, max_len=35):
    """Trim long org names for subject lines."""
    name = re.split(r'\s*[\(\-\|]\s*', name)[0].strip()
    return name[:max_len].rstrip() + "..." if len(name) > max_len else name


def msg_hotel(name, country, notes):
    short = shorten(name)
    city  = ""
    m = re.search(r'City:\s*([^|]+)', notes or "")
    if m:
        city = m.group(1).strip()
    location = city or country

    subject = f"Managed WiFi Infrastructure for {short}"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We provide affordable, high-speed internet infrastructure for hotels, resorts, and commercial properties across Africa.

As guest expectations continue to rise, reliable and fast WiFi has moved from a perk to a baseline requirement. Many hotels across {location} are still running on legacy internet infrastructure that cannot keep up with today's guest demand — and it's quietly costing them in reviews and repeat bookings.

NovaLink replaces that entirely. We provide high-speed managed connectivity at costs well below what most properties currently pay their ISP, with full coverage design, installation, and ongoing management included. Our hotel clients typically see guest WiFi complaints drop to near zero within the first month.

I'd love to have a quick 15-minute conversation to understand your current connectivity setup and share how we've helped similar properties improve guest satisfaction while cutting internet costs.

Would you be open to a brief call this week or next?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_university(name, country, notes):
    short = shorten(name)
    subject = f"Campus Connectivity Partnership — {short}"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We partner with universities across Africa to deliver reliable, affordable, and scalable internet infrastructure — for campuses, student residences, and administrative blocks.

As digital learning becomes central to higher education, institutions are finding that their existing internet infrastructure is a bottleneck rather than an enabler. Slow speeds, unreliable uptime, and high ISP costs are limiting what students and staff can do — and making it harder to attract international partnerships and accreditations.

NovaLink provides managed campus-wide connectivity that scales with your institution. Our solutions are designed specifically for African universities — cost-effective, easy to manage, and built for high-density environments like lecture halls, libraries, and student accommodation.

I'd love to arrange a brief call to understand your current infrastructure and share how we've helped similar institutions across Africa.

Would you be open to a 15-minute conversation this week?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_ngo(name, country, notes):
    short = shorten(name)
    subject = f"Amplifying {short}'s Impact Through Connectivity"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We help NGOs and development organisations across Africa reduce the friction that poor internet connectivity creates in their day-to-day work and programme delivery.

We know that for many NGOs in {country}, unreliable internet is not a minor inconvenience — it disrupts field reporting, slows coordination between offices, limits access to digital tools, and reduces the impact you can deliver to beneficiaries.

NovaLink provides affordable, managed connectivity solutions tailored to NGO budgets and field realities. Whether your teams are in urban offices or field locations, we can design a connectivity plan that keeps everyone connected and your programmes running smoothly.

We also work with international donors and foundations to fund connectivity as part of programme infrastructure — something we'd be happy to explore with you.

I'd love to have a quick conversation about your connectivity situation and see if we can be useful to your work.

Would you be available for a 15-minute call this week or next?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_investor(name, country, notes):
    short = shorten(name)
    subject = f"Investment Opportunity — Internet Infrastructure Across Africa"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. I'm reaching out because we are exploring strategic partnerships and investment to scale our managed internet infrastructure business across the continent.

The opportunity is significant: Africa has some of the world's fastest-growing internet demand, yet the majority of businesses, institutions, and communities are still underserved — paying too much for unreliable connectivity. NovaLink steps into this gap as a managed service provider, delivering enterprise-grade internet to hotels, universities, businesses, and NGOs at costs that make sense for African markets.

Our model is built on recurring revenue, long-term institutional contracts, and a lean operational structure. We have early traction in Ghana and are ready to scale to Nigeria, Tanzania, and beyond.

I would welcome the opportunity to share our deck and have an introductory conversation about how {short} might be aligned with what we are building.

Would you be open to a brief call at your convenience?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_sponsor(name, country, notes):
    short = shorten(name)
    subject = f"CSR Partnership — Connecting Communities Across Africa"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. I'm reaching out to explore a potential CSR partnership that could deliver measurable, visible digital inclusion impact for {short} across {country} and beyond.

NovaLink Africa works to bring affordable, reliable internet connectivity to underserved communities — schools, rural health centres, community hubs, and small businesses that are currently excluded from the digital economy.

We are looking for forward-thinking corporate partners who want to go beyond token CSR activities and create real, lasting infrastructure impact. A sponsorship partnership with NovaLink could connect hundreds or thousands of people, generate authentic storytelling content, and align your brand with Africa's digital future.

We can structure partnerships around specific communities, geographies, or impact metrics — whatever makes the most sense for your CSR strategy.

I'd love to share more about what a partnership could look like and what the impact story would be for {short}.

Would you be open to a 20-minute conversation this week or next?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_business(name, country, notes):
    short = shorten(name)
    subject = f"Reliable Business Internet for {short} — NovaLink Africa"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We provide fast, reliable, and affordable managed internet solutions to growing businesses across Africa.

For businesses in {country}, internet downtime is not just an inconvenience — it directly costs productivity, delays transactions, and damages customer relationships. Yet most businesses are locked into ISP contracts that overpromise and underdeliver, with no real support when things go wrong.

NovaLink takes a different approach. We design your connectivity solution around your actual business needs, install it properly, and manage it on an ongoing basis so your team never has to troubleshoot a router again. Our clients typically cut their internet costs by 20–40% while getting significantly better reliability and speeds.

I'd love to understand your current setup and see whether we can offer something meaningfully better.

Would you be open to a quick 15-minute call this week?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


def msg_rural_community(name, country, notes):
    short = shorten(name)
    subject = f"Bringing Reliable Connectivity to {short}"
    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We work with district assemblies, local councils, and community development organisations to bring affordable, reliable internet connectivity to underserved communities across Africa.

Access to reliable internet is no longer a luxury — it is the foundation for quality education, accessible healthcare, economic opportunity, and effective governance. Yet many communities across {country} remain digitally excluded, not because connectivity is impossible, but because the existing solutions are too expensive or poorly designed for local realities.

NovaLink specialises in building sustainable connectivity infrastructure for communities like yours — connecting schools, health centres, markets, and administrative offices in a way that is affordable, maintainable, and impactful.

We work with community leaders, NGOs, and government bodies to design solutions that fit local needs and budgets, and we actively explore grant and donor funding where available.

I would welcome the opportunity to speak with your team about the connectivity needs in your area and how NovaLink might be able to help.

Would you be available for a short introductory call?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
novalinkafrica@gmail.com
https://nova-link-africa-website.vercel.app/"""
    return subject, body


SECTOR_GENERATORS = {
    "Hotel":            msg_hotel,
    "University":       msg_university,
    "NGO":              msg_ngo,
    "Investor":         msg_investor,
    "Sponsor":          msg_sponsor,
    "Business":         msg_business,
    "Rural Community":  msg_rural_community,
}


def generate(name, sector, country, notes):
    fn = SECTOR_GENERATORS.get(sector)
    if fn:
        return fn(name, country, notes)
    return (f"Connectivity Partnership — {shorten(name)}",
            f"Dear {name} Team,\n\nNovaLink Africa would love to connect.\n\nWarm regards,\nGerald Bonsu")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sector",  default=None, help="Only generate for this sector")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    print("=== Generate Messages ===\n")
    token = get_token()

    print("Reading Master Sheet leads...")
    rows = sheets_get(token, f"{cfg.LEADS_TAB}!A:R")
    if len(rows) <= 1:
        print("Sheet is empty.")
        return

    updates    = []
    skipped    = 0
    generated  = 0
    no_email   = 0

    for sheet_row, row in enumerate(rows[1:], start=2):
        while len(row) <= COL_BODY:
            row.append("")

        name    = row[COL_NAME].strip()
        country = row[COL_COUNTRY].strip()
        sector  = row[COL_SECTOR].strip()
        email   = row[COL_EMAIL].strip()
        status  = row[COL_STATUS].strip()
        notes   = row[COL_NOTES].strip()
        subject = row[COL_SUBJECT].strip()
        body    = row[COL_BODY].strip()

        # Filter by sector if requested
        if args.sector and sector != args.sector:
            skipped += 1
            continue

        # Skip rows that don't need messages
        if status in SKIP_STATUSES:
            skipped += 1
            continue

        # Skip if already has a message
        if subject and body:
            skipped += 1
            continue

        # Skip if no email (can't send anyway; user can add email + regenerate)
        if not email:
            no_email += 1
            continue

        subj, bod = generate(name, sector, country, notes)
        safe = name.encode("ascii", "replace").decode()
        print(f"  [{sector}] {safe[:50]}")

        updates.append({
            "range": f"{cfg.LEADS_TAB}!{COL_LETTER[COL_SUBJECT]}{sheet_row}",
            "values": [[subj]]
        })
        updates.append({
            "range": f"{cfg.LEADS_TAB}!{COL_LETTER[COL_BODY]}{sheet_row}",
            "values": [[bod]]
        })
        generated += 1

    print(f"\n--- Summary ---")
    print(f"  Generated:  {generated}")
    print(f"  Skipped:    {skipped}  (already have messages, wrong sector, or non-sendable status)")
    print(f"  No email:   {no_email}  (message not generated — no email address)")

    if not updates:
        print("\nNothing to update.")
        return

    if args.dry_run:
        print(f"\nDRY RUN: would write {len(updates)} cells. Not writing.")
        return

    print(f"\nWriting {len(updates)} cells to sheet (in batches)...")
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        sheets_batch_update(token, updates[i:i + batch_size])
        print(f"  Wrote batch {i//batch_size + 1}")
        time.sleep(0.3)

    print(f"\nDone. {generated} leads now have Email Subject + Email Body.")
    print("Set Status = 'Approved to Send' in the sheet to trigger outreach.")


if __name__ == "__main__":
    main()
