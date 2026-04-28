"""
Tool: export_creds.py
Purpose: Export gws OAuth credentials to .tmp/gws_credentials.json
         so other tools can use the Gmail + Sheets APIs directly.
Run this once after each gws auth login.
"""

import subprocess, json, os, re

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR    = os.path.join(BASE_DIR, '.tmp')
GWS        = r"C:\Users\gappa\AppData\Roaming\npm\gws.cmd"
OUT_PATH   = os.path.join(TMP_DIR, 'gws_credentials.json')

result = subprocess.run([GWS, "auth", "export", "--unmasked"],
                        capture_output=True, text=True, timeout=30)

# Strip non-JSON lines (e.g. "Using keyring backend: keyring")
lines = result.stdout.strip().splitlines()
json_start = next(i for i, l in enumerate(lines) if l.strip().startswith('{'))
creds = json.loads("\n".join(lines[json_start:]))

os.makedirs(TMP_DIR, exist_ok=True)
with open(OUT_PATH, 'w') as f:
    json.dump(creds, f, indent=2)

print(f"Credentials exported to {OUT_PATH}")
print(f"  client_id:     {creds.get('client_id', '')[:40]}...")
print(f"  refresh_token: {creds.get('refresh_token', '')[:20]}...")
print(f"  type:          {creds.get('type', '')}")
