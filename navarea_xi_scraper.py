#!/usr/bin/env python3
"""
navarea_xi_scraper.py — Japan Coast Guard NAVAREA XI Scraper
Harvests active navigational warnings from the Japan Coast Guard portal using their CGI endpoints,
with an automatic fallback to the SeaLagom mirror (https://www.sealagom.com/navarea/11/)
when the JCG site is unreachable or blocks automated access.
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
# Mirror of the JCG NAVAREA XI bulletins (free full-content page)
URL_MIRROR = "https://www.sealagom.com/navarea/11/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _collect_from_text_lines(blocks):
    """Shared extraction: each block starts with 'NO.26-0451       Date:2026/10/09 07 UTC'."""
    collected_warnings = {}

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Strip any remaining HTML tags
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

    return collected_warnings


def _write_output(collected_warnings, output_filename):
    with open(output_filename, "w", encoding="utf-8") as f:
        for warn in collected_warnings.values():
            f.write(f"--- {warn['header']} ---\n")
            f.write(f"{warn['date_line']}\n")
            f.write(f"{warn['body']}\n\n")


def fetch_from_jcg(year):
    """Primary source: Japan Coast Guard CGI endpoints. Returns dict of warnings or raises."""
    print(f"Fetching XML bulletin list for year {year}...")

    # Fetch warning IDs via CGI POST
    response_xml = requests.post(
        URL_WARNINGS,
        data={'YEAR': str(year), 'TYPE': 'NAVAREA11', 'LANG': 'EG'},
        verify=False,
        headers=HEADERS,
        timeout=30
    )
    response_xml.raise_for_status()

    # Parse XML to get tana IDs
    root = ET.fromstring(response_xml.text)
    tanas = [member.find('tana').text for member in root.findall('Member') if member.find('tana') is not None]

    if not tanas:
        print("ℹ️ No warnings found for the specified year on the JCG endpoint.")
        return {}

    print(f"Found {len(tanas)} active warnings. Fetching bulk HTML...")

    # Fetch bulk HTML via CGI POST
    tana_str = ":".join(tanas) + ":"
    response_html = requests.post(
        URL_DISP,
        data={'TYPE': 'NAVAREA11', 'TANA': tana_str, 'LANG': 'EG'},
        verify=False,
        headers=HEADERS,
        timeout=30
    )
    response_html.raise_for_status()

    html_text = response_html.text

    # Preprocess HTML: replace <br> with newlines, strip <STRONG> tags
    html_text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    html_text = re.sub(r'</?STRONG>', '', html_text, flags=re.IGNORECASE)

    # The messages are separated by <hr> tags
    blocks = re.split(r'<hr\s*/?>', html_text, flags=re.IGNORECASE)
    return _collect_from_text_lines(blocks)


def fetch_from_mirror():
    """Fallback source: SeaLagom mirror of the JCG NAVAREA XI bulletins. Returns dict or raises."""
    print(f"Falling back to mirror: {URL_MIRROR}")
    response = requests.get(URL_MIRROR, headers=HEADERS, timeout=30)
    response.raise_for_status()

    text = response.text
    # Normalise whitespace: warnings on the mirror page are rendered as
    # 'NO.26-0451 Date:2026/10/09 07 UTC <body...>' blocks.
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#39;', "'", text)

    # Split on every warning header occurrence: NO.26-0451 Date:...
    parts = re.split(r'(?=NO\.\d{2}-\d{4}\s+Date:)', text)
    blocks = []
    for part in parts:
        m = re.match(r'(NO\.\d{2}-\d{4})\s+(Date:[^\n]*)', part.strip())
        if not m:
            continue
        header_line = f"{m.group(1)}       {m.group(2).strip()}"
        body = part.strip()[m.end(2):].strip()
        blocks.append(header_line + "\n" + body)

    return _collect_from_text_lines(blocks)


def scrape_xi_warnings(output_filename="navarea_xi_warnings.txt", year=None):
    print("=" * 60)
    print("⚓ Japan Coast Guard NAVAREA XI Navigational Warnings Scraper")
    print("=" * 60)

    if year is None:
        year = datetime.now().year

    collected_warnings = {}

    # Stage 1: primary source (JCG CGI)
    try:
        collected_warnings = fetch_from_jcg(year)
    except Exception as e:
        print(f"⚠️ JCG endpoint unavailable: {e}")

    # Stage 2: mirror fallback
    if not collected_warnings:
        try:
            collected_warnings = fetch_from_mirror()
        except Exception as e:
            print(f"❌ Mirror also unavailable: {e}")

    if not collected_warnings:
        print("❌ All sources failed: could not retrieve NAVAREA XI warnings.")
        sys.exit(1)

    print(f"Total unique warnings extracted: {len(collected_warnings)}")

    # Write out to structured text file
    _write_output(collected_warnings, output_filename)

    print(f"✅ Successfully wrote {len(collected_warnings)} warnings to '{output_filename}'.")
    return collected_warnings

if __name__ == "__main__":
    scrape_xi_warnings()
