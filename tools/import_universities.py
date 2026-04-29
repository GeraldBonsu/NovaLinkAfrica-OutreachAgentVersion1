"""
Tool: import_universities.py
Purpose: One-time import of the University Outreach CRM xlsx into the
         Master AI Growth System Leads tab.

These universities were previously contacted via appaubonsu@gmail.com through
an n8n workflow. They are imported with Status = "Previously Contacted" and
notes indicating they should now be re-contacted via novalinkafrica@gmail.com,
with IT/ICT email CC'd alongside grindhardcircle@gmail.com.

Run once: python tools/import_universities.py
          python tools/import_universities.py --dry-run
"""

import sys, os, json, openpyxl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))

import argparse
import write_to_master_sheet as wms
import config as cfg

# Path to the xlsx — relative to the Website Building folder
XLSX_PATH = os.path.join(
    BASE_DIR, '..', 'Novalink',
    'NovaLink_University_Outreach_CRM (1).xlsx'
)

# University CRM column positions (0-based)
U_NAME         = 0   # University Name
U_LOCATION     = 1   # Location (city)
U_COUNTRY      = 2   # Country
U_GEN_EMAIL    = 3   # General Email
U_ICT_EMAIL    = 4   # IT/ICT Email
U_KEY_CONTACT  = 5   # Key Contact (Role)
U_LINKEDIN     = 6   # LinkedIn
U_PHONE        = 7   # Phone
U_PRIORITY     = 8   # Priority
U_STATUS       = 9   # Status
U_LAST_CONTACT = 10  # Last Contacted
U_NOTES        = 12  # Notes
U_WEBSITE      = 20  # Website (col U in xlsx)


