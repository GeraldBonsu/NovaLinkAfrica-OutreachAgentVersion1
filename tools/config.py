"""
config.py — Central configuration for the Master AI Growth System workflow.

To switch sectors or countries, change TARGET_SECTOR and TARGET_COUNTRY here.
All tools (research_leads.py, write_to_master_sheet.py) read from this file.
"""

# ─── Master AI Growth System Google Sheet ───────────────────────────────────
MASTER_SHEET_ID = "1JxARr89O-MAT3bDzTg0SMdR3CGaG6ly5GZBvmsq9eFQ"
LEADS_TAB       = "Leads"

# ─── Research targets ────────────────────────────────────────────────────────
# Supported sectors: Hotel, University, NGO, Investor, Sponsor, Business, Rural Community
TARGET_SECTOR  = "Hotel"
TARGET_COUNTRY = "Ghana"

# Max leads to add per research run (0 = no limit)
DAILY_LEAD_LIMIT = 50

# ─── Lead ID prefix codes per sector ─────────────────────────────────────────
SECTOR_CODES = {
    "Hotel":            "HTL",
    "University":       "UNI",
    "NGO":              "NGO",
    "Investor":         "INV",
    "Sponsor":          "SPO",
    "Business":         "BIZ",
    "Rural Community":  "RRL",
}

# ─── OAuth credential files (relative to AI Agents/.tmp/) ───────────────────
# Run tools/export_creds.py after each gws auth login to refresh these.
CREDS_SHEETS = "gws_credentials.json"        # appaubonsu — Sheets read/write
CREDS_GMAIL  = "gws_credentials_novalink.json"  # novalinkafrica — Gmail send

# ─── Outreach email settings (used by send_approved.py) ─────────────────────
FROM_EMAIL = "novalinkafrica@gmail.com"
CC_EMAILS  = ["appaubonsu@gmail.com", "grindhardcircle@gmail.com"]
