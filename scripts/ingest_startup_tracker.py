#!/usr/bin/env python3
"""
ingest_startup_tracker.py - Ingests 2026 Startup Funding & Failures tracker Excel sheet
into structured CSV/JSON data files and updates the master directory.
"""

import csv
import json
import re
import shutil
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
XLSX_SRC = ROOT_DIR / "Startup_Funding_Tracker_2026_Final (1).xlsx"
XLSX_DEST = ROOT_DIR / "data" / "Startup_Funding_Tracker_2026_Final.xlsx"

MONTH_NAMES = [
    "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026",
    "Jul 2026", "Aug 2026", "Sep 2026", "Oct 2026", "Nov 2026", "Month not disclosed"
]


def clean_slug(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def main():
    if not XLSX_SRC.is_file():
        print(f"Error: {XLSX_SRC} not found!")
        return

    # Copy raw workbook to data/
    shutil.copy2(XLSX_SRC, XLSX_DEST)
    print(f"Copied workbook to {XLSX_DEST}")

    z = zipfile.ZipFile(XLSX_SRC)

    # 1. Load shared strings
    shared_strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss_tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in ss_tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
            text = "".join([t.text for t in si.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t") if t.text])
            shared_strings.append(text)

    # 2. Map sheet IDs to XML paths
    rels_xml = z.read("xl/_rels/workbook.xml.rels")
    rels_tree = ET.fromstring(rels_xml)
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_tree.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
    }

    wb_tree = ET.fromstring(z.read("xl/workbook.xml"))
    sheet_rel_map = {
        sheet.attrib["name"]: rel_map[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
        for sheet in wb_tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
    }

    def parse_sheet_rows(name):
        if name not in sheet_rel_map:
            return []
        target = sheet_rel_map[name]
        path = "xl/" + target if not target.startswith("/") else target[1:]
        st = ET.fromstring(z.read(path))
        rows = []
        for r in st.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            row_dict = {}
            for c in r.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                ref = c.attrib.get("r", "")
                col_letter = "".join([ch for ch in ref if ch.isalpha()])
                cell_type = c.attrib.get("t")
                v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                val = v.text if v is not None else ""
                if cell_type == "s" and val.isdigit():
                    val = shared_strings[int(val)]
                row_dict[col_letter] = val
            if row_dict:
                rows.append(row_dict)
        return rows

    # Map month sheets
    company_to_month = {}
    for m in MONTH_NAMES:
        m_rows = parse_sheet_rows(m)
        for r in m_rows:
            comp = r.get("B", "").strip()
            if comp and comp != "Company" and not comp.startswith("Global"):
                company_to_month[comp.lower()] = m

    print(f"Mapped {len(company_to_month)} companies to months.")

    # 3. Extract All Funded Companies
    all_comp_rows = parse_sheet_rows("All Companies")
    funded_startups = []
    f_idx = 0
    for r in all_comp_rows:
        comp = r.get("B", "").strip()
        if not comp or comp == "Company" or comp.startswith("Global"):
            continue
        f_idx += 1
        month = company_to_month.get(comp.lower(), r.get("K", "").strip() or "2026")
        if not month or month == "2026":
            ad = r.get("K", "").strip()
            for m in MONTH_NAMES:
                if m[:3].lower() in ad.lower():
                    month = m
                    break

        website = r.get("C", "").strip()
        if website.lower() == "unverified" or not website:
            website = ""
        elif not website.startswith("http"):
            website = "https://" + website

        round_val = r.get("H", "").strip()
        amount_val = r.get("I", "").strip()
        usd_m_val = r.get("J", "").strip()

        safe_query = urllib.parse.quote(comp)
        safe_slug = clean_slug(comp)

        funded_startups.append({
            "id": f_idx,
            "name": comp,
            "slug": safe_slug,
            "website": website,
            "country": r.get("D", "").strip(),
            "region": r.get("E", "").strip(),
            "sector": r.get("F", "").strip(),
            "what_they_build": r.get("G", "").strip(),
            "round": round_val,
            "amount": amount_val,
            "amount_usd_m": usd_m_val,
            "announced_date": r.get("K", "").strip(),
            "month": month,
            "lead_investors": r.get("L", "").strip(),
            "valuation": r.get("M", "").strip(),
            "total_funding": r.get("N", "").strip(),
            "status": r.get("O", "").strip() or "Active",
            "failed_reason": r.get("P", "").strip(),
            "outlook": r.get("Q", "").strip(),
            "outlook_reasoning": r.get("R", "").strip(),
            "source": r.get("S", "").strip(),
            "glassdoor_url": f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}",
            "levels_url": f"https://www.levels.fyi/companies/{safe_slug}/salaries",
            "google_jobs_url": f"https://www.google.com/search?q={safe_query}+jobs+careers",
        })

    print(f"Extracted {len(funded_startups)} funded startups.")

    # 4. Extract Failures & Distress
    fail_rows = parse_sheet_rows("Failures & Distress 2026")
    failures = []
    fail_idx = 0
    for r in fail_rows:
        comp = r.get("B", "").strip()
        if not comp or comp == "Company" or comp.startswith("Global"):
            continue
        fail_idx += 1
        safe_query = urllib.parse.quote(comp)
        safe_slug = clean_slug(comp)
        failures.append({
            "id": fail_idx,
            "name": comp,
            "slug": safe_slug,
            "country": r.get("C", "").strip(),
            "sector": r.get("D", "").strip(),
            "funding_before_failure": r.get("E", "").strip(),
            "when_date": r.get("F", "").strip(),
            "what_happened": r.get("G", "").strip(),
            "precise_reason": r.get("H", "").strip(),
            "lesson": r.get("I", "").strip(),
            "source": r.get("J", "").strip(),
            "glassdoor_url": f"https://www.glassdoor.com/Search/results.htm?keyword={safe_query}",
            "levels_url": f"https://www.levels.fyi/companies/{safe_slug}/salaries",
            "google_jobs_url": f"https://www.google.com/search?q={safe_query}+startup+news",
        })

    print(f"Extracted {len(failures)} failures.")

    # 5. Save JSON files
    json_path_funded = ROOT_DIR / "data" / "funded_startups_2026.json"
    json_path_funded.write_text(json.dumps(funded_startups, indent=2), encoding="utf-8")
    print(f"Wrote {json_path_funded} ({len(funded_startups)} records)")

    json_path_failures = ROOT_DIR / "data" / "startup_failures_2026.json"
    json_path_failures.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(f"Wrote {json_path_failures} ({len(failures)} records)")

    # 6. Save CSV files
    csv_path_funded = ROOT_DIR / "data" / "funded_startups_2026.csv"
    if funded_startups:
        with open(csv_path_funded, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(funded_startups[0].keys()))
            writer.writeheader()
            writer.writerows(funded_startups)
        print(f"Wrote {csv_path_funded}")

    csv_path_failures = ROOT_DIR / "data" / "startup_failures_2026.csv"
    if failures:
        with open(csv_path_failures, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(failures[0].keys()))
            writer.writeheader()
            writer.writerows(failures)
        print(f"Wrote {csv_path_failures}")

    # 7. Update data/all_companies_master.csv to include all new startups
    master_csv_path = ROOT_DIR / "data" / "all_companies_master.csv"
    existing_companies = []
    seen_names = set()
    if master_csv_path.is_file():
        with open(master_csv_path, encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                name = row.get("name", "").strip()
                if name:
                    seen_names.add(name.lower())
                    existing_companies.append(row)

    print(f"Existing master count: {len(existing_companies)}")

    added_count = 0
    for s in funded_startups:
        if s["name"].lower() not in seen_names:
            seen_names.add(s["name"].lower())
            board = s["website"] if s["website"] else s["google_jobs_url"]
            open_jobs_label = f"{s['round']} ({s['amount']})" if s["round"] and s["amount"] else s["round"] or "Funded 2026"
            existing_companies.append({
                "name": s["name"],
                "ats": "funded-2026",
                "slug_or_id": s["slug"],
                "open_jobs": open_jobs_label,
                "board_url": board,
            })
            added_count += 1

    for f_item in failures:
        if f_item["name"].lower() not in seen_names:
            seen_names.add(f_item["name"].lower())
            existing_companies.append({
                "name": f_item["name"],
                "ats": "distressed",
                "slug_or_id": f_item["slug"],
                "open_jobs": f_item["funding_before_failure"][:30] if f_item["funding_before_failure"] else "Distressed 2026",
                "board_url": f_item["google_jobs_url"],
            })
            added_count += 1

    with open(master_csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["name", "ats", "slug_or_id", "open_jobs", "board_url"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_companies)

    print(f"Added {added_count} new startups to master CSV. New total: {len(existing_companies)} companies.")


if __name__ == "__main__":
    main()

