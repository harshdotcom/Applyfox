#!/usr/bin/env python3
"""
run_all.py - Unified orchestrator for Applyfox ATS discovery & validation.

Runs Greenhouse, Lever, Workday, and Ashby pipelines, validates job boards against
live APIs, extracts open job counts, and exports unified master datasets.

Usage:
    python run_all.py                         # Run all 4 ATS pipelines
    python run_all.py --ats greenhouse ashby  # Run specific ATS platforms
    python run_all.py --jobs --workers 8      # Fast parallel validation with job counts
"""
import argparse, csv, subprocess, sys, time
from pathlib import Path


ATS_SCRIPTS = {
    "greenhouse": {
        "script": "gh_discover.py",
        "default_args": ["--seed", "seeds/greenhouse_seed.yaml", "--names", "seeds/names.txt"],
        "csv": "data/greenhouse_master.csv",
        "ats_name": "greenhouse"
    },
    "lever": {
        "script": "lever_discover.py",
        "default_args": ["--directory", "seeds/lever_directory.json", "--seed", "seeds/lever_seed.yaml"],
        "csv": "data/lever_master.csv",
        "ats_name": "lever"
    },
    "workday": {
        "script": "workday_discover.py",
        "default_args": ["--directory", "seeds/workday_directory.json", "--seed", "seeds/workday_seed.yaml"],
        "csv": "data/workday_master.csv",
        "ats_name": "workday"
    },
    "ashby": {
        "script": "ashby_discover.py",
        "default_args": ["--directory", "seeds/ashby_directory.json", "--seed", "seeds/ashby_seed.yaml"],
        "csv": "data/ashby_master.csv",
        "ats_name": "ashby"
    }
}


def build_unified_master():
    """Merge all exported ATS CSVs into data/all_companies_master.csv."""
    all_rows = []

    # 1. Greenhouse
    gh_csv = Path("data/greenhouse_master.csv")
    if gh_csv.is_file():
        with open(gh_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                all_rows.append({
                    "name": r.get("name", "").strip(),
                    "ats": "greenhouse",
                    "slug_or_id": r.get("slug", "").strip(),
                    "open_jobs": r.get("open_jobs", "").strip(),
                    "board_url": r.get("board_url", "").strip()
                })

    # 2. Lever
    lever_csv = Path("data/lever_master.csv")
    if lever_csv.is_file():
        with open(lever_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                all_rows.append({
                    "name": r.get("name", "").strip(),
                    "ats": "lever",
                    "slug_or_id": r.get("slug", "").strip(),
                    "open_jobs": r.get("open_jobs", "").strip(),
                    "board_url": r.get("board_url", "").strip()
                })

    # 3. Workday
    wd_csv = Path("data/workday_master.csv")
    if wd_csv.is_file():
        with open(wd_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                slug_or_id = f"{r.get('tenant', '')}:{r.get('wd_instance', '')}:{r.get('site', '')}".strip(":")
                all_rows.append({
                    "name": r.get("name", "").strip(),
                    "ats": "workday",
                    "slug_or_id": slug_or_id,
                    "open_jobs": r.get("open_jobs", "").strip(),
                    "board_url": r.get("board_url", "").strip()
                })

    # 4. Ashby
    ashby_csv = Path("data/ashby_master.csv")
    if ashby_csv.is_file():
        with open(ashby_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                all_rows.append({
                    "name": r.get("name", "").strip(),
                    "ats": "ashby",
                    "slug_or_id": r.get("slug", "").strip(),
                    "open_jobs": r.get("open_jobs", "").strip(),
                    "board_url": r.get("board_url", "").strip()
                })

    # Sort alphabetically by company name
    all_rows.sort(key=lambda x: x["name"].lower())

    out_file = Path("data/all_companies_master.csv")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "ats", "slug_or_id", "open_jobs", "board_url"])
        w.writeheader()
        w.writerows(all_rows)

    print(f"\n[Applyfox] Successfully generated unified master: {out_file} ({len(all_rows)} total verified companies)")
    return len(all_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ats", nargs="*", default=list(ATS_SCRIPTS.keys()), choices=list(ATS_SCRIPTS.keys()),
                    help="ATS platforms to run (default: all)")
    ap.add_argument("--jobs", action="store_true", default=True,
                    help="Fetch live open job counts (default: True)")
    ap.add_argument("--no-jobs", dest="jobs", action="store_false",
                    help="Skip open job counts for faster board-only validation")
    ap.add_argument("--workers", type=int, default=8, help="Parallel worker threads")
    ap.add_argument("--rate", type=float, default=8.0, help="Max requests per second")
    args = ap.parse_args()

    Path("data").mkdir(exist_ok=True)
    Path("seeds").mkdir(exist_ok=True)

    t0 = time.time()
    print("=" * 70)
    print(" 🦊 Applyfox - Master ATS Discovery & Validation Runner")
    print(f" Targets: {', '.join(args.ats).upper()} | Workers: {args.workers} | Rate: {args.rate}/s")
    print("=" * 70)

    for ats in args.ats:
        info = ATS_SCRIPTS[ats]
        script = info["script"]
        cmd = [sys.executable, script, "--workers", str(args.workers), "--rate", str(args.rate)]
        if args.jobs:
            cmd.append("--jobs")
        cmd.extend(info["default_args"])

        print(f"\n>>> Running {ats.upper()} discovery ({script})...")
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"Warning: {script} exited with code {res.returncode}", file=sys.stderr)

    total = build_unified_master()
    elapsed = time.time() - t0
    print(f"\nFinished in {elapsed:.1f}s. Total verified companies across all platforms: {total}")


if __name__ == "__main__":
    main()

