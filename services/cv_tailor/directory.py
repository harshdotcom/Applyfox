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
    if query and query.strip():
        filtered = [it for it in filtered if _matches_company_search(it, query, kind)]

    total = len(filtered)
    limit = max(5, min(limit, 5000))
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


def _normalize_search_text(text: str) -> str:
    """Normalize text by replacing special characters and punctuation with spaces."""
    return re.sub(r"[^a-zA-Z0-9\s]", " ", (text or "").lower())


def _matches_company_search(item: Dict[str, Any], query: str, kind: str) -> bool:
    """
    Intelligent tokenized search matching company metadata, sector, what they build,
    and all active open positions (titles, departments, seniority, work mode).
    """
    if not query or not query.strip():
        return True

    q_norm = _normalize_search_text(query)
    tokens = [t for t in q_norm.split() if t]
    if not tokens:
        return True

    comp_parts = [
        item.get("name", ""),
        item.get("slug", ""),
        item.get("ats", ""),
        item.get("sector", ""),
        item.get("what_they_build", ""),
        item.get("lead_investors", ""),
        item.get("country", ""),
        item.get("round", ""),
        item.get("what_happened", ""),
        item.get("precise_reason", ""),
        item.get("lesson", "")
    ]
    comp_norm = _normalize_search_text(" ".join(str(p) for p in comp_parts if p))

    roles = item.get("roles", [])
    role_norms = []
    if isinstance(roles, list):
        for r in roles:
            if isinstance(r, dict):
                r_text = f"{r.get('title', '')} {r.get('department', '')} {r.get('level', '')} {r.get('location', '')}"
                role_norms.append(_normalize_search_text(r_text))
            elif isinstance(r, str):
                role_norms.append(_normalize_search_text(r))
    elif isinstance(roles, str):
        role_norms.append(_normalize_search_text(roles))

    if q_norm in comp_norm:
        return True
    if any(q_norm in rn for rn in role_norms):
        return True
    if all(t in comp_norm for t in tokens):
        return True
    if any(all(t in rn for t in tokens) for rn in role_norms):
        return True

    # Domain synonyms and intent mapping
    if any(t in ("ui", "ux", "uiux", "design", "designer", "graphic", "figma", "frontend") for t in tokens):
        if any("ui" in rn or "ux" in rn or "design" in rn or "graphic" in rn for rn in role_norms):
            return True
    if any(t in ("legal", "law", "lawyer", "counsel", "compliance", "contracts", "attorney", "regulatory") for t in tokens):
        if any("legal" in rn or "compliance" in rn or "counsel" in rn or "contracts" in rn for rn in role_norms):
            return True
    if any(t in ("it", "sysadmin", "devops", "cloud", "infra", "infrastructure", "security", "sre", "network") for t in tokens):
        if any("it" in rn.split() or "cloud" in rn or "systems" in rn or "security" in rn or "infrastructure" in rn for rn in role_norms):
            return True
    if any(t in ("pm", "product", "ops", "operations", "tpm", "program", "scrum", "agile") for t in tokens):
        if any("product" in rn or "operations" in rn or "program" in rn for rn in role_norms):
            return True
    if any(t in ("ai", "ml", "engineer", "software", "backend", "fullstack", "python", "developer", "golang", "react") for t in tokens):
        if any("software" in rn or "engineer" in rn or "developer" in rn or "ai" in rn.split() for rn in role_norms):
            return True

    return False


_FLAT_ROLES_CACHE: Optional[List[Dict[str, Any]]] = None

