# ⚓ HELM SCRAPER — NAVAREA XI Sub-Area Ingestion Engine

[![Production Portal](https://img.shields.io/badge/Production%20Portal-Helm.Warning%20Data%20Bank-0070f3?style=for-the-badge&logo=vercel)](https://helmwarning.vercel.app/)
[![NAVAREA XI Pipeline](https://img.shields.io/github/actions/workflow/status/alfredpanakkal/NAVAREA-XI-JAPAN/navarea-xi-sync.yml?branch=main&label=NAVAREA%20XI%20Pipeline&style=for-the-badge&logo=githubactions)](https://github.com/alfredpanakkal/NAVAREA-XI-JAPAN/actions/workflows/navarea-xi-sync.yml)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase)](https://supabase.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Automated radio navigational warning scraper, deterministic parser, coordinate normalizer, and Supabase synchronizer for NAVAREA XI, coordinated by the Japan Coast Guard, powering [Helm.Warning](https://helmwarning.vercel.app/).**

---

## 🌊 Overview

**NAVAREA XI** covers a vast maritime region in the western Pacific Ocean, coordinated by the **Japan Coast Guard**.

This engine harvests official maritime safety broadcasts from the [Japan Coast Guard Navigational Warnings Portal](https://www1.kaiho.mlit.go.jp/TUHO/keiho/navarea11_en.html), normalizes navigational positions (including Degrees-Minutes-Seconds and decimal minutes) into WGS84 coordinates, infers issued dates, classifies maritime hazard semantics, and persists data directly into the Helm.Warning Supabase data bank.

---

## 🗺️ NAVAREA XI Coverage

Broadcasts originate across various sub-regions in the Western Pacific and Southeast Asia, including:
- **North Pacific** (e.g., Marianas, Marshalls, Okinotori Shima)
- **South China Sea**
- **Taiwan Strait**
- **Sulu Sea & Celebes Sea**
- **Singapore & Malacca Straits**
- **Java Sea**
- **Japanese Coastal Waters & Nanpo Shoto**

---

## 🏗️ Architecture Pipeline

```
            [ Japan Coast Guard CGI Endpoints ]
       (www1.kaiho.mlit.go.jp/TUHO/keiho/cgi/warnings.cgi)
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 1: EVIDENCE ACQUISITION                     │
 │  navarea_xi_scraper.py                                          │
 │  • Sends POST requests to CGI endpoints to fetch active IDs     │
 │  • Fetches bulk HTML for all active warnings                    │
 │  • Emits verbatim text ledger (navarea_xi_warnings.txt)         │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 2: DETERMINISTIC REGEX PARSER               │
 │  navarea_xi_parser.py                                           │
 │  • Handles Degrees-Minutes-Seconds & Decimal Minute coordinates │
 │  • Centroid & GeoJSON bounding box polygon computation          │
 │  • Date extraction and temporal inference                       │
 │  • Hazard semantic categorization (military, aton, subsea, etc.)│
 │  • SHA-256 cryptographic bulletin auditing                      │
 │  • Emits structured payload (parsed_xi_warnings.json)           │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 3: SMART DIFFERENTIAL SYNC                  │
 │  navarea_xi_sync.py                                             │
 │  • Pre-sync Supabase state inspection                           │
 │  • SKIPS unchanged bulletins (zero redundant DB writes)         │
 │  • INSERTS new bulletins into public.raw_messages               │
 │  • UPSERTS new/revised bulletins into public.nav_warnings       │
 │  • MARKS status='cancelled' for expired/dropped bulletins       │
 │    (source_id: 'kaiho-navarea-xi', navarea: 'XI')               │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 4: MARITIME PRESENTATION                    │
 │  Helm.Warning Web Portal (Next.js / MapLibre / Vercel)          │
 │  https://helmwarning.vercel.app/                                │
 └─────────────────────────────────────────────────────────────────┘
```

---

## 💾 Database Integration Contract

Fully aligned with the Helm.Warning data bank specification:
- **`source_id`**: `'kaiho-navarea-xi'` (matches `sourcesRegistry.ts`)
- **`navarea`**: `'XI'` (matches `types.ts`)

### Composite Uniqueness:
- `public.raw_messages`: `(warning_id, source_id, checksum_sha256)`
- `public.nav_warnings`: `(warning_id, source_id)`

---

## 🏷️ Hazard Classification

| Category | Keywords & Terminology | Sample NAVAREA XI Findings |
| :--- | :--- | :--- |
| `military` | `DETONATIONS`, `FIRING`, `GUNNERY`, `NAVAL EXERCISES` | Nanpo Shoto gunnery exercises (`0430/26`) |
| `aton` | `LIGHT`, `BUOY`, `RACON`, `BEACON`, `UNLIT`, `OFF AIR` | Guam HF NAVTEX off air (`0400/26`), Apo Island light extinguished (`0387/26`) |
| `subsea` | `PIPELINE`, `CABLE`, `SEISMIC`, `DREDGING`, `SUNKEN WRECK` | Taiwan Strait cable repairs (`0448/26`), Java Sea sunken wreck (`0408/26`) |
| `electronic` | `GNSS`, `DGPS`, `AIS INTERFERENCE`, `JAMMING` | Electronic interference alerts |
| `drifting` | `DRIFTING`, `DERELICT`, `MINE`, `ADRIFT`, `SPACE DEBRIS` | Sulu Sea space debris (`0445/26`), Derelict barge in Marshalls (`0449/26`) |
| `general` | *(Fallback)* | General safety and advisory bulletins |

---

## ⚙️ Quickstart & Local Execution

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Environment Variables (Optional for Supabase Sync)
```bash
# PowerShell:
$env:SUPABASE_URL = "https://your-project.supabase.co"
$env:SUPABASE_KEY = "your-supabase-key"

# Bash:
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-supabase-key"
```

### 3. Run Pipeline
```bash
# Execute end-to-end pipeline in one command:
python run_xi_pipeline.py

# Or step-by-step:
python navarea_xi_scraper.py   # Harvests navarea_xi_warnings.txt
python navarea_xi_parser.py    # Normalizes & emits parsed_xi_warnings.json
python navarea_xi_sync.py      # Syncs to Supabase tables
```

### 4. Run Unit Test Suite
```bash
python -m unittest tests/test_navarea_xi.py
```

---

## 🤖 Cloud Automation (GitHub Actions)

Configured via [`.github/workflows/navarea-xi-sync.yml`](./.github/workflows/navarea-xi-sync.yml).

### Architecture Decision: No Git Commits in CI
Initially, the pipeline committed the scraped and parsed JSON/TXT files back to the repository. This is an anti-pattern that causes `git push` race conditions during concurrent workflow runs.

Instead, the workflow operates as a **State-Free Sync Engine**:
1. **GitHub Actions Artifacts:** Temporary output files (`navarea_xi_warnings.txt` and `parsed_xi_warnings.json`) are uploaded directly as pipeline artifacts.
2. **Supabase Differential Sync:** `navarea_xi_sync.py` connects directly to the production database, diffs the current state, and executes surgical inserts/upserts, making Git entirely unnecessary for data persistence.

### CI Configuration
- **Cron Frequency:** Every 6 hours (`0 */6 * * *`).
- **Manual Trigger:** Supported via `workflow_dispatch`.
- **Required Secrets:** `SUPABASE_URL` and `SUPABASE_KEY` must be configured in GitHub Secrets.
- **Outputs:** Safely synchronizes data to Supabase and publishes verified JSON/TXT as run artifacts, keeping the Git `main` branch pristine.
