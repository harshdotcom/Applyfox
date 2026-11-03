#!/usr/bin/env python3
"""
cv_service.py - CLI & Web Service for tailoring LaTeX CVs per Job Description (JD),
tracking applications in a persistent sheet, and archiving exact versions for future reference.

Usage:
    # 1. Launch interactive Web Form & Application Tracker UI
    python cv_service.py serve --port 8080

    # 2. Tailor CV directly via CLI
    python cv_service.py tailor --company "OpenAI" --title "AI Agent Engineer" --jd "path/to/jd.txt" --save

    # 3. Interactive CLI Wizard
    python cv_service.py interactive

    # 4. List all tracked applications ("The Sheet")
    python cv_service.py list

    # 5. Retrieve an exact previously sent CV & metadata
    python cv_service.py get APP-OPENAI-20261103-0001

    # 6. Update application status
    python cv_service.py status APP-OPENAI-20261103-0001 Interviewing
"""

import argparse
import os
import sys
from pathlib import Path

from services.cv_tailor.html_preview import render_resume_to_html
from services.cv_tailor.tailor_engine import tailor_cv
from services.cv_tailor.tracker import (
    get_application,
    list_applications,
    record_application,
    update_application_status,
)
from services.cv_tailor.web_app import run_server


BASE_TEX_PATH = Path("data/main.tex")


def cmd_tailor(args):
    """Tailor CV via command-line arguments."""
    company = args.company
    jd_input = args.jd

    if not company:
        print("Error: --company is required.", file=sys.stderr)
        sys.exit(1)

    jd_text = ""
    # Check if jd_input is a file path
    if Path(jd_input).is_file():
        jd_text = Path(jd_input).read_text(encoding="utf-8")
    else:
        jd_text = jd_input

    if not jd_text.strip():
        print("Error: Empty Job Description provided.", file=sys.stderr)
        sys.exit(1)

    print(f"\n🦊 Analyzing JD & tailoring LaTeX CV for {company}...")
    res = tailor_cv(
        base_tex_path=BASE_TEX_PATH,
        jd_text=jd_text,
        company_name=company,
        job_title=args.title or None,
        job_url=args.url or None,
        referral_name=args.referral_name or None,
        referral_contact=args.referral_contact or None
    )

    print(f"\n=======================================================")
    print(f" 🎯 Tailoring Summary for {company}")
    print(f" Role Title : {res.analysis.target_title}")
    print(f" Archetype  : {res.analysis.archetype}")
    print(f" Match Score: {res.analysis.match_score}%")
    print(f" Key Skills : {', '.join(res.analysis.top_priorities)}")
    if args.referral_name:
        print(f" Referral   : {args.referral_name} ({args.referral_contact or 'N/A'})")
    print(f"=======================================================\n")

    print("--- PROFILE MODIFICATION DIFF ---")
    print(res.profile_diff if res.profile_diff.strip() else "No changes to Profile.")
    print("\n--- SKILLS MODIFICATION DIFF ---")
    print(res.skills_diff if res.skills_diff.strip() else "No changes to Skills.")
    print("\n--- PROJECTS MODIFICATION DIFF ---")
    print(res.projects_diff if res.projects_diff.strip() else "No changes to Projects.")

    # Save output file if requested
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(res.tailored_tex, encoding="utf-8")
        print(f"\nSaved tailored LaTeX CV to: {out_path}")

    # Track application in the sheet and archive
    if args.save:
        preview_html = render_resume_to_html(res.tailored_tex, title_badge=company)
        app = record_application(
            company=company,
            job_title=res.analysis.target_title,
            tailored_tex=res.tailored_tex,
            metadata=res.metadata,
            job_url=args.url or "",
            has_referral=bool(args.referral_name),
            referral_name=args.referral_name or "",
            referral_contact=args.referral_contact or "",
            notes=args.notes or "",
            preview_html=preview_html
        )
        print(f"\n✅ Application recorded in Sheet (data/job_applications_tracker.csv)!")
        print(f"   Application ID : {app['application_id']}")
        print(f"   Archived Folder: {app['archive_dir']}")
        print(f"   To re-generate or view anytime: python cv_service.py get {app['application_id']}")


def cmd_interactive(args):
    """Interactive wizard in terminal."""
    print("\n🦊 Applyfox Interactive CV Tailor & Tracker")
    print("------------------------------------------")

    company = input("1. Company Name: ").strip()
    if not company:
        print("Company name is required.")
        return

    title = input("2. Job Title / Role (press Enter to auto-extract from JD): ").strip()
    url = input("3. Job URL (optional): ").strip()

    has_ref_str = input("4. Do you have a Referral? (y/N): ").strip().lower()
    has_ref = has_ref_str.startswith("y")
    ref_name = ""
    ref_contact = ""
    if has_ref:
        ref_name = input("   Referrer Name: ").strip()
        ref_contact = input("   Referrer Contact / LinkedIn: ").strip()

    notes = input("5. Application Notes (optional): ").strip()

    print("\n6. Paste Job Description (JD). When finished, type 'EOF' on a new line and press Enter:")
    jd_lines = []
    while True:
        try:
            line = input()
            if line.strip() == "EOF":
                break
            jd_lines.append(line)
        except EOFError:
            break

    jd_text = "\n".join(jd_lines).strip()
    if not jd_text:
        print("Job Description is required.")
        return

    args.company = company
    args.title = title or None
    args.url = url or None
    args.jd = jd_text
    args.referral_name = ref_name or None
    args.referral_contact = ref_contact or None
    args.notes = notes
    args.save = True
    args.out = None

    cmd_tailor(args)


