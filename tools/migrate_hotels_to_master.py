"""
Tool: migrate_hotels_to_master.py
Purpose: One-time migration of all leads from the Hotel Directory sheet into
         the Master AI Growth System Leads tab.

After running this, the Hotel Directory sheet is retired — the Master Sheet
becomes the single source of truth for all leads and outreach.

Run: python tools/migrate_hotels_to_master.py
     python tools/migrate_hotels_to_master.py --dry-run
"""

import json, os, sys, re, requests, argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))
import config as cfg
import write_to_master_sheet as wms

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

# Hotel Directory sheet ID (read-only after migration)
HOTEL_SHEET_ID = "1Jd03sw86hKqe-vckNw_443KGQqeS3MTHNM4AXQN4zfA"

# Hotel Directory column indices (0-based)
H_NAME      = 0
H_CITY      = 1
H_REGION    = 2
H_COUNTRY   = 3
H_PHONE     = 4
H_EMAIL     = 5
H_WEBSITE   = 6
H_CONTACT   = 7
H_ROLE      = 8
H_SOURCE    = 9
H_SCORE     = 10
H_REASON    = 11
H_MESSAGE   = 12
H_SUBJECT   = 13
H_STATUS    = 14
H_DATE      = 15
H_UPDATED   = 16
H_SENT_TS   = 17
H_NOTES     = 18

# Map Hotel Directory status → Master Sheet status
STATUS_MAP = {
    "Ready to Review":  "New",
    "No Email — Skip":  "No Email - Review",
    "No Email - Skip":  "No Email - Review",
    "Sent":             "Sent",
    "Approved to Send": "Approved to Send",
}


