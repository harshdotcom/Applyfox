#!/usr/bin/env python3
"""
build_static_page.py - Builds self-contained index.html and docs/index.html
for instant, zero-dependency hosting on GitHub Pages (e.g. https://harshdotcom.github.io/Applyfox/).
"""

import json
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from services.cv_tailor.directory import get_sheets_summary, get_sheet_page
from services.cv_tailor.html_preview import render_resume_to_html
from services.cv_tailor.web_app import HTML_PAGE


def main():
    root = root_dir
    base_tex_path = root / "data" / "main.tex"
    base_tex = base_tex_path.read_text(encoding="utf-8") if base_tex_path.is_file() else ""
    preview_html = render_resume_to_html(base_tex, title_badge="Base Master CV").replace("</script>", "<\\/script>")

    # Ingest 500 verified directory companies across Ashby, Greenhouse, Lever, Workday with full roles
    page_data = get_sheet_page("master", 1, 500)
    items = page_data.get("items", [])
    summaries = get_sheets_summary()

    funded_json = root / "data" / "funded_startups_2026.json"
    funded_startups = json.loads(funded_json.read_text(encoding="utf-8")) if funded_json.is_file() else []

    failures_json = root / "data" / "startup_failures_2026.json"
    startup_failures = json.loads(failures_json.read_text(encoding="utf-8")) if failures_json.is_file() else []

    static_data_js = f"""
const IS_GITHUB_PAGES = (window.location.hostname.endsWith('.github.io') || window.location.protocol === 'file:');
const EMBEDDED_BASE_TEX = {json.dumps(base_tex)};
const EMBEDDED_PREVIEW_HTML = {json.dumps(preview_html)};
const EMBEDDED_SUMMARIES = {json.dumps(summaries)};
const EMBEDDED_ITEMS = {json.dumps(items)};
const EMBEDDED_FUNDED_STARTUPS = {json.dumps(funded_startups)};
const EMBEDDED_FAILURES = {json.dumps(startup_failures)};
"""

    static_html = HTML_PAGE.replace("/* GITHUB_PAGES_EMBEDDED_DATA */", static_data_js.strip())

    # Write root index.html and docs/index.html
    (root / "index.html").write_text(static_html, encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "index.html").write_text(static_html, encoding="utf-8")
    
    print(f"Successfully generated static GitHub Pages files:")
    print(f"  - {root / 'index.html'} ({len(static_html):,} bytes)")
    print(f"  - {root / 'docs' / 'index.html'} ({len(static_html):,} bytes)")


if __name__ == "__main__":
    main()
