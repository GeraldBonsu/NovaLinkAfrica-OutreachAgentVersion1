"""
Tool: build_sheet.py
Purpose: Create Google Sheet and populate with processed hotel lead data.
         Calls the Sheets API directly via requests (no gws CLI) to avoid
         Windows CMD argument-length and special-character issues.
Input:  .tmp/hotels_processed.json
Output: .tmp/sheet_info.json
"""

import json, os, sys, requests, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')

CREDS_FILE = os.path.join(TMP_DIR, 'gws_credentials.json')

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL  = "https://oauth2.googleapis.com/token"

HEADERS_ROW = [
    "Hotel Name", "City", "Region", "Country", "Phone Number", "Email",
    "Website", "Contact Person", "Contact Role", "Source URL",
    "Lead Quality Score", "Reason for Score", "Personalised Message",
    "Email Subject Line", "Outreach Status", "Date Added", "Last Updated",
    "Sent Timestamp", "Notes"
]

def get_token():
    if not os.path.exists(CREDS_FILE):
        print(f"ERROR: {CREDS_FILE} not found. Run: python tools/export_creds.py")
        sys.exit(1)
    with open(CREDS_FILE) as f:
        creds = json.load(f)
    resp = requests.post(TOKEN_URL, data={
        "client_id":     creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]

def api(method, url, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = getattr(requests, method)(url, headers=headers, timeout=60, **kwargs)
    if not resp.ok:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()

def create_spreadsheet(token, title):
    body = {"properties": {"title": title},
            "sheets": [{"properties": {"title": "Hotel Directory"}}]}
    result = api("post", SHEETS_API, token, json=body)
    return result["spreadsheetId"]

def write_values(token, sid, range_, values, batch_size=20):
    """Write values in batches to avoid payload size limits."""
    sheet, start = range_.split("!")
    row_start = int(''.join(filter(str.isdigit, start))) if any(c.isdigit() for c in start) else 1

    for i in range(0, len(values), batch_size):
        chunk      = values[i:i + batch_size]
        cell_range = f"{sheet}!A{row_start + i}"
        url = f"{SHEETS_API}/{sid}/values/{requests.utils.quote(cell_range, safe='')}?valueInputOption=USER_ENTERED"
        api("put", url, token, json={"values": chunk})
        print(f"    rows {row_start + i}–{row_start + i + len(chunk) - 1} written")
        time.sleep(0.3)

def format_header(token, sid, sheet_id):
    body = {"requests": [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.07, "green": 0.52, "blue": 0.78}
            }},
            "fields": "userEnteredFormat(textFormat,backgroundColor)"
        }},
        {"updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1}
            },
            "fields": "gridProperties.frozenRowCount"
        }},
        {"autoResizeDimensions": {
            "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                           "startIndex": 0, "endIndex": 19}
        }}
    ]}
    api("post", f"{SHEETS_API}/{sid}:batchUpdate", token, json=body)

def main():
    input_path = os.path.join(TMP_DIR, 'hotels_processed.json')
    if not os.path.exists(input_path):
        print(f"ERROR: {input_path} not found. Run process_leads.py first.")
        sys.exit(1)

    with open(input_path, encoding='utf-8') as f:
        hotels = json.load(f)

    print(f"Loaded {len(hotels)} hotels.")
    print("Getting access token...")
    token = get_token()

    print("Creating Google Spreadsheet...")
    sid = create_spreadsheet(token, "NovaLink Africa - Hotel Directory Ghana")
    print(f"  Spreadsheet ID: {sid}")
    print(f"  URL: https://docs.google.com/spreadsheets/d/{sid}")

    today = datetime.now().strftime("%Y-%m-%d")
    rows  = [HEADERS_ROW]

    for h in hotels:
        rows.append([
            h.get("hotel_name", ""),
            h.get("city", ""),
            h.get("region", ""),
            h.get("country", "Ghana"),
            h.get("phone", ""),
            h.get("email", ""),
            h.get("website", ""),
            h.get("contact_person", ""),
            h.get("contact_role", ""),
            h.get("source_url", ""),
            str(h.get("lead_quality_score", "")),
            h.get("reason_for_score", ""),
            h.get("personalised_message", ""),
            h.get("email_subject_line", ""),
            h.get("outreach_status", "Ready to Review"),
            today, today, "",
            h.get("notes", ""),
        ])

    print(f"Writing {len(rows)-1} data rows...")
    write_values(token, sid, "Hotel Directory!A1", rows)

    # Get sheet_id for formatting
    info    = api("get", f"{SHEETS_API}/{sid}", token)
    sheet_id = info["sheets"][0]["properties"]["sheetId"]

    print("Formatting header row...")
    format_header(token, sid, sheet_id)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}"
    sheet_info = {
        "spreadsheet_id": sid,
        "url": sheet_url,
        "created_at": today,
        "total_leads": len(hotels),
        "leads_with_email": sum(1 for h in hotels if h.get("email")),
    }
    with open(os.path.join(TMP_DIR, 'sheet_info.json'), 'w') as f:
        json.dump(sheet_info, f, indent=2)

    print(f"\n=== Sheet Built Successfully ===")
    print(f"  URL:          {sheet_url}")
    print(f"  Total leads:  {len(hotels)}")
    print(f"  With email:   {sheet_info['leads_with_email']}")

if __name__ == "__main__":
    main()
