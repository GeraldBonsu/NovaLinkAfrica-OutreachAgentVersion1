"""
Tool: write_to_master_sheet.py
Purpose: Read leads from .tmp/leads_for_master.json, deduplicate against the
         Master AI Growth System Leads tab, and append only new leads.

Deduplication order:
  1. Website (normalised — strips protocol, www, trailing slash)
  2. Contact Email (lowercase)
  3. Organisation Name (lowercase) + Country (lowercase)

Lead ID format: NVL-{SECTOR_CODE}-{YYYY}-{NNNN}
  Example: NVL-HTL-2026-0001, NVL-UNI-2026-0042

Usage:
  python tools/write_to_master_sheet.py
  python tools/write_to_master_sheet.py --input .tmp/my_leads.json

Safety:
  - NEVER overwrites existing rows
  - NEVER deletes rows
  - Dry-run mode: python tools/write_to_master_sheet.py --dry-run
"""

import json, os, sys, re, time, requests, argparse
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))
import config as cfg

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

# Leads tab column order (must match the sheet header exactly)
LEADS_COLUMNS = [
    "Lead ID", "Organisation Name", "Country", "Sector", "Website",
    "Contact Name", "Contact Email", "LinkedIn", "Lead Source", "Status",
    "Lead Score", "Outreach Angle", "Last Contacted", "Next Follow Up",
    "Notes", "Date Added", "Email Subject", "Email Body"
]
COL = {name: i for i, name in enumerate(LEADS_COLUMNS)}


# ── Google Sheets helpers ─────────────────────────────────────────────────────

def get_token():
    creds_path = os.path.join(TMP_DIR, cfg.CREDS_SHEETS)
    if not os.path.exists(creds_path):
        print(f"ERROR: {creds_path} not found. Run: python tools/export_creds.py")
        sys.exit(1)
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


def sheets_get(token, sid, range_):
    """Read a range from Google Sheets. Returns list of rows (each row is a list)."""
    url = f"{SHEETS_API}/{sid}/values/{requests.utils.quote(range_, safe='')}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Sheets read failed {r.status_code}: {r.text[:200]}")
    return r.json().get("values", [])


def sheets_append(token, sid, tab, rows):
    """Append rows to the sheet (will never overwrite existing data)."""
    range_ = f"{tab}!A1"
    url = (f"{SHEETS_API}/{sid}/values/{requests.utils.quote(range_, safe='')}"
           f":append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS")
    r = requests.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      json={"values": rows}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Sheets append failed {r.status_code}: {r.text[:200]}")
    return r.json()


# ── Deduplication helpers ─────────────────────────────────────────────────────

def normalise_website(url):
    """Strip protocol, www, and trailing slashes for comparison."""
    if not url:
        return ""
    url = url.lower().strip()
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^www\.', '', url)
    return url.rstrip('/')


def normalise_email(email):
    return (email or "").lower().strip()


def build_existing_sets(rows):
    """
    Build lookup sets from existing sheet rows for fast dedup.
    Returns: (websites, emails, org_country_pairs)
    """
    websites, emails, org_country = set(), set(), set()
    for row in rows[1:]:  # skip header
        while len(row) < len(LEADS_COLUMNS):
            row.append("")
        w = normalise_website(row[COL["Website"]])
        e = normalise_email(row[COL["Contact Email"]])
        o = (row[COL["Organisation Name"]].lower().strip(),
             row[COL["Country"]].lower().strip())
        if w:
            websites.add(w)
        if e:
            emails.add(e)
        if o[0]:
            org_country.add(o)
    return websites, emails, org_country


def is_duplicate(lead, websites, emails, org_country):
    """Return (True, reason) if lead already exists, else (False, '')."""
    w = normalise_website(lead.get("website", ""))
    e = normalise_email(lead.get("contact_email", ""))
    o = (lead.get("organisation_name", "").lower().strip(),
         lead.get("country", "").lower().strip())

    if w and w in websites:
        return True, f"website match ({w})"
    if e and e in emails:
        return True, f"email match ({e})"
    if o[0] and o in org_country:
        return True, f"org+country match ({o[0]}, {o[1]})"
    return False, ""


# ── Lead ID generation ────────────────────────────────────────────────────────

