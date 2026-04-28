"""
Tool: send_approved.py
Purpose: Read the Hotel Directory sheet and send emails to rows where
         Outreach Status = "Approved to Send".
         Uses Sheets API + Gmail API directly via requests (no gws CLI).
SAFETY:  Will NOT send if status != "Approved to Send".
         Will NOT send to duplicate domains in the same run.
         Will NOT send if email field is empty.
"""

import json, os, sys, time, base64, requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')

# appaubonsu credentials — Sheets read/write access
CREDS_FILE         = os.path.join(TMP_DIR, 'gws_credentials.json')
# novalinkafrica credentials — Gmail send access
CREDS_FILE_GMAIL   = os.path.join(TMP_DIR, 'gws_credentials_novalink.json')
SHEETS_API   = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_API    = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL    = "https://oauth2.googleapis.com/token"

FROM_EMAIL   = "novalinkafrica@gmail.com"
CC_EMAILS    = ["appaubonsu@gmail.com", "grindhardcircle@gmail.com"]

# Column indices (0-based, matching HEADERS_ROW order)
COL_NAME    = 0
COL_EMAIL   = 5
COL_MSG     = 12
COL_SUBJECT = 13
COL_STATUS  = 14
COL_UPDATED = 16
COL_SENT_TS = 17
COL_LETTER  = list("ABCDEFGHIJKLMNOPQRS")

def load_creds():
    if not os.path.exists(CREDS_FILE):
        print(f"ERROR: {CREDS_FILE} not found.")
        print("Run: python tools/export_creds.py  to generate it.")
        sys.exit(1)
    with open(CREDS_FILE) as f:
        return json.load(f)

def get_token(creds):
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

def sheets_update(token, sid, range_, value):
    r = requests.put(
        f"{SHEETS_API}/{sid}/values/{requests.utils.quote(range_, safe='')}?valueInputOption=USER_ENTERED",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"values": [[value]]},
        timeout=30
    )
    r.raise_for_status()

def build_mime(to, subject, body_text):
    msg = MIMEMultipart()
    msg["From"]    = FROM_EMAIL
    msg["To"]      = to
    msg["Cc"]      = ", ".join(CC_EMAILS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return raw

def send_gmail(token, raw_message):
    r = requests.post(
        f"{GMAIL_API}/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw_message},
        timeout=60
    )
    if not r.ok:
        raise RuntimeError(f"Gmail send failed {r.status_code}: {r.text[:200]}")
    return r.json().get("id", "")

def main():
    info_path = os.path.join(TMP_DIR, 'sheet_info.json')
    if not os.path.exists(info_path):
        print("ERROR: sheet_info.json not found. Run build_sheet.py first.")
        sys.exit(1)

    with open(info_path) as f:
        sheet_info = json.load(f)
    sid = sheet_info["spreadsheet_id"]

    print("Loading credentials...")
    creds       = load_creds()
    token       = get_token(creds)                          # Sheets token (appaubonsu)

    gmail_creds = json.load(open(CREDS_FILE_GMAIL))
    gmail_token = get_token(gmail_creds)                   # Gmail token (novalinkafrica)

    print(f"Reading sheet: {sheet_info['url']}\n")
    rows = sheets_get(token, sid, "Hotel Directory!A:S")
    if not rows:
        print("Sheet is empty.")
        return

    headers = rows[0]
    sent_count = skipped_count = error_count = 0
    sent_domains = set()

    for sheet_row, row in enumerate(rows[1:], start=2):
        while len(row) <= COL_STATUS:
            row.append("")

        name    = row[COL_NAME].strip()
        email   = row[COL_EMAIL].strip()
        status  = row[COL_STATUS].strip()
        subject = row[COL_SUBJECT].strip() if len(row) > COL_SUBJECT else ""
        message = row[COL_MSG].strip()    if len(row) > COL_MSG     else ""

        safe_name = name.encode('ascii', 'replace').decode()

        if not email:
            print(f"  SKIP  [{safe_name}] - no email")
            skipped_count += 1
            continue

        if status != "Approved to Send":
            print(f"  SKIP  [{safe_name}] - status '{status}'")
            skipped_count += 1
            continue

        domain = email.split("@")[-1].lower()
        if domain in sent_domains:
            print(f"  SKIP  [{safe_name}] - already sent to @{domain} this run")
            skipped_count += 1
            continue

        if not subject or not message:
            print(f"  SKIP  [{safe_name}] - missing subject or message")
            skipped_count += 1
            continue

        print(f"  SEND  [{safe_name}] -> {email}")
        try:
            raw = build_mime(email, subject, message)
            msg_id = send_gmail(gmail_token, raw)
            sent_domains.add(domain)
            sent_count += 1

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheets_update(token, sid, f"Hotel Directory!{COL_LETTER[COL_STATUS]}{sheet_row}",  "Sent")
            sheets_update(token, sid, f"Hotel Directory!{COL_LETTER[COL_SENT_TS]}{sheet_row}", timestamp)
            sheets_update(token, sid, f"Hotel Directory!{COL_LETTER[COL_UPDATED]}{sheet_row}", timestamp)
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
