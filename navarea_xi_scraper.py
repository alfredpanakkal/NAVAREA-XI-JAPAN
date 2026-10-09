#!/usr/bin/env python3
"""
navarea_xi_scraper.py — Japan Coast Guard NAVAREA XI Scraper
Harvests active navigational warnings from the Japan Coast Guard portal using their CGI endpoints.
"""

import sys
import re
import requests
import urllib3
import xml.etree.ElementTree as ET
from datetime import datetime

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_WARNINGS = "https://www1.kaiho.mlit.go.jp/TUHO/keiho/cgi/warnings.cgi"
URL_DISP = "https://www1.kaiho.mlit.go.jp/TUHO/keiho/cgi/disp_warnings.cgi"

def scrape_xi_warnings(output_filename="navarea_xi_warnings.txt", year=None):
    print("=" * 60)
    print("⚓ Japan Coast Guard NAVAREA XI Navigational Warnings Scraper")
    print("=" * 60)
    
    if year is None:
        year = datetime.now().year
        
    print(f"Fetching XML bulletin list for year {year}...")

    # Fetch warning IDs via CGI POST
    try:
        response_xml = requests.post(
            URL_WARNINGS, 
            data={'YEAR': str(year), 'TYPE': 'NAVAREA11', 'LANG': 'EG'}, 
            verify=False,
            timeout=30
        )
        response_xml.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error while fetching {URL_WARNINGS}: {e}")
        sys.exit(1)

    # Parse XML to get tana IDs
    root = ET.fromstring(response_xml.text)
    tanas = [member.find('tana').text for member in root.findall('Member') if member.find('tana') is not None]
    
    if not tanas:
        print("ℹ️ No warnings found for the specified year.")
        return {}

    print(f"Found {len(tanas)} active warnings. Fetching bulk HTML...")

    # Fetch bulk HTML via CGI POST
    tana_str = ":".join(tanas) + ":"
    try:
        response_html = requests.post(
            URL_DISP, 
            data={'TYPE': 'NAVAREA11', 'TANA': tana_str, 'LANG': 'EG'}, 
            verify=False,
            timeout=30
        )
        response_html.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error while fetching {URL_DISP}: {e}")
        sys.exit(1)

    html_text = response_html.text
    
    # Preprocess HTML: replace <br> with newlines, strip <STRONG> tags
    html_text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    html_text = re.sub(r'</?STRONG>', '', html_text, flags=re.IGNORECASE)
    
    # The messages are separated by <hr> tags
    blocks = re.split(r'<hr\s*/?>', html_text, flags=re.IGNORECASE)
    
    collected_warnings = {}
    
    for block in blocks:
        # Each block starts with something like: "NO.26-0451       Date:2026/10/09 07 UTC"
        # We need to extract the header and the body.
        block = block.strip()
        if not block:
            continue
            
        # Strip other HTML tags just to be safe (like H1 NAVAREA XI at the top)
        block = re.sub(r'<.*?>', '', block)
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        if not lines:
            continue
            
        header_line = lines[0]
        # Look for the warning ID, e.g. "NO.26-0451"
        id_match = re.search(r'(NO\.\d{2}-\d{4})', header_line)
        if not id_match:
            continue
            
        warning_id_raw = id_match.group(1)
        header_clean = f"NAVAREA XI {warning_id_raw}"
        
        # The remaining lines are the date and body
        body_text = "\n".join(lines[1:]).strip()
        
        key = header_clean
        if key not in collected_warnings:
            collected_warnings[key] = {
                "header": header_clean,
                "date_line": header_line,
                "body": body_text
            }

    print(f"Total unique warnings extracted: {len(collected_warnings)}")

    # Write out to structured text file
    with open(output_filename, "w", encoding="utf-8") as f:
        for warn in collected_warnings.values():
            f.write(f"--- {warn['header']} ---\n")
            f.write(f"{warn['date_line']}\n")
            f.write(f"{warn['body']}\n\n")

    print(f"✅ Successfully wrote {len(collected_warnings)} warnings to '{output_filename}'.")
    return collected_warnings

if __name__ == "__main__":
    scrape_xi_warnings()