def get_token():
    creds_path = os.path.join(TMP_DIR, cfg.CREDS_SHEETS)
    with open(creds_path) as f:
        creds = json.load(f)
    resp = requests.post(TOKEN_URL, data={
        "client_id":     creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def read_hotel_directory(token):
    """Read all rows from the Hotel Directory sheet."""
    r = requests.get(
        f"{SHEETS_API}/{HOTEL_SHEET_ID}/values/{requests.utils.quote('Hotel Directory!A:S', safe='')}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    return rows


def hotel_row_to_lead(row):
    """Convert a Hotel Directory row to Master Sheet lead format."""
    while len(row) <= H_NOTES:
        row.append("")

    name    = row[H_NAME].strip()
    city    = row[H_CITY].strip()
    region  = row[H_REGION].strip()
    country = row[H_COUNTRY].strip() or "Ghana"
    phone   = row[H_PHONE].strip()
    email   = row[H_EMAIL].strip()
    website = row[H_WEBSITE].strip()
    contact = row[H_CONTACT].strip()
    role    = row[H_ROLE].strip()
    source  = row[H_SOURCE].strip()
    score   = row[H_SCORE].strip()
    reason  = row[H_REASON].strip()
    message = row[H_MESSAGE].strip()
    subject = row[H_SUBJECT].strip()
    status  = row[H_STATUS].strip()
    date    = row[H_DATE].strip()
    sent_ts = row[H_SENT_TS].strip()
    notes   = row[H_NOTES].strip()

    # Build contact name (combine person + role if both present)
    contact_name = contact
    if contact and role:
        contact_name = f"{contact} ({role})"
    elif role:
        contact_name = role

    # Build notes (combine original notes with location/phone data)
    notes_parts = []
    if city or region:
        notes_parts.append(f"Location: {', '.join(filter(None, [city, region]))}")
    if phone:
        notes_parts.append(f"Phone: {phone}")
    if reason:
        notes_parts.append(f"Score reason: {reason}")
    if notes:
        notes_parts.append(notes)
    if not email:
        notes_parts.append("No contact email found.")
    combined_notes = " | ".join(notes_parts)

    # Map status
    master_status = STATUS_MAP.get(status, "New" if email else "No Email - Review")

    # Use original date if present
    date_added = date or datetime.now().strftime("%Y-%m-%d")

    # Last Contacted: use sent timestamp if status is Sent
    last_contacted = sent_ts if master_status == "Sent" else ""

    return {
        "organisation_name": name,
        "country":           country,
        "sector":            "Hotel",
        "website":           website,
        "contact_name":      contact_name,
        "contact_email":     email,
        "linkedin":          "",
        "lead_source":       "SerpAPI Google Maps",
        "status":            master_status,
        "lead_score":        score,
        "last_contacted":    last_contacted,
        "notes":             combined_notes,
        "date_added":        date_added,
        "email_subject":     subject,
        "email_body":        message,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing to the Master Sheet")
    args = parser.parse_args()

    print("=== Hotel Directory Migration ===\n")
    print(f"Source: Hotel Directory (ID: {HOTEL_SHEET_ID})")
    print(f"Target: Master AI Growth System (ID: {cfg.MASTER_SHEET_ID})")
    if args.dry_run:
        print("MODE: DRY RUN\n")

    token = get_token()

    print("Reading Hotel Directory...")
    hotel_rows = read_hotel_directory(token)
    data_rows  = hotel_rows[1:]  # skip header
    print(f"Found {len(data_rows)} hotel rows.\n")

    print("Reading existing Master Sheet leads (for deduplication)...")
    existing = wms.sheets_get(token, cfg.MASTER_SHEET_ID, f"{cfg.LEADS_TAB}!A:R")
    print(f"Existing leads in master sheet: {max(0, len(existing) - 1)}\n")

    websites, emails, org_country = wms.build_existing_sets(existing)

    today      = datetime.now().strftime("%Y-%m-%d")
    new_rows   = []
    dup_log    = []
    no_email_log = []
    status_counts = {}

    for row in data_rows:
        lead = hotel_row_to_lead(row)
        org_name = lead["organisation_name"]
        if not org_name:
            continue

        dup, dup_reason = wms.is_duplicate(lead, websites, emails, org_country)
        if dup:
            dup_log.append(f"{org_name.encode('ascii','replace').decode()} -- {dup_reason}")
            continue

        if not lead["contact_email"]:
            no_email_log.append(org_name.encode("ascii","replace").decode())

        lead_id = wms.next_lead_id(existing, "Hotel")
        existing.append([lead_id])  # bump sequence for next iteration

        status = lead["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

        sheet_row = [
            lead_id,
            lead["organisation_name"],
            lead["country"],
            "Hotel",
            lead["website"],
            lead["contact_name"],
            lead["contact_email"],
            "",                         # LinkedIn
            lead["lead_source"],
            status,
            lead["lead_score"],
            "",                         # Outreach Angle
            lead["last_contacted"],
            "",                         # Next Follow Up
            lead["notes"],
            lead["date_added"],
            lead["email_subject"],
            lead["email_body"],
        ]
        new_rows.append(sheet_row)

        # Add to in-memory dedup sets
        wn = wms.normalise_website(lead["website"])
        en = wms.normalise_email(lead["contact_email"])
        on = (lead["organisation_name"].lower(), lead["country"].lower())
        if wn: websites.add(wn)
        if en: emails.add(en)
        if on[0]: org_country.add(on)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("--- Migration Summary ---")
    print(f"  Total hotel rows:  {len(data_rows)}")
    print(f"  Duplicates:        {len(dup_log)}")
    print(f"  New leads:         {len(new_rows)}")
    print(f"  Missing email:     {len(no_email_log)}")
    print(f"  Status breakdown:")
    for s, c in sorted(status_counts.items()):
        print(f"    {s}: {c}")

    if dup_log:
        print(f"\n  Duplicates skipped ({len(dup_log)}):")
        for d in dup_log[:10]:
            print(f"    - {d}")
        if len(dup_log) > 10:
            print(f"    ... and {len(dup_log)-10} more")

    if no_email_log:
        print(f"\n  No email (added as 'No Email - Review'):")
        for n in no_email_log[:5]:
            print(f"    - {n}")
        if len(no_email_log) > 5:
            print(f"    ... and {len(no_email_log)-5} more")

    if not new_rows:
        print("\nNothing new to migrate.")
        return

    if args.dry_run:
        print(f"\nDRY RUN: would append {len(new_rows)} hotel leads. First 3:")
        for row in new_rows[:3]:
            print(f"  {row[0]} | {row[1]} | {row[6] or '(no email)'} | {row[9]}")
        return

    print(f"\nAppending {len(new_rows)} hotels to Master Sheet...")
    # Write in batches of 50 to avoid payload limits
    batch = 50
    for i in range(0, len(new_rows), batch):
        chunk = new_rows[i:i + batch]
        wms.sheets_append(token, cfg.MASTER_SHEET_ID, cfg.LEADS_TAB, chunk)
        print(f"  Wrote rows {i+1}-{i+len(chunk)}")

    print(f"\nDone. {len(new_rows)} hotels migrated.")
    print(f"Master Sheet: https://docs.google.com/spreadsheets/d/{cfg.MASTER_SHEET_ID}")
    print("\nThe Hotel Directory sheet is now retired. Use the Master Sheet for all outreach.")


if __name__ == "__main__":
    main()