def next_lead_id(existing_rows, sector):
    """
    Find the highest existing sequence number for this sector+year,
    then return the next ID in sequence.
    """
    year = datetime.now().strftime("%Y")
    code = cfg.SECTOR_CODES.get(sector, "GEN")
    prefix = f"NVL-{code}-{year}-"
    max_seq = 0

    for row in existing_rows[1:]:
        if row and row[0].startswith(prefix):
            try:
                seq = int(row[0].replace(prefix, ""))
                max_seq = max(max_seq, seq)
            except ValueError:
                pass

    return f"{prefix}{max_seq + 1:04d}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(TMP_DIR, "leads_for_master.json"),
                        help="Path to JSON file of leads to import")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be added without writing to the sheet")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        print("Run research_leads.py first, or pass --input path/to/leads.json")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        incoming = json.load(f)

    print(f"Input file:  {args.input}")
    print(f"Leads found: {len(incoming)}")
    print(f"Sheet ID:    {cfg.MASTER_SHEET_ID}")
    print(f"Tab:         {cfg.LEADS_TAB}")
    if args.dry_run:
        print("MODE:        DRY RUN (no writes)\n")

    print("\nLoading credentials and reading existing leads...")
    token = get_token()

    try:
        existing = sheets_get(token, cfg.MASTER_SHEET_ID, f"{cfg.LEADS_TAB}!A:P")
    except RuntimeError as e:
        print(f"ERROR reading sheet: {e}")
        sys.exit(1)

    print(f"Existing leads in sheet: {max(0, len(existing) - 1)}")

    websites, emails, org_country = build_existing_sets(existing)

    today = datetime.now().strftime("%Y-%m-%d")
    new_rows       = []
    duplicate_log  = []
    no_email_log   = []
    error_log      = []
    seq_offset     = 0  # tracks IDs assigned this run

    for lead in incoming:
        org_name = (lead.get("organisation_name") or "").strip()
        if not org_name:
            error_log.append("Skipped: missing organisation_name")
            continue

        # Check duplicate
        dup, dup_reason = is_duplicate(lead, websites, emails, org_country)
        if dup:
            safe = org_name.encode("ascii", "replace").decode()
            duplicate_log.append(f"{safe} — {dup_reason}")
            continue

        # Note missing email
        email = (lead.get("contact_email") or "").strip()
        if not email:
            no_email_log.append(org_name.encode("ascii", "replace").decode())

        # Determine status
        if email:
            status = "New"
        elif (lead.get("website") or "").strip():
            status = "No Email - Review"
        else:
            status = "Research Needed"

        # Generate Lead ID
        # Temporarily add to sets so IDs within this batch don't collide
        seq_offset += 1
        lead_id = next_lead_id(existing, lead.get("sector", cfg.TARGET_SECTOR))
        # Bump sequence for next iteration within this batch
        existing.append([lead_id])  # dummy row so next_lead_id increments

        website = (lead.get("website") or "").strip()
        contact_email = email
        notes = (lead.get("notes") or "").strip()
        if not email and website:
            if notes:
                notes += " | No contact email found."
            else:
                notes = "No contact email found."

        row = [
            lead_id,                                            # Lead ID
            org_name,                                           # Organisation Name
            (lead.get("country") or cfg.TARGET_COUNTRY).strip(), # Country
            (lead.get("sector") or cfg.TARGET_SECTOR).strip(),  # Sector
            website,                                            # Website
            (lead.get("contact_name") or "").strip(),           # Contact Name
            contact_email,                                      # Contact Email
            (lead.get("linkedin") or "").strip(),               # LinkedIn
            (lead.get("lead_source") or "Web Search").strip(),  # Lead Source
            status,                                             # Status
            "",                                                 # Lead Score (blank — fill via scoring step)
            "",                                                 # Outreach Angle (blank — fill before sending)
            "",                                                 # Last Contacted (blank)
            "",                                                 # Next Follow Up (blank)
            notes,                                              # Notes
            today,                                              # Date Added
            "",                                                 # Email Subject (blank — fill before sending)
            "",                                                 # Email Body (blank — fill before sending)
        ]
        new_rows.append(row)

        # Add to in-memory sets to prevent duplicates within this batch
        w_norm = normalise_website(website)
        e_norm = normalise_email(contact_email)
        o_norm = (org_name.lower(), (lead.get("country") or cfg.TARGET_COUNTRY).lower())
        if w_norm: websites.add(w_norm)
        if e_norm: emails.add(e_norm)
        if o_norm[0]: org_country.add(o_norm)

    # ── Console summary ───────────────────────────────────────────────────────
    print(f"\n--- Summary ---")
    print(f"  Total in file:  {len(incoming)}")
    print(f"  Duplicates:     {len(duplicate_log)}")
    print(f"  Errors/skipped: {len(error_log)}")
    print(f"  New leads:      {len(new_rows)}")
    print(f"  Missing email:  {len(no_email_log)}")

    if duplicate_log:
        print("\n  Duplicates skipped:")
        for d in duplicate_log:
            print(f"    - {d}")

    if no_email_log:
        print("\n  Added but missing email (marked 'No Email - Review'):")
        for n in no_email_log:
            print(f"    - {n}")

    if error_log:
        print("\n  Errors:")
        for e in error_log:
            print(f"    ! {e}")

    if not new_rows:
        print("\nNothing new to add.")
        return

    # Apply daily limit
    if cfg.DAILY_LEAD_LIMIT and len(new_rows) > cfg.DAILY_LEAD_LIMIT:
        print(f"\nDAILY_LEAD_LIMIT ({cfg.DAILY_LEAD_LIMIT}) applied — trimming from {len(new_rows)}.")
        new_rows = new_rows[:cfg.DAILY_LEAD_LIMIT]

    if args.dry_run:
        print(f"\nDRY RUN: would append {len(new_rows)} rows. First 3:")
        for row in new_rows[:3]:
            print(f"  {row[0]} | {row[1]} | {row[6] or '(no email)'}")
        return

    print(f"\nAppending {len(new_rows)} new leads to sheet...")
    try:
        sheets_append(token, cfg.MASTER_SHEET_ID, cfg.LEADS_TAB, new_rows)
        print(f"Done. {len(new_rows)} leads added.")
    except RuntimeError as e:
        print(f"ERROR writing to sheet: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
