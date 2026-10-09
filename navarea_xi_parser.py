#!/usr/bin/env python3
"""
navarea_xi_parser.py — Deterministic Navigational Warning Parser for NAVAREA XI (Japan)
Normalizes coordinate geometries into WGS84 decimal, infers issued years, classifies maritime hazard semantics,
and prepares structured JSON payloads for Supabase synchronization.
"""

import sys
import re
import json
import hashlib
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

SOURCE_ID = "kaiho-navarea-xi"
NAVAREA_ID = "XI"

def convert_to_decimal(degrees: str, minutes: str, seconds: str, direction: str) -> float:
    """Converts Degrees, Decimal Minutes, and Decimal Seconds into Signed Decimal Degrees (WGS84)."""
    decimal = float(degrees)
    
    if minutes:
        decimal += float(minutes) / 60.0
    if seconds:
        decimal += float(seconds) / 3600.0
        
    if direction.upper() in ['S', 'W']:
        decimal = -decimal
    return round(decimal, 6)

def parse_coordinates(raw_text: str):
    """
    Extracts navigational coordinates from text.
    Handles varied precision including Decimal Minutes and Decimal Seconds:
      - 16-54.1N 134-39.5E
      - 24-04.12N 118-46.48E
      - 28-15-15N 146-29-47E
      - 04-32-31.8S 114-01-36.0E
    """
    # Regex matches: DD-MM.MM-SS.SS[N/S] DDD-MM.MM-SS.SS[E/W]
    # Minutes and seconds can be optional and can have decimal components.
    pattern = r'(\d{2,3})-(\d{2}(?:\.\d+)?)(?:-(\d{2}(?:\.\d+)?))?([NS])\s+(\d{2,3})-(\d{2}(?:\.\d+)?)(?:-(\d{2}(?:\.\d+)?))?([EW])'
    matches = list(re.finditer(pattern, raw_text, re.IGNORECASE))

    parsed_coords = []
    points = []

    for match in matches:
        lat_deg, lat_min, lat_sec, lat_dir = match.group(1), match.group(2), match.group(3), match.group(4).upper()
        lon_deg, lon_min, lon_sec, lon_dir = match.group(5), match.group(6), match.group(7), match.group(8).upper()

        lat = convert_to_decimal(lat_deg, lat_min, lat_sec, lat_dir)
        lon = convert_to_decimal(lon_deg, lon_min, lon_sec, lon_dir)

        points.append([lon, lat])  # GeoJSON format: [lon, lat]
        
        # Reconstruct string format for display
        lat_str = f"{lat_deg}-{lat_min}" + (f"-{lat_sec}" if lat_sec else "") + lat_dir
        lon_str = f"{lon_deg}-{lon_min}" + (f"-{lon_sec}" if lon_sec else "") + lon_dir
        parsed_coords.append(f"{lat_str} {lon_str}")

    spatial = None
    primary_lat = None
    primary_lon = None

    if points:
        if len(points) == 1:
            primary_lat = points[0][1]
            primary_lon = points[0][0]
            spatial = {"type": "Point", "coordinates": points[0]}
        elif len(points) >= 4:
            # Check for polygon or closed bounding box
            primary_lat = round(sum(p[1] for p in points) / len(points), 6)
            primary_lon = round(sum(p[0] for p in points) / len(points), 6)
            # Ensure closed polygon loop for GeoJSON specification
            closed_points = points if points[0] == points[-1] else points + [points[0]]
            spatial = {"type": "Polygon", "coordinates": [closed_points]}
        else:
            primary_lat = points[0][1]
            primary_lon = points[0][0]
            spatial = {"type": "LineString", "coordinates": points}

    return parsed_coords, primary_lat, primary_lon, spatial

def classify_hazard(raw_text: str) -> str:
    """Classifies maritime hazard category based on terminology."""
    text = raw_text.upper()
    # 1. Electronic / GNSS interference
    if any(k in text for k in ["GNSS", "DGPS", "AIS INTERFERENCE", "RADAR INTERFERENCE", "INTERFERENCE OBSERVED", "JAMMING", "SPOOFING"]):
        return "electronic"
    # 2. Military / Naval operations (explicitly avoid matching "EXERCISE CAUTION")
    military_pattern = r'\b(DETONATION|DETONATIONS|FIRING|FIRINGS|GUNNERY|MISSILE|WEAPONS?|ARMED FORCES|NAVAL EXERCISE|NAVAL EXERCISES|MILITARY EXERCISE)\b'
    if re.search(military_pattern, text):
        return "military"
    # 3. Aids to Navigation (AtoN)
    if any(k in text for k in ["LIGHT", "LIGHTS", "BUOY", "BUOYS", "RACON", "BEACON", "UNLIT", "EXTINGUISHED", "OFF AIR"]):
        return "aton"
    # 4. Subsea / Obstruction
    if any(k in text for k in ["SEISMIC", "CABLE", "PIPELINE", "ROV", "TOWING", "DREDGING", "ANCHOR", "CHAIN LOST", "SUNKEN WRECK"]):
        return "subsea"
    # 5. Drifting hazards
    if any(k in text for k in ["DRIFTING", "DERELICT", "MINE", "CONTAINER", "ADRIFT", "SPACE DEBRIS"]):
        return "drifting"
    # 6. Offshore operations
    if any(k in text for k in ["RIG", "PLATFORM", "JACK-UP"]):
        return "offshore"
    return "general"

