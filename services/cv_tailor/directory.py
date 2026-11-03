#!/usr/bin/env python3
"""
directory.py - Fast on-demand paginated loader for multi-portal ATS career boards.
Supports Master (7,008), Ashby (3,212), Greenhouse (1,894), Lever (1,522), and Workday (380).
"""

import csv
import math
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional


SHEETS = {
    "master": {
        "key": "master",
        "title": "Master Directory",
        "subtitle": "All Platforms Aggregated",
        "path": Path("data/all_companies_master.csv"),
        "ats_default": "all",
        "badge_color": "neutral",
        "icon": "fa-globe",
    },
    "ashby": {
        "key": "ashby",
        "title": "Ashby Portals",
        "subtitle": "Modern Tech & High-Growth Startups",
        "path": Path("data/ashby_master.csv"),
        "ats_default": "ashby",
        "badge_color": "purple",
        "icon": "fa-bolt",
    },
    "greenhouse": {
        "key": "greenhouse",
        "title": "Greenhouse Portals",
        "subtitle": "Global Enterprise & Tech Unicorns",
        "path": Path("data/greenhouse_master.csv"),
        "ats_default": "greenhouse",
        "badge_color": "emerald",
        "icon": "fa-seedling",
    },
    "lever": {
        "key": "lever",
        "title": "Lever Portals",
        "subtitle": "Fast-Scaling Software & Product Teams",
        "path": Path("data/lever_master.csv"),
        "ats_default": "lever",
        "badge_color": "sky",
        "icon": "fa-sliders",
    },
    "workday": {
        "key": "workday",
        "title": "Workday Portals",
        "subtitle": "Fortune 500 & Multinationals",
        "path": Path("data/workday_master.csv"),
        "ats_default": "workday",
        "badge_color": "amber",
        "icon": "fa-building",
    },
}

# Cache sheets in memory to avoid repeated disk reads
_SHEET_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _clean_slug(text: str) -> str:
    """Normalize company name to a safe URL slug for Levels.fyi."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _load_sheet(sheet_key: str) -> List[Dict[str, Any]]:
    """Load and normalize rows for a given sheet."""
    if sheet_key in _SHEET_CACHE:
        return _SHEET_CACHE[sheet_key]

    config = SHEETS.get(sheet_key)
    if not config or not config["path"].is_file():
        return []

    items: List[Dict[str, Any]] = []
    with open(config["path"], encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            name = (row.get("name") or "").strip()
            if not name:
                continue

            ats = (row.get("ats") or config["ats_default"]).strip().lower()
            slug = (row.get("slug") or row.get("slug_or_id") or row.get("tenant") or _clean_slug(name)).strip()
            open_jobs = (row.get("open_jobs") or "").strip()
            board_url = (row.get("board_url") or "").strip()

            # Generate Glassdoor & Levels.fyi search links
            safe_query = urllib.parse.quote(name)
            safe_slug = _clean_slug(name)
            glassdoor_url = f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}"
            levels_url = f"https://www.levels.fyi/companies/{safe_slug}/salaries"
            google_jobs_url = f"https://www.google.com/search?q={safe_query}+jobs+careers"

            items.append({
                "id": idx,
                "name": name,
                "ats": ats,
                "slug": slug,
                "open_jobs": open_jobs if open_jobs else None,
                "board_url": board_url,
                "glassdoor_url": glassdoor_url,
                "levels_url": levels_url,
                "google_jobs_url": google_jobs_url,
            })

    _SHEET_CACHE[sheet_key] = items
    return items


def get_sheets_summary() -> List[Dict[str, Any]]:
    """Return summary metadata for all supported portal sheets."""
    summaries = []
    for key, cfg in SHEETS.items():
        items = _load_sheet(key)
        summaries.append({
            "key": key,
            "title": cfg["title"],
            "subtitle": cfg["subtitle"],
            "badge_color": cfg["badge_color"],
            "icon": cfg["icon"],
            "total_count": len(items),
        })
    return summaries


def get_sheet_page(
    sheet_key: str = "master",
    page: int = 1,
    limit: int = 25,
    query: str = ""
) -> Dict[str, Any]:
    """
    Retrieve a single paginated slice of companies for the requested sheet.
    Only the requested page slice is returned to keep network payloads under ~15KB.
    """
    if sheet_key not in SHEETS:
        sheet_key = "master"

    items = _load_sheet(sheet_key)
    cfg = SHEETS[sheet_key]

    # Apply search filter if query is present
    q = query.strip().lower()
    if q:
        filtered = [
            item for item in items
            if q in item["name"].lower()
            or q in item["slug"].lower()
            or q in item["ats"].lower()
        ]
    else:
        filtered = items

    total = len(filtered)
    limit = max(5, min(limit, 100))
    total_pages = max(1, math.ceil(total / limit))
    page = max(1, min(page, total_pages))

    start = (page - 1) * limit
    end = start + limit
    page_items = filtered[start:end]

    return {
        "sheet_key": sheet_key,
        "sheet_title": cfg["title"],
        "sheet_subtitle": cfg["subtitle"],
        "total_in_sheet": len(items),
        "total_filtered": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "start_index": start + 1 if total > 0 else 0,
        "end_index": min(end, total),
        "items": page_items,
    }