def cmd_list(args):
    """Display tracked applications table."""
    apps = list_applications()
    if not apps:
        print("\nNo job applications tracked yet.")
        print("Track one using: python cv_service.py tailor --company ... --save")
        print("Or launch UI:    python cv_service.py serve\n")
        return

    print(f"\n{'='*95}")
    print(f" 🦊 Tracked Job Applications Sheet ({len(apps)} total) - data/job_applications_tracker.csv")
    print(f"{'='*95}")
    print(f"{'ID':<25} {'DATE':<17} {'COMPANY':<18} {'ROLE':<20} {'STATUS':<12} {'REFERRAL':<10}")
    print(f"{'-'*95}")

    for a in apps:
        app_id = a.get("application_id", "")[:24]
        date = a.get("applied_date", "")[:16]
        comp = a.get("company", "")[:17]
        role = a.get("job_title", "")[:19]
        status = a.get("status", "")[:11]
        ref = a.get("referral_name", "None")[:9] if a.get("has_referral") else "None"
        print(f"{app_id:<25} {date:<17} {comp:<18} {role:<20} {status:<12} {ref:<10}")

    print(f"{'='*95}")
    print(f"To inspect any application's exact CV: python cv_service.py get <ID>\n")


def cmd_get(args):
    """Retrieve full details and exact tailored CV of a tracked application."""
    app_id = args.id
    app = get_application(app_id)
    if not app:
        print(f"Error: Application '{app_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n=======================================================")
    print(f" 🦊 Application Details: {app_id}")
    print(f"=======================================================")
    print(f" Company     : {app.get('company')}")
    print(f" Job Title   : {app.get('job_title')}")
    print(f" Applied Date: {app.get('applied_date')}")
    print(f" Status      : {app.get('status')}")
    print(f" Job URL     : {app.get('job_url') or 'N/A'}")
    print(f" Referral    : {'Yes (' + app.get('referral_name','') + ' - ' + app.get('referral_contact','') + ')' if app.get('has_referral') else 'No'}")
    print(f" Match Score : {app.get('match_score')}%")
    print(f" Key Skills  : {', '.join(app.get('key_skills_matched', []))}")
    print(f" Archive Dir : {app.get('archive_dir')}")
    print(f" TeX File    : {app.get('tex_path')}")
    if app.get("notes"):
        print(f" Notes       : {app.get('notes')}")
    print(f"=======================================================\n")

    if args.tex:
        print("--- TAILORED LATEX CV SOURCE ---")
        print(app.get("tailored_tex", "TeX content not loaded."))


def cmd_status(args):
    """Update status of a tracked application."""
    app_id = args.id
    new_status = args.status
    notes = args.notes

    updated = update_application_status(app_id, new_status, notes=notes)
    if updated:
        print(f"✅ Updated status for {app_id} to '{new_status}'.")
    else:
        print(f"Error: Application '{app_id}' not found.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # serve
    p_serve = subparsers.add_parser("serve", help="Launch interactive local Web Application")
    p_serve.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")

    # tailor
    p_tailor = subparsers.add_parser("tailor", help="Tailor CV per Job Description")
    p_tailor.add_argument("--company", required=True, help="Target company name")
    p_tailor.add_argument("--title", help="Job Title (optional)")
    p_tailor.add_argument("--jd", required=True, help="Job description text or path to JD file")
    p_tailor.add_argument("--url", help="Job board application URL")
    p_tailor.add_argument("--referral-name", help="Referrer name")
    p_tailor.add_argument("--referral-contact", help="Referrer contact info (email/LinkedIn)")
    p_tailor.add_argument("--notes", help="Application notes")
    p_tailor.add_argument("--out", help="Save tailored .tex to this output path")
    p_tailor.add_argument("--save", action="store_true", help="Record application in tracking sheet and archive CV")

    # interactive
    subparsers.add_parser("interactive", help="Interactive terminal wizard")

    # list
    subparsers.add_parser("list", help="List all tracked applications in the sheet")

    # get
    p_get = subparsers.add_parser("get", help="Retrieve archived application and tailored CV")
    p_get.add_argument("id", help="Application ID (e.g. APP-OPENAI-20261103-0001)")
    p_get.add_argument("--tex", action="store_true", help="Print full LaTeX source")

    # status
    p_status = subparsers.add_parser("status", help="Update application status in tracking sheet")
    p_status.add_argument("id", help="Application ID")
    p_status.add_argument("status", help="New status (e.g. Applied, Interviewing, Offer, Rejected)")
    p_status.add_argument("--notes", help="Additional notes")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(port=args.port)
    elif args.command == "tailor":
        cmd_tailor(args)
    elif args.command == "interactive":
        cmd_interactive(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

