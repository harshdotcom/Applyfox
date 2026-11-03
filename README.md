# 🦊 Applyfox

> **The High-Speed ATS Job Board Discovery, Validation, and Market Intelligence Engine.**  
> Automatically discover, validate against official career APIs, count live open jobs, and export structured company datasets across **Greenhouse**, **Lever**, **Workday**, and **Ashby**.

---

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Verified Companies](https://img.shields.io/badge/verified%20companies-7%2C008-brightgreen.svg)](#-live-fetched-results-summary)
[![Active Live Jobs](https://img.shields.io/badge/live%20open%20jobs-393%2C892-orange.svg)](#-live-fetched-results-summary)
[![ATS Supported](https://img.shields.io/badge/ATS-Greenhouse%20%7C%20Lever%20%7C%20Workday%20%7C%20Ashby-purple.svg)](#-supported-applicant-tracking-systems)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 Table of Contents

- [🦊 About Applyfox](#-about-applyfox)
- [📊 Live Fetched Results Summary](#-live-fetched-results-summary)
  - [Overall Multi-Platform Statistics](#overall-multi-platform-statistics)
  - [Top Hiring Companies by Platform](#top-hiring-companies-by-platform)
- [📁 Project Structure](#-project-structure)
- [⚙️ Architecture & Discovery Engine](#️-architecture--discovery-engine)
  - [1. Greenhouse Pipeline](#1-greenhouse-pipeline-gh_discoverpy)
  - [2. Lever Pipeline (Global + EU)](#2-lever-pipeline-lever_discoverpy)
  - [3. Workday Enterprise CXS Pipeline](#3-workday-enterprise-cxs-pipeline-workday_discoverpy)
  - [4. Ashby Pipeline](#4-ashby-pipeline-ashby_discoverpy)
- [🚀 Quickstart & Usage](#-quickstart--usage)
  - [Installation](#installation)
  - [One-Command Orchestration](#one-command-orchestration)
  - [Platform-Specific Execution](#platform-specific-execution)
- [💾 Export Data Schemas](#-export-data-schemas)
- [🏷️ Recommended Repository Names](#️-recommended-repository-names)
- [📜 License](#-license)

---

## 🦊 About Applyfox

Traditional job boards and job aggregators (LinkedIn, Indeed, Google Jobs) suffer from expired listings, ghost jobs, and aggressive rate limits.

**Applyfox** bypasses job board scrapers completely by interfacing directly with the underlying **Applicant Tracking Systems (ATS)** that power company career portals. Using high-throughput multi-threaded HTTP discovery, Common Crawl index queries, and direct REST validation, Applyfox builds verified, canonical databases of companies actively hiring today.

### Core Features:
- **Direct ATS API Validation**: Validates candidate slugs directly against live ATS backend APIs (no headless browser overhead).
- **Live Open Job Counts**: Extracts real-time active vacancy tallies for each verified company board.
- **Multi-Source Discovery**:
  - Curated seed databases (`seeds/`)
  - Petabyte-scale Common Crawl index queries (`CC-MAIN-2024-38`, `CC-MAIN-2026-30`, etc.)
  - Heuristic company name slugifier (`"Warby Parker"` -> `warbyparker`, `warby-parker`, `warbyparkerinc`)
  - Raw GitHub URL repository scraping
- **Multi-Format Persistence**: Exports to **CSV**, **JSON**, **YAML**, and indexed **SQLite** databases.
- **Fail-Safe Throttling**: Thread-safe leaky-bucket rate limiting with connection pooling, exponential backoff, and graceful timeout handling.

---

## 📊 Live Fetched Results Summary

The dataset currently bundled in [`data/`](file:///home/priyanshu/Documents/Applyfox/data) contains **7,008 verified company career boards** and **393,892+ active open jobs**.

### Overall Multi-Platform Statistics

| Applicant Tracking System (ATS) | Verified Boards | Boards with Active Jobs (>0) | Total Open Jobs Tracked | Primary Validation Protocol |
| :--- | :---: | :---: | :---: | :--- |
| **Greenhouse** | **1,894** | 1,762 | 86,999 | `GET boards-api.greenhouse.io/v1/boards/{slug}` |
| **Lever** (Global + EU) | **1,522** | 1,246 | 60,264 | `GET api.lever.co/v0/postings/{slug}?mode=json` |
| **Workday** (Enterprise) | **380** | 380 | 238,210 | `POST {tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` |
| **Ashby** (Modern Tech/AI) | **3,212** | 153+ | 8,419+ | `GET api.ashbyhq.com/posting-api/job-board/{slug}` |
| **TOTAL UNIFIED** | **7,008** | **3,541+** | **393,892+** | *Merged in [`data/all_companies_master.csv`](file:///home/priyanshu/Documents/Applyfox/data/all_companies_master.csv)* |

---

### Top Hiring Companies by Platform

#### 🟢 Greenhouse (`data/greenhouse_master.csv`)
| Company | Open Jobs | Verified Career Board |
| :--- | :---: | :--- |
| **SpaceX** | 2,873 | [boards.greenhouse.io/spacex](https://boards.greenhouse.io/spacex) |
| **Pulse Healthcare** | 2,772 | [boards.greenhouse.io/pulse](https://boards.greenhouse.io/pulse) |
| **Anduril Industries** | 2,567 | [boards.greenhouse.io/andurilindustries](https://boards.greenhouse.io/andurilindustries) |
| **Private Equity Insights** | 1,284 | [boards.greenhouse.io/privateequityinsights](https://boards.greenhouse.io/privateequityinsights) |
| **EquipmentShare** | 1,040 | [boards.greenhouse.io/equipmentsharecom](https://boards.greenhouse.io/equipmentsharecom) |
| **BlueSky Telepsych** | 1,005 | [boards.greenhouse.io/blueskytelepsych](https://boards.greenhouse.io/blueskytelepsych) |
| **Databricks** | 910 | [boards.greenhouse.io/databricks](https://boards.greenhouse.io/databricks) |
| **Meridial** | 827 | [boards.greenhouse.io/agency](https://boards.greenhouse.io/agency) |

#### 🔵 Lever (`data/lever_master.csv`)
| Company | Open Jobs | Verified Career Board |
| :--- | :---: | :--- |
| **BoxLunch & Hot Topic** | 4,612 | [jobs.lever.co/boxlunch](https://jobs.lever.co/boxlunch) |
| **Jobgether** | 4,543 | [jobs.lever.co/jobgether](https://jobs.lever.co/jobgether) |
| **TSMG** | 4,454 | [jobs.lever.co/tsmg](https://jobs.lever.co/tsmg) |
| **AO Garcia Agency** | 3,779 | [jobs.lever.co/aogarciaagency](https://jobs.lever.co/aogarciaagency) |
| **TowardJobs** | 1,573 | [jobs.lever.co/usasurveyjob](https://jobs.lever.co/usasurveyjob) |
| **Contact Government Services (CGS)** | 1,429 | [jobs.lever.co/cgsfederal](https://jobs.lever.co/cgsfederal) |
| **LifeStance Health** | 1,399 | [jobs.lever.co/lifestance](https://jobs.lever.co/lifestance) |
| **Insomnia Cookies** | 1,100 | [jobs.lever.co/insomniacookies](https://jobs.lever.co/insomniacookies) |

#### 🟠 Workday (`data/workday_master.csv`)
| Company / Enterprise Board | Open Jobs | Verified Career Board |
| :--- | :---: | :--- |
| **CVS Health** | 19,080 | [cvshealth.wd1.myworkdayjobs.com/...](https://cvshealth.wd1.myworkdayjobs.com/en-US/CVS_Health_Careers) |
| **Lowe's** | 12,575 | [lowes.wd5.myworkdayjobs.com/...](https://lowes.wd5.myworkdayjobs.com/en-US/LWS_External_CS) |
| **RTX (Raytheon Technologies)** | 4,676 | [globalhr.wd5.myworkdayjobs.com/...](https://globalhr.wd5.myworkdayjobs.com/en-US/rec_rtx_ext_gateway) |
| **Northrop Grumman** | 3,747 | [ngc.wd1.myworkdayjobs.com/...](https://ngc.wd1.myworkdayjobs.com/en-US/Northrop_Grumman_External_Site) |
| **Amentum / PAE** | 2,923 | [pae.wd1.myworkdayjobs.com/...](https://pae.wd1.myworkdayjobs.com/en-US/amentum_careers) |
| **Micron Technology** | 2,910 | [micron.wd1.myworkdayjobs.com/...](https://micron.wd1.myworkdayjobs.com/en-US/External) |
| **Target** | 2,514 | [target.wd5.myworkdayjobs.com/...](https://target.wd5.myworkdayjobs.com/en-US/targetcareers) |
| **Walmart** | 2,423 | [walmart.wd5.myworkdayjobs.com/...](https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal) |

#### 🟣 Ashby (`data/ashby_master.csv`)
| Company | Open Jobs | Verified Career Board |
| :--- | :---: | :--- |
| **OpenAI** | 809 | [jobs.ashbyhq.com/openai](https://jobs.ashbyhq.com/openai) |
| **Harvey** | 379 | [jobs.ashbyhq.com/harvey](https://jobs.ashbyhq.com/harvey) |
| **Snowflake** | 367 | [jobs.ashbyhq.com/snowflake](https://jobs.ashbyhq.com/snowflake) |
| **Applied Intuition** | 321 | [jobs.ashbyhq.com/applied](https://jobs.ashbyhq.com/applied) |
| **Saronic Technologies** | 255 | [jobs.ashbyhq.com/saronic](https://jobs.ashbyhq.com/saronic) |
| **Sierra** | 219 | [jobs.ashbyhq.com/sierra](https://jobs.ashbyhq.com/sierra) |
| **Base Power Company** | 191 | [jobs.ashbyhq.com/base-power](https://jobs.ashbyhq.com/base-power) |
| **Linear** | 24 | [jobs.ashbyhq.com/linear](https://jobs.ashbyhq.com/linear) |

---

## 📁 Project Structure

```text
applyfox/
├── README.md                   # Complete documentation, benchmarks, and API guides
├── requirements.txt            # Python dependencies (requests, pyyaml)
├── LICENSE                     # MIT License
├── .gitignore                  # Git hygiene rules
│
├── run_all.py                  # Master CLI runner & orchestrator
├── gh_discover.py              # Greenhouse ATS discovery & validation engine
├── lever_discover.py           # Lever ATS discovery & validation engine (Global + EU)
├── workday_discover.py         # Workday CXS enterprise validation engine
├── ashby_discover.py           # Ashby Posting API discovery engine
│
├── data/                       # Validated master datasets & SQLite databases
│   ├── all_companies_master.csv    # 7,008 companies across all 4 platforms
│   ├── greenhouse_master.csv       # 1,894 Greenhouse companies
│   ├── greenhouse_master.json
│   ├── greenhouse_master.yaml
│   ├── gh_master.db                # SQLite DB with indexed slugs & statuses
│   ├── lever_master.csv            # 1,522 Lever companies
│   ├── lever_master.json
│   ├── lever_master.yaml
│   ├── lever_master.db
│   ├── workday_master.csv          # 380 Workday career portals
│   ├── workday_master.json
│   ├── workday_master.yaml
│   ├── workday_master.db
│   ├── ashby_master.csv            # 3,212 Ashby companies
│   ├── ashby_master.json
│   ├── ashby_master.yaml
│   ├── ashby_master.db
│   └── ashby_companies.csv         # Curated final Ashby dataset
│
└── seeds/                      # Input seed lists & pre-crawled directories
    ├── greenhouse_seed.yaml
    ├── lever_seed.yaml
    ├── lever_directory.json        # Curated 23k+ candidate Lever directory
    ├── workday_seed.yaml
    ├── workday_directory.json      # Curated 2.6k+ candidate Workday directory
    ├── ashby_seed.yaml
    ├── ashby_directory.json        # Curated 3.2k+ candidate Ashby directory
    └── names.txt                   # Standard seed company names
```

---

## ⚙️ Architecture & Discovery Engine

Applyfox uses lightweight, targeted network probes to discover candidate slugs and confirm their validity via authoritative JSON APIs:

```mermaid
flowchart TD
    A["Discovery Sources<br/>(Seeds, Dictionaries, Common Crawl, Names)"] --> B["Candidate Normalizer<br/>(Extract slugs, tenants, sites)"]
    B --> C["Local SQLite Cache<br/>(State: pending, valid, invalid)"]
    D["Multi-Threaded Worker Pool<br/>(Rate limited & Thread-safe)"]
    C --> D

    D -->|"boards-api.greenhouse.io"| E["Greenhouse Engine<br/>1,894 Boards"]
    D -->|"api.lever.co & api.eu.lever.co"| F["Lever Engine<br/>1,522 Boards"]
    D -->|"CXS POST JSON Endpoint"| G["Workday Engine<br/>380 Boards"]
    D -->|"api.ashbyhq.com/posting-api"| H["Ashby Engine<br/>3,212 Boards"]

    E & F & G & H --> I["Export Pipeline<br/>(CSV, JSON, YAML, SQLite)"]
    I --> J["Unified Master Dataset<br/>7,008 Companies"]
```

### 1. Greenhouse Pipeline (`gh_discover.py`)
- **Metadata Endpoint**: `GET https://boards-api.greenhouse.io/v1/boards/{slug}`
- **Jobs Endpoint**: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
- **Logic**: Returns HTTP 200 with company name and configuration. An optional secondary request retrieves the full active job array.

### 2. Lever Pipeline (`lever_discover.py`)
- **Global Endpoint**: `GET https://api.lever.co/v0/postings/{slug}?mode=json`
- **EU Endpoint**: `GET https://api.eu.lever.co/v0/postings/{slug}?mode=json`
- **Logic**: Checks the US endpoint first. If HTTP 404, automatically attempts the European endpoint (`api.eu.lever.co`). Both return the job postings list directly in a single request, optimizing throughput.

### 3. Workday Enterprise CXS Pipeline (`workday_discover.py`)
- **Endpoint**: `POST https://{tenant}.{wd_instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
- **Payload**: `{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}`
- **Logic**: Workday career portals are Single Page Applications (SPAs) that do not render job details in static HTML. Applyfox directly invokes Workday's internal Client Experience Service (`wday/cxs`) API, which responds with `total` live job counts and company metadata in milliseconds.

### 4. Ashby Pipeline (`ashby_discover.py`)
- **Endpoint**: `GET https://api.ashbyhq.com/posting-api/job-board/{slug}`
- **Logic**: Ashby powers modern tech and AI startups. The public posting API returns an object containing `jobs: [...]`, title, department, employment type, and location data. Company names are resolved from page titles or structured metadata.

---

## 🚀 Quickstart & Usage

### Installation

Requires Python 3.8+:

```bash
git clone https://github.com/your-username/applyfox.git
cd applyfox
pip install -r requirements.txt
```

### One-Command Orchestration

To run the complete pipeline across all 4 ATS platforms with parallel workers, rate limiting, and automated master dataset compilation:

```bash
# Run all platforms with live open job counts (8 parallel workers)
python run_all.py

# Run only specific platforms
python run_all.py --ats greenhouse ashby

# Fast board validation without job counts
python run_all.py --no-jobs --workers 12
```

### Platform-Specific Execution

Each discovery engine can be executed independently with granular flags:

```bash
# --- Greenhouse ---
python gh_discover.py --seed seeds/greenhouse_seed.yaml --jobs
python gh_discover.py --names seeds/names.txt --jobs
python gh_discover.py --cc --max-cc-pages 100

# --- Lever ---
python lever_discover.py --directory seeds/lever_directory.json --jobs --workers 10
python lever_discover.py --seed seeds/lever_seed.yaml --jobs

# --- Workday ---
python workday_discover.py --directory seeds/workday_directory.json --jobs --workers 8
python workday_discover.py --seed seeds/workday_seed.yaml --jobs

# --- Ashby ---
python ashby_discover.py --directory seeds/ashby_directory.json --jobs
python ashby_discover.py --seed seeds/ashby_seed.yaml --jobs
```

---

## 💾 Export Data Schemas

### Unified Master (`data/all_companies_master.csv`)
Contains all validated companies across every platform:

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `name` | string | Normalized company name | `OpenAI` |
| `ats` | string | ATS platform identifier (`greenhouse`, `lever`, `workday`, `ashby`) | `ashby` |
| `slug_or_id` | string | Unique identifier, slug, or composite key | `openai` |
| `open_jobs` | integer | Live open job count | `809` |
| `board_url` | string | Direct link to public career portal | `https://jobs.ashbyhq.com/openai` |

---

## 🎯 Applyfox CV Studio & Job Application Tracker (`cv_service.py`)

Applyfox includes an intelligent LaTeX CV tailoring engine and persistent job application tracker designed for [`data/main.tex`](file:///home/priyanshu/Documents/Applyfox/data/main.tex).

### Key Features:
- **Overleaf-Grade LaTeX PDF Compilation Engine**: Built-in standalone TeX compiler (`bin/tectonic`) that renders pristine, authentic single-page PDFs directly from LaTeX source code. No HTML-to-PDF conversions or browser print dialogs—pure vector typesetting with full hyperref link support.
- **Precise Section Tailoring**: Intelligently analyzes any target Job Description (JD) and adapts:
  - `%-----------PROFILE-----------`: Re-aligns lead title, emphasis, and core competencies to match the role archetype (AI/GenAI, Backend, DevOps, Distributed Systems).
  - `%-----------TECHNICAL SKILLS-----------`: Re-orders skill categories and front-loads matching technologies while preserving authentic verified skills.
  - `%-----------PROJECTS-----------`: Dynamically adjusts project header tech-stack tags (e.g. `VitaTrack.ai` and `AI Agent Workflow System`) to match the JD stack.
- **Master Job Application Tracker ("The Sheet")**:
  - Automatically records every application in [`data/job_applications_tracker.csv`](file:///home/priyanshu/Documents/Applyfox/data/job_applications_tracker.csv) and JSON database.
  - Tracks **Company Name**, **Job Title**, **Application Date**, **Referral Status & Referrer Name/Contact**, **Match Score**, and **Archive Path**.
- **Full Version Archival & Real PDF Artifacts**:
  - Stores each application in `data/applications/<APP-ID>_<company>/` with the exact `.tex` source, compiled `.pdf`, full metadata JSON, and paper preview for future reference and interview prep.
- **Multi-Portal Directory Sheets & Career Intelligence**:
  - Browse **7,008 career boards** across dedicated sheets: **Master (7,008)**, **Ashby (3,212)**, **Greenhouse (1,894)**, **Lever (1,522)**, and **Workday (380)**.
  - On-demand server-side pagination with isolated sheet loading (loads only 25–100 rows at a time, preserving speed and memory).
  - Integrated with **Levels.fyi** (live compensation benchmarks) and **Glassdoor** (interview reviews & ratings).
  - 1-click **"Tailor CV"** action to load any company and career board URL straight into the Studio.
- **Editorial Minimalist Design System**:
  - Warm organic paper canvas with subtle architectural grid, editorial serif typography, and dark developer diagnostics bar inspired by modern developer animation and coding studios.
- **Interactive Web Studio**:
  - Built-in local web server with autocomplete across **7,008 verified companies**, live compiled PDF preview, visual paper preview, section diffs, editable LaTeX source with instant recompile, and 1-click PDF download.

### Usage:

```bash
# 1. Launch interactive Web Studio & Application Tracker UI
python cv_service.py serve --port 8080

# 2. Tailor CV directly via CLI with instant tracking
python cv_service.py tailor --company "OpenAI" --title "AI Agent Engineer" --jd "path/to/jd.txt" --save

# 3. Interactive Terminal Wizard
python cv_service.py interactive

# 4. View Application Tracking Sheet in Terminal
python cv_service.py list

# 5. Retrieve an exact previously sent CV version
python cv_service.py get APP-OPENAI-20261103-3458 --tex
```

---

## 🏷️ Recommended Repository Names

For publishing this repository on GitHub:

| Option | Repository Name | Tagline & Positioning |
| :---: | :--- | :--- |
| **1 (Chosen)** | **`applyfox`** | **Modern, brandable, memorable animal name (like Firefox, GitLab, Celery). Ideal for a standalone product or community tool.** |
| **2** | **`ats-radar`** | High-utility, search-optimized for developers looking for ATS board discovery. |
| **3** | **`applyfox-engine`** | Clarifies the backend/engine nature of the pipeline for data ingestion. |
| **4** | **`hire-scout`** | Friendly, developer-first recruitment intelligence brand. |
| **5** | **`open-career-pipeline`** | Emphasizes open-source job data aggregation and ATS transparency. |

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

