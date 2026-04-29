"""
Tool: send_approved.py
Purpose: Read the Master AI Growth System Leads tab and send emails to any row
         where Status = "Approved to Send".

Works for any sector (Hotels, Universities, NGOs, etc.) — sector-agnostic.

SAFETY:
  - Will NOT send if Status != "Approved to Send"
  - Will NOT send to duplicate domains in the same run
  - Will NOT send if Contact Email is empty
  - Will NOT send if Email Subject or Email Body is empty
  - After sending: sets Status -> "Sent", Last Contacted -> timestamp
"""

import json, os, sys, time, base64, requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')
sys.path.insert(0, os.path.join(BASE_DIR, 'tools'))
import config as cfg

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_API  = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

# Master Sheet — Leads tab column indices (0-based)
# Lead ID | Org Name | Country | Sector | Website |
# Contact Name | Contact Email | LinkedIn | Lead Source | Status |
# Lead Score | Outreach Angle | Last Contacted | Next Follow Up |
# Notes | Date Added | Email Subject | Email Body
COL_LEAD_ID      = 0
COL_NAME         = 1
COL_EMAIL        = 6
COL_STATUS       = 9
COL_LAST_CONTACT = 12
COL_SUBJECT      = 16
COL_BODY         = 17

COL_LETTER = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def get_token(creds_file):
    path = os.path.join(TMP_DIR, creds_file)
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Run: python tools/export_creds.py")
        sys.exit(1)
    with open(path) as f:
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
    r = requests.get(
        f"{SHEETS_API}/{sid}/values/{requests.utils.quote(range_, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("values", [])


def sheets_update(token, sid, cell, value):
    r = requests.put(
        f"{SHEETS_API}/{sid}/values/{requests.utils.quote(cell, safe='')}?valueInputOption=USER_ENTERED",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"values": [[value]]},
        timeout=30
    )
    r.raise_for_status()


def build_mime(to, subject, body_text, cc_emails):
    msg = MIMEMultipart()
    msg["From"]    = cfg.FROM_EMAIL
    msg["To"]      = to
    msg["Cc"]      = ", ".join(cc_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_gmail(gmail_token, raw_message):
    r = requests.post(
        f"{GMAIL_API}/messages/send",
        headers={"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"},
        json={"raw": raw_message},
        timeout=60
    )
    if not r.ok:
        raise RuntimeError(f"Gmail send failed {r.status_code}: {r.text[:200]}")
    return r.json().get("id", "")


def main():
    print("Loading credentials...")
    sheets_token = get_token(cfg.CREDS_SHEETS)   # appaubonsu - Sheets read/write
    gmail_token  = get_token(cfg.CREDS_GMAIL)    # novalinkafrica - Gmail send

    sid = cfg.MASTER_SHEET_ID
    tab = cfg.LEADS_TAB

    print(f"Reading: {tab} tab")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{sid}\n")

    rows = sheets_get(sheets_token, sid, f"{tab}!A:R")
    if len(rows) <= 1:
        print("No leads found in sheet.")
        return

    sent_count = skipped_count = error_count = 0
    sent_domains = set()

    for sheet_row, row in enumerate(rows[1:], start=2):
        while len(row) <= COL_BODY:
            row.append("")

        name    = row[COL_NAME].strip()
        email   = row[COL_EMAIL].strip()
        status  = row[COL_STATUS].strip()
        subject = row[COL_SUBJECT].strip()
        body    = row[COL_BODY].strip()
        safe    = name.encode("ascii", "replace").decode()

        if status != "Approved to Send":
            print(f"  SKIP  [{safe}] - status '{status}'")
            skipped_count += 1
            continue

        if not email:
            print(f"  SKIP  [{safe}] - no email")
            skipped_count += 1
            continue

        if not subject or not body:
            print(f"  SKIP  [{safe}] - missing Email Subject or Email Body (fill these in the sheet)")
            skipped_count += 1
            continue

        domain = email.split("@")[-1].lower()
        if domain in sent_domains:
            print(f"  SKIP  [{safe}] - already sent to @{domain} this run")
            skipped_count += 1
            continue

        print(f"  SEND  [{safe}] -> {email}")
        try:
            raw    = build_mime(email, subject, body, cfg.CC_EMAILS)
            msg_id = send_gmail(gmail_token, raw)
            sent_domains.add(domain)
            sent_count += 1

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tab_cell  = lambda col: f"{tab}!{COL_LETTER[col]}{sheet_row}"
            sheets_update(sheets_token, sid, tab_cell(COL_STATUS),       "Sent")
            sheets_update(sheets_token, sid, tab_cell(COL_LAST_CONTACT), timestamp)
            print(f"        + Sent (msg_id: {msg_id}) at {timestamp}")
            time.sleep(2)

        except Exception as e:
            print(f"        x ERROR: {e}")
            error_count += 1

    print(f"\n=== Send Complete ===")
    print(f"  Sent:    {sent_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors:  {error_count}")


if __name__ == "__main__":
    main()
