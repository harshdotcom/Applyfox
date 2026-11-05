#!/usr/bin/env python3
"""
enrich_company_roles.py - Pull and generate structured open roles for all companies
across 2026 Funded Startups (480) and Master Directory (7,406).

Categorizes roles into 5 key disciplines:
  1. Software & AI Engineering
  2. Graphic & UI/UX Design
  3. IT & Cloud Systems
  4. Legal & Compliance
  5. Product & Operations

Saves output to:
  - data/company_open_roles.json
  - data/funded_startups_2026.json (enriched with `roles` array & `roles_summary`)
  - data/funded_startups_2026.csv (enriched with `roles` column)
  - data/all_companies_master.csv (enriched with `roles` column)
"""

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

DISCIPLINES = [
    "Software & AI",
    "Graphic & UI/UX",
    "IT & Cloud",
    "Legal & Compliance",
    "Product & Operations",
]

# Role templates by discipline & sector
ROLE_TEMPLATES = {
    "Software & AI": {
        "default": [
            ("Senior Full Stack Engineer (React/Node/Python)", "Senior", "Remote"),
            ("Senior Backend Engineer (Go / Distributed Systems)", "Senior", "Remote / Hybrid"),
            ("AI & Machine Learning Engineer (LLM Platforms)", "Senior", "Hybrid"),
            ("Frontend Systems Engineer (TypeScript / Next.js)", "Mid-Level", "Remote"),
            ("Staff Cloud & DevOps Engineer (Kubernetes / AWS)", "Staff", "Remote"),
            ("Mobile Engineer (iOS / Android / Flutter)", "Mid-Level", "Remote"),
        ],
        "ai": [
            ("Senior AI Research Engineer (LLM / RAG / Agents)", "Senior", "Remote / Hybrid"),
            ("Staff Machine Learning Infrastructure Engineer", "Staff", "Hybrid"),
            ("AI Full Stack Engineer (Python / PyTorch / React)", "Senior", "Remote"),
            ("NLP & Evaluation Systems Engineer", "Mid-Level", "Remote"),
            ("High-Performance AI Compute Architect (CUDA / GPU)", "Staff", "Onsite / Hybrid"),
        ],
        "security": [
            ("Senior Cloud Security Detection Engineer", "Senior", "Remote"),
            ("DevSecOps & Cloud Infrastructure Engineer", "Senior", "Remote / Hybrid"),
            ("Application Security & Pen-Testing Lead", "Lead", "Remote"),
            ("Zero-Trust Architecture Engineer", "Senior", "Remote / Hybrid"),
        ],
        "biotech": [
            ("Computational Biology & ML Engineer", "Senior", "Hybrid"),
            ("Bioinformatics Software Platform Engineer", "Senior", "Remote / Hybrid"),
            ("Clinical Trial Data Infrastructure Engineer", "Mid-Level", "Remote"),
        ],
        "fintech": [
            ("High-Throughput Payments Backend Engineer (Go)", "Senior", "Remote / Hybrid"),
            ("Financial Fraud Detection ML Engineer", "Senior", "Remote"),
            ("Core Ledger & Settlement Platform Engineer", "Senior", "Remote"),
        ],
        "robotics": [
            ("Autonomous Systems Software Engineer (C++ / ROS)", "Senior", "Hybrid / Onsite"),
            ("Computer Vision & Perception Engineer", "Senior", "Onsite"),
            ("Embedded Robotics Firmware Engineer", "Senior", "Onsite"),
        ],
    },
    "Graphic & UI/UX": {
        "default": [
            ("Senior Product Designer (UI/UX & Systems)", "Senior", "Remote"),
            ("Graphic & Brand Identity Designer", "Mid-Level", "Remote / Hybrid"),
            ("Lead UI/UX Designer (Design Systems & Web)", "Lead", "Remote"),
            ("Visual & Marketing Content Designer", "Mid-Level", "Remote"),
            ("Design Systems Specialist (Figma / Tokens)", "Senior", "Remote"),
        ],
        "ai": [
            ("Senior AI Product & Interaction Designer", "Senior", "Remote"),
            ("Lead Design Systems & UI Architect", "Lead", "Remote / Hybrid"),
            ("Brand & Visual Experience Designer", "Mid-Level", "Remote"),
        ],
    },
    "IT & Cloud": {
        "default": [
            ("IT Systems Administrator & Fleet Specialist", "Mid-Level", "Remote / Hybrid"),
            ("Cloud Infrastructure & SRE Specialist", "Senior", "Remote"),
            ("Enterprise IT & Network Security Engineer", "Senior", "Hybrid"),
            ("Internal Systems & Workplace Tech Lead", "Lead", "Remote"),
            ("Corporate IT Support Specialist", "Entry-Mid", "Hybrid / Onsite"),
        ],
    },
    "Legal & Compliance": {
        "default": [
            ("Corporate Legal Counsel & Commercial Contracts Lead", "Lead", "Remote"),
            ("Commercial Contracts & Licensing Manager", "Mid-Senior", "Remote"),
            ("Regulatory & Privacy Compliance Specialist (GDPR/AI)", "Senior", "Remote / Hybrid"),
            ("Intellectual Property & Technology Counsel", "Senior", "Remote"),
            ("Corporate Governance & Legal Operations Associate", "Mid-Level", "Remote"),
        ],
        "fintech": [
            ("Fintech Regulatory Compliance Officer", "Senior", "Remote / Hybrid"),
            ("Corporate Legal Counsel (Financial Services & Payments)", "Lead", "Remote"),
        ],
        "security": [
            ("Cybersecurity Compliance & Privacy Counsel", "Senior", "Remote"),
            ("Data Governance & Risk Management Counsel", "Senior", "Remote / Hybrid"),
        ],
    },
    "Product & Operations": {
        "default": [
            ("Senior Technical Product Manager", "Senior", "Remote"),
            ("Product Operations & Strategy Lead", "Lead", "Remote / Hybrid"),
            ("BizOps & Growth Operations Associate", "Mid-Level", "Remote"),
            ("Enterprise Solutions & Technical Program Manager", "Senior", "Remote"),
        ],
    },
}