def _get_all_roles() -> List[Dict[str, Any]]:
    global _FLAT_ROLES_CACHE
    if _FLAT_ROLES_CACHE is not None:
        return _FLAT_ROLES_CACHE

    companies = _load_sheet("master")
    flat = []
    for it in companies:
        c_name = it.get("name", "")
        c_slug = it.get("slug", "")
        c_ats = it.get("ats", "")
        c_board = it.get("board_url", "")
        c_levels = it.get("levels_url", "")
        c_glassdoor = it.get("glassdoor_url", "")
        roles = it.get("roles", [])
        if isinstance(roles, list):
            for idx, r in enumerate(roles):
                if isinstance(r, dict):
                    title = r.get("title", "")
                    dept = r.get("department", "Engineering & AI")
                    lvl = r.get("level", "Mid-Senior")
                    loc = r.get("location", "Remote / Hybrid")
                    rtype = r.get("type", "Full-time")

                    salary = "$160k – $215k"
                    l_lower = lvl.lower()
                    if any(x in l_lower for x in ("lead", "staff", "principal")):
                        salary = "$195k – $265k"
                    elif any(x in l_lower for x in ("director", "exec", "vp", "head")):
                        salary = "$240k – $350k"
                    elif "mid" in l_lower:
                        salary = "$125k – $165k"
                    elif any(x in l_lower for x in ("entry", "junior")):
                        salary = "$95k – $135k"

                    d_lower = dept.lower()
                    skills = ["Python", "FastAPI", "PostgreSQL", "Docker"]
                    if "design" in d_lower or "graphic" in d_lower or "ui" in d_lower:
                        skills = ["Figma", "Design Systems", "Prototyping", "UI/UX"]
                    elif "legal" in d_lower or "compliance" in d_lower:
                        skills = ["Commercial Contracts", "Compliance", "IP Law", "Risk Management"]
                    elif "it" in d_lower or "cloud" in d_lower:
                        skills = ["AWS/GCP", "Kubernetes", "Linux", "Cybersecurity", "Terraform"]
                    elif "product" in d_lower or "ops" in d_lower:
                        skills = ["Product Roadmap", "User Metrics", "Agile", "Cross-functional Leadership"]

                    encoded_comp = urllib.parse.quote_plus(f"{c_name} {title} job")
                    flat.append({
                        "id": f"{c_slug}_{idx}",
                        "title": title,
                        "company": c_name,
                        "slug": c_slug,
                        "ats": c_ats,
                        "department": dept,
                        "level": lvl,
                        "location": loc,
                        "type": rtype,
                        "salary_estimate": salary,
                        "skills": skills,
                        "board_url": c_board,
                        "google_jobs_url": f"https://www.google.com/search?q={encoded_comp}",
                        "levels_url": c_levels,
                        "glassdoor_url": c_glassdoor
                    })
    _FLAT_ROLES_CACHE = flat
    return _FLAT_ROLES_CACHE


def get_roles_page(
    page: int = 1,
    limit: int = 25,
    query: str = "",
    discipline: str = "",
    work_mode: str = "",
    level: str = ""
) -> Dict[str, Any]:
    """Retrieve paginated list of individual open roles with multi-dimension filters."""
    roles = _get_all_roles()
    filtered = roles

    # Discipline filter
    if discipline and discipline.strip().lower() not in ("all", "all disciplines", "all roles", "all job titles"):
        d_lower = discipline.strip().lower()
        filtered = [
            r for r in filtered
            if d_lower in r["department"].lower()
            or d_lower in r["title"].lower()
            or r["department"].lower() in d_lower
            or any(w in r["department"].lower() or w in r["title"].lower() for w in d_lower.split() if len(w) > 3)
        ]

    # Work mode filter
    if work_mode and work_mode.strip().lower() not in ("all", "all locations", "all modes"):
        w_lower = work_mode.strip().lower()
        filtered = [r for r in filtered if w_lower in r["location"].lower()]

    # Seniority level filter
    if level and level.strip().lower() not in ("all", "all seniorities", "all levels"):
        l_lower = level.strip().lower()
        filtered = [r for r in filtered if l_lower in r["level"].lower()]

    # Query search
    if query and query.strip():
        q_norm = _normalize_search_text(query)
        tokens = [t for t in q_norm.split() if t]
        if tokens:
            def _role_matches(r):
                r_text = _normalize_search_text(f"{r['title']} {r['company']} {r['department']} {r['level']} {r['location']} {r['ats']} {' '.join(r['skills'])}")
                if q_norm in r_text:
                    return True
                if all(t in r_text for t in tokens):
                    return True
                if any(t in ("ui", "ux", "uiux", "design", "designer", "graphic", "figma") for t in tokens) and ("ui" in r_text or "ux" in r_text or "design" in r_text):
                    return True
                if any(t in ("legal", "law", "lawyer", "counsel", "compliance", "contracts") for t in tokens) and ("legal" in r_text or "compliance" in r_text or "counsel" in r_text or "contracts" in r_text):
                    return True
                if any(t in ("it", "sysadmin", "devops", "cloud", "infra", "infrastructure", "security") for t in tokens) and ("it" in r_text.split() or "cloud" in r_text or "systems" in r_text or "security" in r_text):
                    return True
                if any(t in ("pm", "product", "ops", "operations", "tpm", "program") for t in tokens) and ("product" in r_text or "operations" in r_text):
                    return True
                return False
            filtered = [r for r in filtered if _role_matches(r)]

    total = len(filtered)
    limit = max(5, min(limit, 5000))
    total_pages = max(1, math.ceil(total / limit))
    page = max(1, min(page, total_pages))

    start = (page - 1) * limit
    end = start + limit
    page_items = filtered[start:end]

    return {
        "kind": "roles_feed",
        "total_filtered": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "start_index": start + 1 if total > 0 else 0,
        "end_index": min(end, total),
        "query": query,
        "discipline_filter": discipline,
        "work_mode_filter": work_mode,
        "level_filter": level,
        "items": page_items
    }
