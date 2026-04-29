# Workflow: Master AI Growth System — Lead Research & Population
# NovaLink Africa

## Objective
Research leads for any sector and country, then populate the Master AI Growth System
Google Sheet (Leads tab) with deduplicated, structured lead data.
Outreach emails are handled separately by the outreach workflow — this workflow only populates leads.

## Master Sheet
- **Google Sheet:** https://docs.google.com/spreadsheets/d/1JxARr89O-MAT3bDzTg0SMdR3CGaG6ly5GZBvmsq9eFQ
- **Tabs:** Leads | Outreach Log | Replies | Lead Scoring | Proposals | Weekly Report
- **Active tab:** Leads (all research outputs go here)

## Configuration
Edit `tools/config.py` to change the research target:

```python
TARGET_SECTOR  = "Hotel"       # Hotel | University | NGO | Investor | Sponsor | Business
TARGET_COUNTRY = "Ghana"       # Ghana | Nigeria | Tanzania | Kenya | Rwanda
DAILY_LEAD_LIMIT = 50          # Max leads added per run (0 = unlimited)
MASTER_SHEET_ID = "1JxARr89O-MAT3bDzTg0SMdR3CGaG6ly5GZBvmsq9eFQ"
```

## Leads Tab Columns
| Column | Description |
|---|---|
| Lead ID | Auto-generated: NVL-{SECTOR_CODE}-{YYYY}-{NNNN} |
| Organisation Name | Hotel/university/org name |
| Country | Country of lead |
| Sector | Hotel, University, NGO, etc. |
| Website | Organisation website |
| Contact Name | Key contact name or role |
| Contact Email | Primary outreach email |
| LinkedIn | LinkedIn profile or company page |
| Lead Source | How the lead was found |
| Status | New / No Email - Review / Research Needed / Previously Contacted |
| Lead Score | Left blank (to be scored manually or by scoring agent) |
| Outreach Angle | Left blank (to be filled before outreach) |
| Last Contacted | Updated by outreach workflow |
| Next Follow Up | Updated by outreach workflow |
| Notes | Research notes, IT/ICT emails, additional context |
| Date Added | Date the lead was added |

## Lead ID Codes
| Sector | Code | Example |
|---|---|---|
| Hotel | HTL | NVL-HTL-2026-0001 |
| University | UNI | NVL-UNI-2026-0001 |
| NGO | NGO | NVL-NGO-2026-0001 |
| Investor | INV | NVL-INV-2026-0001 |
| Sponsor | SPO | NVL-SPO-2026-0001 |
| Business | BIZ | NVL-BIZ-2026-0001 |
| Rural Community | RRL | NVL-RRL-2026-0001 |

## Execution Order

### Regular research run (hotels, NGOs, etc.):
1. Set `TARGET_SECTOR` and `TARGET_COUNTRY` in `tools/config.py`
2. Run: `python tools/research_leads.py` → outputs `.tmp/leads_for_master.json`
3. Run: `python tools/write_to_master_sheet.py` → appends new leads to Leads tab
4. Review new rows in the sheet; set Status to "Approved to Send" when ready for outreach

### Safe test before writing:
```
python tools/write_to_master_sheet.py --dry-run
```

### Import from a different source:
```
python tools/write_to_master_sheet.py --input path/to/my_leads.json
```

## Deduplication Rules
write_to_master_sheet.py checks in this order before inserting:
1. Website (normalised — strips protocol, www, trailing slash)
2. Contact Email (lowercase)
3. Organisation Name (lowercase) + Country (lowercase)

If any match exists, the lead is skipped and logged.

## Status Values
| Status | Meaning |
|---|---|
| New | Email found — ready for outreach review |
| No Email - Review | No email found but website present — worth manual research |
| Research Needed | No email and no website — needs more investigation |
| Previously Contacted | Lead contacted via prior campaign (e.g. via appaubonsu@gmail.com) |
| Approved to Send | Human approved — outreach workflow will send email |
| Sent | Email has been sent by outreach workflow |

## Outreach Control
- This workflow NEVER sends emails
- Only `tools/send_approved.py` sends emails, and only when Status = "Approved to Send"
- Outreach emails come FROM: novalinkafrica@gmail.com
- Always CC: appaubonsu@gmail.com, grindhardcircle@gmail.com
- For universities with an IT/ICT email: include IT/ICT email as CC alongside grindhardcircle@gmail.com

## University Notes (Special Case)
Universities were imported from the University Outreach CRM with Status = "Previously Contacted".
- They were originally emailed via appaubonsu@gmail.com through an n8n workflow on 2026-04-28
- Future outreach to these universities should come FROM novalinkafrica@gmail.com
- The general email is in Contact Email; IT/ICT email is captured in Notes
- CC both grindhardcircle@gmail.com AND the IT/ICT email when sending

## Output Files
- `.tmp/leads_raw_serpapi.json` — raw SerpAPI results (checkpoint)
- `.tmp/leads_for_master.json` — final leads ready for import

## One-Time Imports
- Universities: `python tools/import_universities.py` (already completed 2026-04-29)
- Re-run is safe — deduplication prevents double-imports

## Known Issues / Notes
- Uses SerpAPI google_maps engine for Hotels/Businesses (best local business data)
- Uses SerpAPI organic search for Universities/NGOs/Investors
- Firecrawl REST API used for email extraction (not CLI — Windows subprocess limitation)
- All credentials loaded from .tmp/ (gitignored) — never hardcoded