def parse_xlsx():
    """Read the University Outreach CRM xlsx and return a list of lead dicts."""
    if not os.path.exists(XLSX_PATH):
        print(f"ERROR: xlsx not found at: {XLSX_PATH}")
        sys.exit(1)

    wb  = openpyxl.load_workbook(XLSX_PATH)
    ws  = wb['University Outreach CRM']
    rows = list(ws.iter_rows(values_only=True))

    leads = []
    seen_names = set()  # deduplicate within xlsx (it has some duplicates)

    for row in rows[1:]:  # skip header
        # Pad short rows
        row = list(row) + [''] * 25
        row = [str(v).strip() if v else '' for v in row]

        name = row[U_NAME]
        if not name:
            continue

        # Deduplicate by name within the xlsx itself
        name_key = name.lower()
        if name_key in seen_names:
            print(f"  [xlsx dup] Skipping duplicate: {name}")
            continue
        seen_names.add(name_key)

        country      = row[U_COUNTRY] or "Ghana"
        gen_email    = row[U_GEN_EMAIL]
        ict_email    = row[U_ICT_EMAIL]
        key_contact  = row[U_KEY_CONTACT]
        linkedin     = row[U_LINKEDIN]
        website      = row[U_WEBSITE]
        location     = row[U_LOCATION]

        # Build notes
        notes_parts = [
            "Previously contacted via appaubonsu@gmail.com (n8n workflow, 2026-04-28).",
            "To be re-contacted via novalinkafrica@gmail.com.",
        ]
        if ict_email:
            notes_parts.append(
                f"IT/ICT email: {ict_email} — CC grindhardcircle@gmail.com on outreach."
            )
        if gen_email and ict_email:
            notes_parts.append(f"General email: {gen_email}.")
        if location:
            notes_parts.append(f"Location: {location}.")
        notes = " ".join(notes_parts)

        # Primary contact email = general email (ICT captured in notes)
        contact_email = gen_email

        # Clean up LinkedIn — strip "Search: ..." placeholder values
        if linkedin and linkedin.lower().startswith("search:"):
            linkedin = ""

        lead = {
            "organisation_name": name,
            "country":           country,
            "sector":            "University",
            "website":           website,
            "contact_name":      key_contact,
            "contact_email":     contact_email,
            "linkedin":          linkedin,
            "lead_source":       "University Outreach CRM Import",
            "notes":             notes,
            "_status_override":  "Previously Contacted",
        }
        leads.append(lead)

    return leads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing to the sheet")
    args = parser.parse_args()

    print("=== University CRM Import ===\n")
    print(f"Reading: {XLSX_PATH}")
    leads = parse_xlsx()
    print(f"Parsed {len(leads)} universities from xlsx.\n")

    if args.dry_run:
        print("DRY RUN mode — showing first 5 leads:\n")
        for l in leads[:5]:
            print(f"  {l['organisation_name']} | {l['country']} | {l['contact_email'] or '(no email)'}")
            print(f"    Notes: {l['notes'][:80]}...")
        print(f"\n(Total {len(leads)} would be processed — run without --dry-run to import)")
        return

    # Save to leads_for_master.json so write_to_master_sheet can process it
    # But override status field after the fact
    out_path = os.path.join(TMP_DIR, 'leads_for_master.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)
    print(f"Saved leads to {out_path}")

    # Monkey-patch the status determination in write_to_master_sheet
    # by overriding its main() to respect _status_override field
    print("\nRunning deduplication and sheet write...\n")

    import requests
    from datetime import datetime

    token = wms.get_token()
    existing = wms.sheets_get(token, cfg.MASTER_SHEET_ID, f"{cfg.LEADS_TAB}!A:P")
    print(f"Existing leads in sheet: {max(0, len(existing) - 1)}")

    websites, emails, org_country = wms.build_existing_sets(existing)

    today      = datetime.now().strftime("%Y-%m-%d")
    new_rows   = []
    dup_log    = []
    no_email_log = []

    for lead in leads:
        org_name = lead["organisation_name"].strip()
        dup, dup_reason = wms.is_duplicate(lead, websites, emails, org_country)
        if dup:
            dup_log.append(f"{org_name.encode('ascii','replace').decode()} -- {dup_reason}")
            continue

        email = (lead.get("contact_email") or "").strip()
        if not email:
            no_email_log.append(org_name.encode("ascii","replace").decode())

        # Use _status_override if present
        status = lead.get("_status_override") or ("New" if email else "No Email - Review")

        lead_id = wms.next_lead_id(existing, "University")
        existing.append([lead_id])  # bump sequence

        website = (lead.get("website") or "").strip()
        notes   = (lead.get("notes") or "").strip()
        if not email and website and "No contact email" not in notes:
            notes += " | No contact email found." if notes else "No contact email found."

        row = [
            lead_id,
            org_name,
            (lead.get("country") or "Ghana").strip(),
            "University",
            website,
            (lead.get("contact_name") or "").strip(),
            email,
            (lead.get("linkedin") or "").strip(),
            (lead.get("lead_source") or "University Outreach CRM Import").strip(),
            status,
            "", "", "", "",  # Lead Score, Outreach Angle, Last Contacted, Next Follow Up
            notes,
            today,
        ]
        new_rows.append(row)

        # Track in-memory sets
        wn = wms.normalise_website(website)
        en = wms.normalise_email(email)
        on = (org_name.lower(), lead.get("country", "Ghana").lower())
        if wn: websites.add(wn)
        if en: emails.add(en)
        if on[0]: org_country.add(on)

    print(f"--- Summary ---")
    print(f"  Total in xlsx:   {len(leads)}")
    print(f"  Duplicates:      {len(dup_log)}")
    print(f"  New leads:       {len(new_rows)}")
    print(f"  Missing email:   {len(no_email_log)}")

    if dup_log:
        print("\n  Duplicates skipped:")
        for d in dup_log:
            print(f"    - {d}")
    if no_email_log:
        print("\n  No email (added as 'No Email - Review' or 'Previously Contacted'):")
        for n in no_email_log:
            print(f"    - {n}")

    if not new_rows:
        print("\nNothing new to add.")
        return

    print(f"\nAppending {len(new_rows)} university leads to Master Sheet...")
    wms.sheets_append(token, cfg.MASTER_SHEET_ID, cfg.LEADS_TAB, new_rows)
    print(f"Done. {len(new_rows)} universities imported with Status = 'Previously Contacted'.")
    print(f"\nSheet: https://docs.google.com/spreadsheets/d/{cfg.MASTER_SHEET_ID}")


if __name__ == "__main__":
    main()