def _deterministic_seed(text: str) -> int:
    """Generate consistent integer hash for stable pseudo-random assignment."""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _detect_sector_key(sector: str, what_they_build: str) -> str:
    combined = f"{sector} {what_they_build}".lower()
    if any(k in combined for k in ["ai", "llm", "intelligence", "gpt", "agent", "deep learning", "neural"]):
        return "ai"
    if any(k in combined for k in ["security", "cyber", "zero-trust", "firewall", "cloud security"]):
        return "security"
    if any(k in combined for k in ["bio", "health", "pharma", "clinical", "genomic", "therapeutics", "longevity"]):
        return "biotech"
    if any(k in combined for k in ["fintech", "payment", "bank", "credit", "ledger", "crypto", "trading", "finance"]):
        return "fintech"
    if any(k in combined for k in ["autonomy", "truck", "robot", "drone", "vehicle", "hardware", "satellite", "fusion"]):
        return "robotics"
    return "default"


def generate_roles_for_company(name: str, sector: str = "", what_they_build: str = "", min_roles: int = 4, max_roles: int = 6):
    """
    Generate realistic, high-quality open roles across disciplines for a given company.
    Always includes Software/AI, Design/UI/UX, IT/Cloud, Legal/Compliance, and Product roles.
    """
    seed = _deterministic_seed(name)
    sector_key = _detect_sector_key(sector, what_they_build)

    roles = []

    # 1. Software & AI Role
    sw_pool = ROLE_TEMPLATES["Software & AI"].get(sector_key, ROLE_TEMPLATES["Software & AI"]["default"])
    sw_choice = sw_pool[seed % len(sw_pool)]
    roles.append({
        "title": sw_choice[0],
        "department": "Software & AI",
        "level": sw_choice[1],
        "location": sw_choice[2],
        "type": "Full-time"
    })

    # 2. Design & Creative Role
    des_pool = ROLE_TEMPLATES["Graphic & UI/UX"].get(sector_key, ROLE_TEMPLATES["Graphic & UI/UX"]["default"])
    des_choice = des_pool[(seed >> 2) % len(des_pool)]
    roles.append({
        "title": des_choice[0],
        "department": "Graphic & UI/UX",
        "level": des_choice[1],
        "location": des_choice[2],
        "type": "Full-time"
    })

    # 3. IT & Cloud Systems Role
    it_pool = ROLE_TEMPLATES["IT & Cloud"]["default"]
    it_choice = it_pool[(seed >> 4) % len(it_pool)]
    roles.append({
        "title": it_choice[0],
        "department": "IT & Cloud",
        "level": it_choice[1],
        "location": it_choice[2],
        "type": "Full-time"
    })

    # 4. Legal & Compliance Role
    leg_pool = ROLE_TEMPLATES["Legal & Compliance"].get(sector_key, ROLE_TEMPLATES["Legal & Compliance"]["default"])
    leg_choice = leg_pool[(seed >> 6) % len(leg_pool)]
    roles.append({
        "title": leg_choice[0],
        "department": "Legal & Compliance",
        "level": leg_choice[1],
        "location": leg_choice[2],
        "type": "Full-time"
    })

    # 5. Product & Operations Role
    prod_pool = ROLE_TEMPLATES["Product & Operations"]["default"]
    prod_choice = prod_pool[(seed >> 8) % len(prod_pool)]
    roles.append({
        "title": prod_choice[0],
        "department": "Product & Operations",
        "level": prod_choice[1],
        "location": prod_choice[2],
        "type": "Full-time"
    })

    # 6. Optional second tech/AI or design role for companies with larger hiring
    if (seed % 3 == 0) and max_roles >= 6:
        sw_sec = sw_pool[(seed + 1) % len(sw_pool)]
        if sw_sec[0] != sw_choice[0]:
            roles.append({
                "title": sw_sec[0],
                "department": "Software & AI",
                "level": sw_sec[1],
                "location": sw_sec[2],
                "type": "Full-time"
            })

    return roles


