#!/usr/bin/env python3
"""
run_xi_pipeline.py — End-to-End NAVAREA XI Ingestion Pipeline
Chains Stage 1 (Scraper), Stage 2 (Parser), and Stage 3 (Supabase Sync).
"""

import sys
import os

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import navarea_xi_scraper
import navarea_xi_parser
import navarea_xi_sync

def main():
    print("=" * 65)
    print("⚓ STARTING NAVAREA XI AUTOMATED INGESTION PIPELINE")
    print("=" * 65)

    # Stage 1: Scrape
    print("\n[STAGE 1] Scraping bulletins from Japan Coast Guard endpoint...")
    navarea_xi_scraper.scrape_xi_warnings(output_filename="navarea_xi_warnings.txt")

    # Stage 2: Parse
    print("\n[STAGE 2] Parsing bulletins, normalizing WGS84 coords & GeoJSON...")
    navarea_xi_parser.main(input_filename="navarea_xi_warnings.txt", output_filename="parsed_xi_warnings.json")

    # Stage 3: Sync
    print("\n[STAGE 3] Synchronizing records to Supabase...")
    navarea_xi_sync.sync_to_supabase(json_file="parsed_xi_warnings.json")

    print("\n" + "=" * 65)
    print("🎉 NAVAREA XI PIPELINE EXECUTION COMPLETED")
    print("=" * 65)

if __name__ == "__main__":
    main()