def parse_warning(raw_block: str, reference_header: str):
    """
    Parses a single warning block and reference header into database-ready structures.
    Header format example:
      'NAVAREA XI NO.26-0451'
    """
    # 1. Extract warning ID
    header_clean = reference_header.strip()
    
    # Form standardized warning_id:
    # "NAVAREA XI NO.26-0451" -> "NAVAREA XI 0451/26"
    id_match = re.search(r'NO\.(\d{2})-(\d{4})', header_clean)
    if id_match:
        yr_short = id_match.group(1)
        num = id_match.group(2)
        warning_id = f"NAVAREA XI {num}/{yr_short}"
    else:
        warning_id = header_clean.replace("NAVAREA XI ", "").strip()

    # 2. Extract lines & determine title
    lines = [line.strip() for line in raw_block.split('\n') if line.strip()]

    # Check for issued date line (e.g. NO.26-0451       Date:2026/10/09 07 UTC)
    date_pattern = r'Date:(\d{4}/\d{2}/\d{2}\s+\d{2}\s+UTC)'
    issued_text = None
    title = ""

    for line in lines:
        d_match = re.search(date_pattern, line, re.IGNORECASE)
        if d_match and not issued_text:
            issued_text = d_match.group(1)
        elif not title and not d_match and not "NO." in line:
            title = line

    # 3. Parse coordinates
    coords_text, lat, lon, spatial = parse_coordinates(raw_block)

    # 4. Classify hazard
    hazard = classify_hazard(raw_block)

    # 5. Checksum calculation
    checksum = hashlib.sha256(raw_block.encode('utf-8')).hexdigest()

    raw_message = {
        "warning_id": warning_id,
        "source_id": SOURCE_ID,
        "subject_header": header_clean,
        "full_raw_text": raw_block,
        "received_timestamp": datetime.now(timezone.utc).isoformat(),
        "checksum_sha256": checksum
    }

    nav_warning = {
        "warning_id": warning_id,
        "source_id": SOURCE_ID,
        "navarea": NAVAREA_ID,
        "title": title or header_clean,
        "issued_text": issued_text,
        "coordinates": ", ".join(coords_text) if coords_text else None,
        "latitude": lat,
        "longitude": lon,
        "category": hazard,
        "status": "active",
        "raw_text": raw_block
    }

    return raw_message, nav_warning, spatial

def main(input_filename="navarea_xi_warnings.txt", output_filename="parsed_xi_warnings.json"):
    print("=" * 60)
    print("🧭 Japan Coast Guard NAVAREA XI Parser")
    print("=" * 60)
    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: {input_filename} not found.")
        return

    # Match blocks delimited by --- HEADER ---
    pattern = r'--- (.*?) ---\n(.*?)(?=\n--- |$)'
    matches = re.findall(pattern, content, re.DOTALL)

    parsed_data = {
        "raw_messages": [],
        "nav_warnings": [],
        "spatial_features": []
    }

    for header, block in matches:
        raw_msg, nav_warn, spatial = parse_warning(block.strip(), header.strip())
        parsed_data["raw_messages"].append(raw_msg)
        parsed_data["nav_warnings"].append(nav_warn)
        if spatial:
            parsed_data["spatial_features"].append({
                "warning_id": nav_warn["warning_id"],
                "category": nav_warn["category"],
                "geometry": spatial
            })

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Successfully parsed {len(matches)} warnings into '{output_filename}'.")
    print(f"   • {len(parsed_data['raw_messages'])} audit records prepared for 'public.raw_messages'")
    print(f"   • {len(parsed_data['nav_warnings'])} active warnings prepared for 'public.nav_warnings'")
    print(f"   • {len(parsed_data['spatial_features'])} GeoJSON geometries generated")

if __name__ == "__main__":
    main()