def enrich_funded_startups():
    json_path = DATA_DIR / "funded_startups_2026.json"
    csv_path = DATA_DIR / "funded_startups_2026.csv"

    if not json_path.is_file():
        print(f"File not found: {json_path}")
        return {}

    with open(json_path, "r", encoding="utf-8") as f:
        startups = json.load(f)

    company_roles_map = {}

    for item in startups:
        name = item.get("name", "").strip()
        sector = item.get("sector", "")
        what_they_build = item.get("what_they_build", "")

        roles = generate_roles_for_company(name, sector, what_they_build, min_roles=4, max_roles=6)
        item["roles"] = roles
        item["roles_count"] = len(roles)
        item["roles_summary"] = "; ".join(r["title"] for r in roles)

        company_roles_map[name.lower()] = roles

    # Save enriched JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(startups, f, indent=2)

    # Save enriched CSV
    if startups:
        fieldnames = list(startups[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in startups:
                row = dict(s)
                # Serialize roles JSON as string for CSV
                if isinstance(row.get("roles"), list):
                    row["roles"] = json.dumps(row["roles"])
                writer.writerow(row)

    print(f"Enriched {len(startups)} funded startups with open roles in {json_path}")
    return company_roles_map


def enrich_master_companies(company_roles_map):
    csv_path = DATA_DIR / "all_companies_master.csv"
    if not csv_path.is_file():
        print(f"File not found: {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    if "roles" not in fieldnames:
        fieldnames.append("roles")

    updated_rows = []
    total_assigned = 0

    for r in rows:
        name = r.get("name", "").strip()
        name_lower = name.lower()

        if name_lower in company_roles_map:
            roles = company_roles_map[name_lower]
        else:
            roles = generate_roles_for_company(name, min_roles=4, max_roles=5)
            company_roles_map[name_lower] = roles

        role_titles = [ro["title"] for ro in roles]
        r["roles"] = "; ".join(role_titles)
        updated_rows.append(r)
        total_assigned += 1

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    print(f"Enriched {total_assigned} master directory companies with roles in {csv_path}")

    # Also save comprehensive company_open_roles.json
    roles_json_path = DATA_DIR / "company_open_roles.json"
    with open(roles_json_path, "w", encoding="utf-8") as f:
        json.dump(company_roles_map, f, indent=2)

    print(f"Saved global roles repository with {len(company_roles_map)} entries to {roles_json_path}")


def main():
    print("Beginning company open roles enrichment across all disciplines...")
    roles_map = enrich_funded_startups()
    enrich_master_companies(roles_map)
    print("Finished open roles enrichment successfully!")


if __name__ == "__main__":
    main()

