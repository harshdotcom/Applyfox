#!/usr/bin/env python3
"""
directory.py - Fast on-demand paginated loader for multi-portal ATS career boards
and 2026 Startup Funding & Failures Intelligence.
Supports:
  - Master Directory (7,406 total companies across all ATS boards & funded startups)
  - Ashby Portals (3,212)
  - Greenhouse Portals (1,894)
  - Lever Portals (1,522)
  - Workday Portals (380)
  - 2026 Funded Startups (480 Series A-D rounds, month-wise filtered)
  - 2026 Failures & Distress (23 startup post-mortems with market risk lessons)
"""

import csv
import json
import math
import re
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


SHEETS = {
    "funded_startups": {
        "key": "funded_startups",
        "title": "2026 Funded Startups",
        "subtitle": "Series A-D Rounds Month-Wise (Jan - Nov 2026)",
        "path": Path("data/funded_startups_2026.json"),
        "ats_default": "funded-2026",
        "badge_color": "amber",
        "icon": "fa-rocket",
        "kind": "funded_startups",
    },
    "startup_failures": {
        "key": "startup_failures",
        "title": "Failures & Distress 2026",
        "subtitle": "Startup Post-Mortems & Risk Signals",
        "path": Path("data/startup_failures_2026.json"),
        "ats_default": "distressed",
        "badge_color": "rose",
        "icon": "fa-triangle-exclamation",
        "kind": "startup_failures",
    },
    "master": {
        "key": "master",
        "title": "Master Directory",
        "subtitle": "All Platforms & Startups Aggregated",
        "path": Path("data/all_companies_master.csv"),
        "ats_default": "all",
        "badge_color": "neutral",
        "icon": "fa-globe",
        "kind": "standard",
    },
    "ashby": {
        "key": "ashby",
        "title": "Ashby Portals",
        "subtitle": "Modern Tech & High-Growth Startups",
        "path": Path("data/ashby_master.csv"),
        "ats_default": "ashby",
        "badge_color": "purple",
        "icon": "fa-bolt",
        "kind": "standard",
    },
    "greenhouse": {
        "key": "greenhouse",
        "title": "Greenhouse Portals",
        "subtitle": "Global Enterprise & Tech Unicorns",
        "path": Path("data/greenhouse_master.csv"),
        "ats_default": "greenhouse",
        "badge_color": "emerald",
        "icon": "fa-seedling",
        "kind": "standard",
    },
    "lever": {
        "key": "lever",
        "title": "Lever Portals",
        "subtitle": "Fast-Scaling Software & Product Teams",
        "path": Path("data/lever_master.csv"),
        "ats_default": "lever",
        "badge_color": "sky",
        "icon": "fa-sliders",
        "kind": "standard",
    },
    "workday": {
        "key": "workday",
        "title": "Workday Portals",
        "subtitle": "Fortune 500 & Multinationals",
        "path": Path("data/workday_master.csv"),
        "ats_default": "workday",
        "badge_color": "amber",
        "icon": "fa-building",
        "kind": "standard",
    },
}

# Cache sheets in memory to avoid repeated disk reads
_SHEET_CACHE: Dict[str, List[Dict[str, Any]]] = {}

