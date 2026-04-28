# Workflow: Hotel Lead Generation & Outreach — Ghana
# NovaLink Africa

## Objective
Find hotels in Ghana, build a structured lead database in Google Sheets, generate personalised outreach emails, and send them only when explicitly approved via the sheet.

## Required Inputs
- SerpAPI key (in .env)
- Firecrawl CLI (installed)
- gws CLI authenticated with drive, sheets, docs, slides, gmail scopes
- Business context: NovaLink Africa, Gerald Bonsu, appaubonsu@gmail.com

## Tools
| Tool | Purpose |
|---|---|
| `tools/research_hotels.py` | SerpAPI + Firecrawl to find hotels and extract contact info |
| `tools/build_sheet.py` | Create Google Sheet and populate with all lead + message data |
| `tools/send_approved.py` | Send emails for rows marked "Approved to Send" |

## Execution Order
1. Run `tools/research_hotels.py` → outputs `.tmp/hotels_raw.json`
2. Agent reviews data, scores leads, generates personalised messages → outputs `.tmp/hotels_processed.json`
3. Run `tools/build_sheet.py` → creates Google Sheet, saves ID to `.tmp/sheet_info.json`
4. Human reviews sheet, sets status to "Approved to Send" for desired rows
5. Run `tools/send_approved.py` → sends approved emails, updates sheet

## Control Rules
- NEVER send emails unless Outreach Status = "Approved to Send"
- NEVER send to rows with empty email field
- NEVER send duplicate emails to the same domain
- Send FROM: novalinkafrica@gmail.com (credentials: .tmp/gws_credentials_novalink.json)
- Sheet read/write: appaubonsu@gmail.com (credentials: .tmp/gws_credentials.json)
- Always CC: appaubonsu@gmail.com, grindhardcircle@gmail.com

## Output Files
- `.tmp/hotels_raw.json` — raw research data
- `.tmp/hotels_processed.json` — scored + messaged leads
- `.tmp/sheet_info.json` — spreadsheet ID and URL

## Known Issues / Learnings
- gws auth login must include gmail scope for sending: `gws auth login -s drive,sheets,docs,slides,gmail`
- SerpAPI google_maps engine returns best structured local business data
- Firecrawl contact page scraping: try /contact and /contact-us as fallback URLs
- Gmail +send CC flag: verify support, fall back to users.messages.send with MIME if needed
