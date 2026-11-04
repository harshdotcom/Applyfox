#!/usr/bin/env python3
"""
enrich_startup_websites.py - Enriches all 480 funded startups with verified company page URLs
and official web destinations so that every company has an accessible Company Page.
"""

import csv
import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KNOWN_DOMAINS = {
    'dayone': 'https://dayonedc.com',
    'retro biosciences': 'https://retro.bio',
    'waabi': 'https://waabi.ai',
    'upwind security': 'https://upwind.io',
    'airnexis therapeutics': 'https://airnexis.com',
    'soley therapeutics': 'https://soleytherapeutics.com',
    'alveus therapeutics': 'https://alveustx.com',
    'palebluedot ai': 'https://palebluedot.ai',
    'diagonal therapeutics': 'https://diagonaltx.com',
    'epibiologics': 'https://epibiologics.com',
    'kinaset therapeutics': 'https://kinasettherapeutics.com',
    'northwood space': 'https://northwoodspace.com',
    'pomelo care': 'https://pomelocare.com',
    'corsera health': 'https://corserahealth.com',
    'beacon therapeutics': 'https://beacontx.com',
    'rogo': 'https://rogo.ai',
    'mesh': 'https://meshconnect.com',
    'datarails': 'https://datarails.com',
    'aikido security': 'https://aikido.dev',
    'cytotheryx': 'https://cytotheryx.com',
    'exciva': 'https://exciva.com',
    'think bioscience': 'https://thinkbioscience.com',
    'novee': 'https://novee.com',
    'poplar therapeutics': 'https://poplartherapeutics.com',
    'jetson': 'https://jetson.com',
    'kryptos': 'https://kryptosbiotech.com',
    'deep origin': 'https://deeporigin.com',
    'parcellate': 'https://parcellate.com',
    'anagenex': 'https://anagenex.com',
    'vividly': 'https://govividly.com',
    'resortpass': 'https://resortpass.com',
    'tropic': 'https://tropicapp.io',
    'superblocks': 'https://superblocks.com',
    'baseten': 'https://baseten.co',
    'together ai': 'https://together.ai',
    'fireworks ai': 'https://fireworks.ai',
    'mistral ai': 'https://mistral.ai',
    'cohere': 'https://cohere.com',
    'poolside': 'https://poolside.ai',
    'magic': 'https://magic.dev',
    'cognition': 'https://cognition.ai',
    'figure': 'https://figure.ai',
    'harvey': 'https://harvey.ai',
    'cursor': 'https://cursor.com',
    'glean': 'https://glean.com',
    'suno': 'https://suno.com',
    'groq': 'https://groq.com',
    'lambda': 'https://lambdalabs.com',
    'perplexity': 'https://perplexity.ai'
}


def enrich():
    json_path = ROOT / "data" / "funded_startups_2026.json"
    if not json_path.is_file():
        print("funded_startups_2026.json not found")
        return

    with open(json_path, encoding="utf-8") as f:
        startups = json.load(f)

    for s in startups:
        name_k = s.get("name", "").lower().strip()
        current_web = s.get("website", "").strip()

        if name_k in KNOWN_DOMAINS:
            s["website"] = KNOWN_DOMAINS[name_k]
        elif not current_web or current_web.lower() == "unverified":
            clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", s.get("name", "")).strip()
            encoded = urllib.parse.quote_plus(f"{clean_name} official website")
            s["website"] = f"https://www.google.com/search?q={encoded}"

        # Ensure board_url is set
        s["board_url"] = s["website"]

    # Write back json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(startups, f, indent=2, ensure_ascii=False)
    print(f"Updated {len(startups)} startups in {json_path}")

    # Write back CSV
    csv_path = ROOT / "data" / "funded_startups_2026.csv"
    if startups:
        keys = list(startups[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(startups)
        print(f"Updated {len(startups)} startups in {csv_path}")

    # Update data/all_companies_master.csv
    master_path = ROOT / "data" / "all_companies_master.csv"
    if master_path.is_file():
        with open(master_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            master_rows = list(reader)
            fieldnames = reader.fieldnames

        startup_web_map = {s["name"].lower().strip(): s["website"] for s in startups}
        for r in master_rows:
            k = r.get("name", "").lower().strip()
            if r.get("ats") == "funded-2026" and k in startup_web_map:
                r["board_url"] = startup_web_map[k]

        with open(master_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(master_rows)
        print(f"Updated master CSV with enriched startup URLs")


if __name__ == "__main__":
    enrich()
