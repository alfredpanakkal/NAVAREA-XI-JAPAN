#!/usr/bin/env python3
"""
navarea_xi_scraper.py — Japan Coast Guard NAVAREA XI Scraper
Harvests active navigational warnings from the Japan Coast Guard portal.

Three-tier acquisition strategy (all via curl_cffi with a real Chrome TLS
fingerprint, since JCG/WAFs block plain python-requests from datacenter IPs):
  Tier 1: Direct GET of disp_warnings.cgi (no query params; serves the full
          active NAVAREA XI bulletin list in English, split by <hr>).
  Tier 2: Classic two-step warnings.cgi XML -> disp_warnings.cgi POST chain.
  Tier 3: SeaLagom mirror fallback (https://www.sealagom.com/navarea/11/).

NOTE: When using curl_cffi's impersonate="chrome", do NOT override the
User-Agent header — the TLS/JA3 fingerprint, HTTP/2 settings and sec-ch-ua
headers must stay consistent to avoid bot-detection blocks.
"""

import sys
import re
import urllib3
import xml.etree.ElementTree as ET
from datetime import datetime

from curl_cffi import requests as cffi_requests

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

JCG_ENCODING = "cp932"  # Shift-JIS superset used by JCG pages


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


def fetch_direct_disp():
    """Tier 1: Direct GET of disp_warnings.cgi with NO query parameters.
    Serves the full active NAVAREA XI warnings page in English, blocks
    separated by <hr>. Returns dict of warnings or raises."""
    print(f"Tier 1: Direct fetch of {URL_DISP} ...")

    response = cffi_requests.get(
        URL_DISP,
        impersonate="chrome",
        timeout=30,
        verify=False
    )
    response.raise_for_status()

    html_text = response.content.decode(JCG_ENCODING, errors="replace")

    # Preprocess HTML: replace <br> with newlines, strip <STRONG> tags
    html_text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    html_text = re.sub(r'</?STRONG>', '', html_text, flags=re.IGNORECASE)

    # The messages are separated by <hr> tags
    blocks = re.split(r'<hr\s*/?>', html_text, flags=re.IGNORECASE)
    return _collect_from_text_lines(blocks)


def fetch_two_step(year):
    """Tier 2: Classic JCG chain — warnings.cgi (XML IDs) -> disp_warnings.cgi
    (bulk HTML POST). Returns dict of warnings or raises."""
    print(f"Tier 2: Fetching XML bulletin list for year {year}...")

    # Fetch warning IDs via CGI POST
    response_xml = cffi_requests.post(
        URL_WARNINGS,
        data={'YEAR': str(year), 'TYPE': 'NAVAREA11', 'LANG': 'EG'},
        impersonate="chrome",
        timeout=30,
        verify=False
    )
    response_xml.raise_for_status()

    xml_text = response_xml.content.decode(JCG_ENCODING, errors="replace")
    # Strip any XML encoding declaration (e.g. encoding="Shift_JIS") that can
    # break ET.fromstring when the bytes were already decoded.
    xml_text = re.sub(r'^\s*<\?xml[^>]*\?>', '', xml_text.strip())

    # Parse XML to get tana IDs
    root = ET.fromstring(xml_text)
    tanas = [member.find('tana').text for member in root.findall('Member') if member.find('tana') is not None]

    if not tanas:
        print("ℹ️ No warnings found for the specified year on the JCG endpoint.")
        return {}

    print(f"Found {len(tanas)} active warnings. Fetching bulk HTML...")

    # Fetch bulk HTML via CGI POST
    tana_str = ":".join(tanas) + ":"
    response_html = cffi_requests.post(
        URL_DISP,
        data={'TYPE': 'NAVAREA11', 'TANA': tana_str, 'LANG': 'EG'},
        impersonate="chrome",
        timeout=30,
        verify=False
    )
    response_html.raise_for_status()

    html_text = response_html.content.decode(JCG_ENCODING, errors="replace")

    # Preprocess HTML: replace <br> with newlines, strip <STRONG> tags
    html_text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    html_text = re.sub(r'</?STRONG>', '', html_text, flags=re.IGNORECASE)

    # The messages are separated by <hr> tags
    blocks = re.split(r'<hr\s*/?>', html_text, flags=re.IGNORECASE)
    return _collect_from_text_lines(blocks)


def fetch_from_mirror():
    """Tier 3: SeaLagom mirror of the JCG NAVAREA XI bulletins. Returns dict or raises."""
    print(f"Tier 3: Falling back to mirror: {URL_MIRROR}")
    response = cffi_requests.get(
        URL_MIRROR,
        impersonate="chrome",
        timeout=30
    )
    response.raise_for_status()

    text = response.content.decode("utf-8", errors="replace")
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

    # Tier 1: direct JCG disp_warnings.cgi GET
    try:
        collected_warnings = fetch_direct_disp()
        if collected_warnings:
            print(f"✅ Tier 1 (direct disp_warnings.cgi) succeeded.")
    except Exception as e:
        print(f"⚠️ Tier 1 (direct disp_warnings.cgi) unavailable: {e}")

    # Tier 2: JCG two-step XML + POST chain
    if not collected_warnings:
        try:
            collected_warnings = fetch_two_step(year)
            if collected_warnings:
                print("✅ Tier 2 (JCG two-step chain) succeeded.")
        except Exception as e:
            print(f"⚠️ Tier 2 (JCG two-step chain) unavailable: {e}")

    # Tier 3: mirror fallback
    if not collected_warnings:
        try:
            collected_warnings = fetch_from_mirror()
            if collected_warnings:
                print("✅ Tier 3 (SeaLagom mirror) succeeded.")
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