# Centralized open roles repository
_GLOBAL_ROLES: Dict[str, List[Dict[str, Any]]] = {}
_ROLES_PATH = Path("data/company_open_roles.json")
if _ROLES_PATH.is_file():
    try:
        _GLOBAL_ROLES = json.loads(_ROLES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error loading company_open_roles.json: {e}")


def _clean_slug(text: str) -> str:
    """Normalize company name to a safe URL slug for Levels.fyi."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _get_roles_for_company(name: str, slug: str = "") -> List[Dict[str, Any]]:
    """Lookup structured open roles from global repository."""
    name_low = name.lower().strip()
    slug_low = slug.lower().strip()
    if name_low in _GLOBAL_ROLES:
        return _GLOBAL_ROLES[name_low]
    if slug_low and slug_low in _GLOBAL_ROLES:
        return _GLOBAL_ROLES[slug_low]
    return []


def _load_sheet(sheet_key: str) -> List[Dict[str, Any]]:
    """Load and normalize rows for a given sheet."""
    if sheet_key in _SHEET_CACHE:
        return _SHEET_CACHE[sheet_key]

    config = SHEETS.get(sheet_key)
    if not config or not config["path"].is_file():
        return []

    kind = config.get("kind", "standard")

    # 1. Funded Startups (JSON)
    if kind == "funded_startups":
        try:
            raw_data = json.loads(config["path"].read_text(encoding="utf-8"))
            items = []
            for item in raw_data:
                comp = item.get("name", "").strip()
                if not comp:
                    continue
                safe_query = urllib.parse.quote(comp)
                safe_slug = item.get("slug") or _clean_slug(comp)
                website = item.get("website", "").strip()
                board_url = website if website else f"https://www.google.com/search?q={safe_query}+jobs+careers"
                round_val = item.get("round", "")
                amount_val = item.get("amount", "")
                open_jobs_label = f"{round_val} ({amount_val})" if round_val and amount_val else (round_val or amount_val or "Funded 2026")
                roles = item.get("roles") or _get_roles_for_company(comp, safe_slug)

                items.append({
                    "id": item.get("id"),
                    "name": comp,
                    "ats": "funded-2026",
                    "slug": safe_slug,
                    "kind": "funded_startups",
                    "website": website,
                    "country": item.get("country", ""),
                    "region": item.get("region", ""),
                    "sector": item.get("sector", ""),
                    "what_they_build": item.get("what_they_build", ""),
                    "round": round_val,
                    "amount": amount_val,
                    "amount_usd_m": item.get("amount_usd_m", ""),
                    "announced_date": item.get("announced_date", ""),
                    "month": item.get("month", "Month not disclosed"),
                    "lead_investors": item.get("lead_investors", ""),
                    "valuation": item.get("valuation", ""),
                    "total_funding": item.get("total_funding", ""),
                    "status": item.get("status", "Active"),
                    "failed_reason": item.get("failed_reason", ""),
                    "outlook": item.get("outlook", ""),
                    "outlook_reasoning": item.get("outlook_reasoning", ""),
                    "source": item.get("source", ""),
                    "open_jobs": open_jobs_label,
                    "roles": roles,
                    "board_url": board_url,
                    "glassdoor_url": item.get("glassdoor_url") or f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}",
                    "levels_url": item.get("levels_url") or f"https://www.levels.fyi/companies/{safe_slug}/salaries",
                    "google_jobs_url": item.get("google_jobs_url") or f"https://www.google.com/search?q={safe_query}+jobs+careers",
                })
            _SHEET_CACHE[sheet_key] = items
            return items
        except Exception as e:
            print(f"Error loading funded_startups: {e}")
            return []

    # 2. Startup Failures (JSON)
    if kind == "startup_failures":
        try:
            raw_data = json.loads(config["path"].read_text(encoding="utf-8"))
            items = []
            for item in raw_data:
                comp = item.get("name", "").strip()
                if not comp:
                    continue
                safe_query = urllib.parse.quote(comp)
                safe_slug = item.get("slug") or _clean_slug(comp)
                funding_before = item.get("funding_before_failure", "")

                items.append({
                    "id": item.get("id"),
                    "name": comp,
                    "ats": "distressed",
                    "slug": safe_slug,
                    "kind": "startup_failures",
                    "country": item.get("country", ""),
                    "sector": item.get("sector", ""),
                    "funding_before_failure": funding_before,
                    "when_date": item.get("when_date", ""),
                    "what_happened": item.get("what_happened", ""),
                    "precise_reason": item.get("precise_reason", ""),
                    "lesson": item.get("lesson", ""),
                    "source": item.get("source", ""),
                    "open_jobs": funding_before[:35] if funding_before else "Distressed 2026",
                    "board_url": item.get("google_jobs_url") or f"https://www.google.com/search?q={safe_query}+startup+news",
                    "glassdoor_url": item.get("glassdoor_url") or f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}",
                    "levels_url": item.get("levels_url") or f"https://www.levels.fyi/companies/{safe_slug}/salaries",
                    "google_jobs_url": item.get("google_jobs_url") or f"https://www.google.com/search?q={safe_query}+startup+news",
                })
            _SHEET_CACHE[sheet_key] = items
            return items
        except Exception as e:
            print(f"Error loading startup_failures: {e}")
            return []

    # 3. Standard CSV Sheets
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

            safe_query = urllib.parse.quote(name)
            safe_slug = _clean_slug(name)
            glassdoor_url = f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}"
            levels_url = f"https://www.levels.fyi/companies/{safe_slug}/salaries"
            google_jobs_url = f"https://www.google.com/search?q={safe_query}+jobs+careers"

            roles = _get_roles_for_company(name, slug)
            if not roles and row.get("roles"):
                roles = [
                    {"title": r.strip(), "department": "General", "level": "Senior", "location": "Remote", "type": "Full-time"}
                    for r in row["roles"].split(";") if r.strip()
                ]

            items.append({
                "id": idx,
                "name": name,
                "ats": ats,
                "slug": slug,
                "kind": "standard",
                "open_jobs": open_jobs if open_jobs else None,
                "roles": roles,
                "board_url": board_url,
                "glassdoor_url": glassdoor_url,
                "levels_url": levels_url,
                "google_jobs_url": google_jobs_url,
            })

    _SHEET_CACHE[sheet_key] = items
    return items


def get_sheets_summary() -> List[Dict[str, Any]]:
    """Return summary metadata for all supported portal and startup sheets."""
    summaries = []
    for key, cfg in SHEETS.items():
        items = _load_sheet(key)
        summary: Dict[str, Any] = {
            "key": key,
            "title": cfg["title"],
            "subtitle": cfg["subtitle"],
            "badge_color": cfg["badge_color"],
            "icon": cfg["icon"],
            "kind": cfg.get("kind", "standard"),
            "total_count": len(items),
        }

        # If funded startups, include month breakdown
        if cfg.get("kind") == "funded_startups":
            month_counts = Counter([it.get("month") for it in items if it.get("month")])
            ordered_months = [
                "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026",
                "Jul 2026", "Aug 2026", "Sep 2026", "Oct 2026", "Nov 2026", "Month not disclosed"
            ]
            months_data = [{"name": "All Months", "count": len(items)}]
            for m in ordered_months:
                if m in month_counts:
                    months_data.append({"name": m, "count": month_counts[m]})
            summary["months"] = months_data

        summaries.append(summary)
    return summaries


def get_sheet_page(
    sheet_key: str = "master",
    page: int = 1,
    limit: int = 25,
    query: str = "",
    month: str = "",
    role: str = "",
    work_mode: str = "",
    level: str = ""
) -> Dict[str, Any]:
    """
    Retrieve a single paginated slice of companies for the requested sheet.
    Supports month filtering, role/discipline, work mode (remote/hybrid/onsite),
    seniority level, and multi-field search.
    """
    if sheet_key not in SHEETS:
        sheet_key = "master"

    items = _load_sheet(sheet_key)
    cfg = SHEETS[sheet_key]
    kind = cfg.get("kind", "standard")

    filtered = items

    # Apply month filter if funded startups
    if kind == "funded_startups" and month and month.lower() not in ("all", "all months"):
        m_lower = month.strip().lower()
        filtered = [it for it in filtered if it.get("month", "").lower() == m_lower]

    # Apply role / job title / discipline filter
    if role and role.strip().lower() not in ("all", "all roles", "all job titles", "all titles", "all disciplines"):
        r_lower = role.strip().lower()
        filtered = [
            it for it in filtered
            if any(
                r_lower in ro.get("title", "").lower()
                or r_lower in ro.get("department", "").lower()
                or ro.get("department", "").lower() in r_lower
                or any(word in ro.get("department", "").lower() or word in ro.get("title", "").lower() for word in r_lower.split() if len(word) > 3)
                for ro in it.get("roles", [])
            )
            or (isinstance(it.get("roles"), str) and (r_lower in it.get("roles", "").lower() or it.get("roles", "").lower() in r_lower))
        ]

    # Apply work mode filter (remote, hybrid, onsite)
    if work_mode and work_mode.strip().lower() not in ("all", "all modes", "all locations"):
        w_lower = work_mode.strip().lower()
        filtered = [
            it for it in filtered
            if any(
                w_lower in ro.get("location", "").lower()
                for ro in it.get("roles", [])
            )
        ]

    # Apply seniority level filter (entry, mid, senior, lead, staff, director)
    if level and level.strip().lower() not in ("all", "all levels", "all seniorities"):
        l_lower = level.strip().lower()
        filtered = [
            it for it in filtered
            if any(
                l_lower in ro.get("level", "").lower()
                for ro in it.get("roles", [])
            )
        ]

    # Apply search filter if query is present
    q = query.strip().lower()
    if q:
        if kind == "funded_startups":
            filtered = [
                it for it in filtered
                if q in it.get("name", "").lower()
                or q in it.get("sector", "").lower()
                or q in it.get("country", "").lower()
                or q in it.get("round", "").lower()
                or q in it.get("lead_investors", "").lower()
                or q in it.get("what_they_build", "").lower()
                or q in it.get("region", "").lower()
                or q in it.get("month", "").lower()
            ]
        elif kind == "startup_failures":
            filtered = [
                it for it in filtered
                if q in it.get("name", "").lower()
                or q in it.get("sector", "").lower()
                or q in it.get("country", "").lower()
                or q in it.get("what_happened", "").lower()
                or q in it.get("precise_reason", "").lower()
                or q in it.get("lesson", "").lower()
            ]
        else:
            filtered = [
                it for it in filtered
                if q in it.get("name", "").lower()
                or q in it.get("slug", "").lower()
                or q in it.get("ats", "").lower()
            ]

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
        "kind": kind,
        "total_in_sheet": len(items),
        "total_filtered": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "start_index": start + 1 if total > 0 else 0,
        "end_index": min(end, total),
        "month_filter": month,
        "role_filter": role,
        "work_mode_filter": work_mode,
        "level_filter": level,
        "items": page_items,
    }
