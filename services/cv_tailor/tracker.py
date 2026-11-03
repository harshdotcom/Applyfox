#!/usr/bin/env python3
"""
tracker.py - Persistent application tracking sheet (CSV + JSON) and CV archival manager.
Ensures every application, referral, and exact tailored CV version is recorded and retrievable.
"""

import csv
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


TRACKER_CSV = Path("data/job_applications_tracker.csv")
TRACKER_JSON = Path("data/job_applications_tracker.json")
TRACKER_HTML = Path("data/job_applications_tracker.html")
APPLICATIONS_DIR = Path("data/applications")

CSV_FIELDNAMES = [
    "Application ID",
    "Applied Date",
    "Company",
    "Job Title",
    "Status",
    "Has Referral",
    "Referral Name",
    "Referral Contact",
    "Job URL",
    "Match Score",
    "Key Skills Matched",
    "Archive Path",
    "Notes"
]


def ensure_storage_ready():
    """Ensure data/ and data/applications/ directories and tracking sheet exist."""
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKER_CSV.is_file():
        with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(CSV_FIELDNAMES)
    if not TRACKER_JSON.is_file():
        TRACKER_JSON.write_text("[]\n", encoding="utf-8")


def generate_application_id(company: str) -> str:
    """Generate a readable, timestamped unique application identifier."""
    clean_company = re.sub(r"[^a-zA-Z0-9]", "", company).upper()[:8] or "JOB"
    date_str = datetime.now().strftime("%Y%m%d")
    timestamp_suffix = datetime.now().strftime("%H%M%S")
    return f"APP-{clean_company}-{date_str}-{timestamp_suffix[-4:]}"


def save_application_archive(
    app_id: str,
    company: str,
    tailored_tex: str,
    metadata: Dict[str, Any],
    preview_html: Optional[str] = None,
    diff_html: Optional[str] = None,
) -> Path:
    """Save the exact generated CV, metadata, and preview into an isolated archive directory."""
    clean_slug = re.sub(r"[^a-z0-9_\-]", "", company.lower().replace(" ", "-")) or "company"
    archive_dir = APPLICATIONS_DIR / f"{app_id}_{clean_slug}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exact LaTeX CV
    tex_path = archive_dir / "tailored_cv.tex"
    tex_path.write_text(tailored_tex, encoding="utf-8")

    # 2. Compile to authentic LaTeX PDF (Overleaf-grade via TeX engine)
    try:
        from services.cv_tailor.latex_compiler import compile_tex_to_pdf
        ok, pdf_path, msg = compile_tex_to_pdf(tex_path, archive_dir, "tailored_cv.pdf")
        if ok and pdf_path and pdf_path.is_file():
            metadata["pdf_path"] = str(pdf_path)
            metadata["has_pdf"] = True
    except Exception as e:
        print(f"Warning: LaTeX compilation failed during archiving: {e}")

    # 3. Complete Metadata
    meta_path = archive_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 4. HTML Preview
    if preview_html:
        preview_path = archive_dir / "preview.html"
        preview_path.write_text(preview_html, encoding="utf-8")

    # 5. HTML Diff
    if diff_html:
        diff_path = archive_dir / "diff.html"
        diff_path.write_text(diff_html, encoding="utf-8")

    return archive_dir


def record_application(
    company: str,
    job_title: str,
    tailored_tex: str,
    metadata: Dict[str, Any],
    job_url: str = "",
    status: str = "Applied",
    has_referral: bool = False,
    referral_name: str = "",
    referral_contact: str = "",
    notes: str = "",
    preview_html: Optional[str] = None,
    diff_html: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a newly applied job into the tracker sheet and create its CV archive."""
    ensure_storage_ready()

    app_id = generate_application_id(company)
    applied_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Save to archive
    metadata["application_id"] = app_id
    metadata["applied_date"] = applied_date
    metadata["status"] = status
    metadata["notes"] = notes

    archive_dir = save_application_archive(
        app_id=app_id,
        company=company,
        tailored_tex=tailored_tex,
        metadata=metadata,
        preview_html=preview_html,
        diff_html=diff_html
    )

    top_skills_str = ", ".join(metadata.get("top_priorities", [])[:6])
    match_score_str = f"{metadata.get('match_score', 0)}%"

    # Record in CSV Sheet
    csv_row = [
        app_id,
        applied_date,
        company,
        job_title,
        status,
        "Yes" if has_referral else "No",
        referral_name,
        referral_contact,
        job_url,
        match_score_str,
        top_skills_str,
        str(archive_dir),
        notes
    ]

    with open(TRACKER_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(csv_row)

    # Record in JSON Database
    current_records = []
    if TRACKER_JSON.is_file():
        try:
            current_records = json.loads(TRACKER_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current_records = []

    record_entry = {
        "application_id": app_id,
        "applied_date": applied_date,
        "company": company,
        "job_title": job_title,
        "status": status,
        "has_referral": has_referral,
        "referral_name": referral_name,
        "referral_contact": referral_contact,
        "job_url": job_url,
        "match_score": metadata.get("match_score", 0),
        "key_skills_matched": metadata.get("top_priorities", []),
        "archive_dir": str(archive_dir),
        "tex_path": str(archive_dir / "tailored_cv.tex"),
        "notes": notes,
        "created_at": time.time()
    }
    current_records.append(record_entry)
    TRACKER_JSON.write_text(json.dumps(current_records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    generate_tracker_html()

    return record_entry


def list_applications() -> List[Dict[str, Any]]:
    """Return all recorded applications sorted latest first."""
    ensure_storage_ready()
    if not TRACKER_JSON.is_file():
        return []
    try:
        data = json.loads(TRACKER_JSON.read_text(encoding="utf-8"))
        return sorted(data, key=lambda x: x.get("created_at", 0), reverse=True)
    except Exception:
        return []


def get_application(app_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve application record and its archived CV."""
    apps = list_applications()
    for a in apps:
        if a.get("application_id") == app_id:
            # Load metadata and tex content if available
            archive_dir = Path(a.get("archive_dir", ""))
            tex_file = archive_dir / "tailored_cv.tex"
            meta_file = archive_dir / "metadata.json"
            preview_file = archive_dir / "preview.html"

            if tex_file.is_file():
                a["tailored_tex"] = tex_file.read_text(encoding="utf-8")
            if meta_file.is_file():
                try:
                    a["metadata"] = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if preview_file.is_file():
                a["preview_html"] = preview_file.read_text(encoding="utf-8")
            pdf_file = archive_dir / "tailored_cv.pdf"
            if pdf_file.is_file():
                a["has_pdf"] = True
                a["pdf_path"] = str(pdf_file)

            return a
    return None


def update_application_status(app_id: str, new_status: str, notes: Optional[str] = None) -> bool:
    """Update status (e.g. 'Interviewing', 'Offer', 'Rejected') in both CSV and JSON."""
    ensure_storage_ready()
    updated = False

    # 1. Update JSON
    records = list_applications()
    for r in records:
        if r.get("application_id") == app_id:
            r["status"] = new_status
            if notes is not None:
                r["notes"] = notes
            updated = True
            break

    if updated:
        TRACKER_JSON.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # 2. Rewrite CSV
        with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(CSV_FIELDNAMES)
            for r in sorted(records, key=lambda x: x.get("created_at", 0)):
                w.writerow([
                    r.get("application_id", ""),
                    r.get("applied_date", ""),
                    r.get("company", ""),
                    r.get("job_title", ""),
                    r.get("status", ""),
                    "Yes" if r.get("has_referral") else "No",
                    r.get("referral_name", ""),
                    r.get("referral_contact", ""),
                    r.get("job_url", ""),
                    f"{r.get('match_score', 0)}%",
                    ", ".join(r.get("key_skills_matched", [])[:6]),
                    r.get("archive_dir", ""),
                    r.get("notes", "")
                ])
        generate_tracker_html()

    return updated


def generate_tracker_html() -> Path:
    """Generate a portable, interactive HTML sheet view that can be opened directly in any browser."""
    records = list_applications()

    total_apps = len(records)
    interviewing = sum(1 for r in records if "interview" in (r.get("status") or "").lower())
    offers = sum(1 for r in records if "offer" in (r.get("status") or "").lower())
    referrals = sum(1 for r in records if r.get("has_referral"))

    rows_html = []
    for r in records:
        app_id = r.get("application_id", "")
        date = r.get("applied_date", "-")
        comp = r.get("company", "-")
        title = r.get("job_title", "-")
        status = r.get("status", "Applied")
        score = r.get("match_score", 0)
        skills = r.get("key_skills_matched", [])
        archive_dir = r.get("archive_dir", "")
        tex_path = r.get("tex_path", "")
        notes = r.get("notes", "")
        job_url = r.get("job_url", "")

        status_class = "status-applied"
        st = status.lower()
        if "interview" in st:
            status_class = "status-interview"
        elif "offer" in st:
            status_class = "status-offer"
        elif "reject" in st:
            status_class = "status-rejected"

        ref_html = (
            f'<span class="ref-badge"><i class="fa fa-user-check"></i> {r.get("referral_name", "Referred")}'
            f'<small style="display:block; opacity:0.8;">{r.get("referral_contact", "")}</small></span>'
            if r.get("has_referral")
            else '<span style="color:#64748b;">None</span>'
        )

        skills_pills = " ".join([f'<span class="skill-pill">{s}</span>' for s in skills[:5]])

        # Absolute paths for local file links
        abs_archive = Path(archive_dir).resolve()
        abs_tex = Path(tex_path).resolve()
        abs_preview = (abs_archive / "preview.html")
        preview_link = f'file://{abs_preview}' if abs_preview.is_file() else "#"
        tex_link = f'file://{abs_tex}' if abs_tex.is_file() else "#"

        comp_link = f'<a href="{job_url}" target="_blank" style="color:#38bdf8; text-decoration:none;">{comp} <i class="fa fa-external-link-alt" style="font-size:0.75rem;"></i></a>' if job_url else f'<strong>{comp}</strong>'

        rows_html.append(f"""
        <tr data-status="{status.lower()}" data-search="{comp.lower()} {title.lower()} {r.get('referral_name', '').lower()}">
            <td style="white-space:nowrap; font-size:0.85rem; color:#94a3b8;">{date}</td>
            <td>{comp_link}</td>
            <td><strong>{title}</strong></td>
            <td><span class="status-pill {status_class}">{status}</span></td>
            <td>{ref_html}</td>
            <td><span class="score-pill">{score}%</span></td>
            <td>{skills_pills}</td>
            <td style="white-space:nowrap;">
                <a href="{preview_link}" target="_blank" class="action-btn" title="View CV in Browser"><i class="fa fa-eye"></i> View CV</a>
                <a href="{tex_link}" download class="action-btn" title="Open LaTeX Source"><i class="fa fa-file-code"></i> .tex</a>
            </td>
        </tr>
        """)

    tbody_content = "\n".join(rows_html) if rows_html else '<tr><td colspan="8" style="text-align:center; padding:50px; color:#64748b;">No applications logged yet.</td></tr>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🦊 Applyfox | Job Applications Master Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
  :root {{
    --bg: #0b1120;
    --card-bg: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #f97316;
    --success: #10b981;
    --info: #38bdf8;
  }}
  * {{ box-sizing: border-box; margin:0; padding:0; }}
  body {{
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    line-height: 1.5;
  }}
  .container {{
    max-width: 1400px;
    margin: 0 auto;
  }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .brand h1 {{
    font-size: 1.4rem;
    font-weight: 700;
  }}
  .brand-badge {{
    background: var(--primary);
    color: #fff;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .header-actions {{
    display: flex;
    gap: 10px;
  }}
  .btn {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #334155;
    color: #fff;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.88rem;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    border: none;
    transition: background 0.2s;
  }}
  .btn:hover {{ background: #475569; }}
  .btn-primary {{ background: var(--primary); }}
  .btn-primary:hover {{ background: #ea580c; }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }}
  .stat-title {{
    font-size: 0.8rem;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .stat-value {{
    font-size: 1.8rem;
    font-weight: 700;
    margin-top: 4px;
  }}
  .filter-bar {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 16px;
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .search-input {{
    flex: 1;
    min-width: 250px;
    background: #0f172a;
    border: 1px solid var(--border);
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.9rem;
  }}
  .filter-select {{
    background: #0f172a;
    border: 1px solid var(--border);
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.9rem;
  }}
  .table-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    text-align: left;
  }}
  th {{
    background: #0f172a;
    padding: 14px;
    font-weight: 600;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 14px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }}
  tr:hover td {{
    background: rgba(255,255,255,0.02);
  }}
  .status-pill {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
  }}
  .status-applied {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); }}
  .status-interview {{ background: rgba(249, 115, 22, 0.2); color: #fb923c; border: 1px solid rgba(249, 115, 22, 0.4); }}
  .status-offer {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
  .status-rejected {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
  .score-pill {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 700;
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
  }}
  .skill-pill {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    background: #334155;
    color: #e2e8f0;
    font-size: 0.75rem;
    margin: 2px;
  }}
  .ref-badge {{
    color: #fb923c;
    font-weight: 600;
    font-size: 0.85rem;
  }}
  .action-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #334155;
    color: #e2e8f0;
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 0.8rem;
    text-decoration: none;
    margin-right: 4px;
  }}
  .action-btn:hover {{ background: #475569; color: #fff; }}
</style>
</head>
<body>

<div class="container">
  <header>
    <div class="brand">
      <h1>🦊 Applyfox Job Applications Master Tracker</h1>
      <span class="brand-badge">Official Tracker Sheet</span>
    </div>
    <div class="header-actions">
      <a href="http://127.0.0.1:8080" target="_blank" class="btn btn-primary"><i class="fa fa-wand-magic-sparkles"></i> Open Web Studio</a>
      <a href="job_applications_tracker.csv" download class="btn"><i class="fa fa-file-csv"></i> Download CSV</a>
    </div>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-title">Total Applications</div>
      <div class="stat-value" style="color: #38bdf8;">{total_apps}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Interviewing</div>
      <div class="stat-value" style="color: #fb923c;">{interviewing}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Referrals Tracked</div>
      <div class="stat-value" style="color: var(--primary);">{referrals}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Offers Received</div>
      <div class="stat-value" style="color: #34d399;">{offers}</div>
    </div>
  </div>

  <div class="filter-bar">
    <i class="fa fa-magnifying-glass" style="color: var(--text-muted);"></i>
    <input type="text" id="searchInput" class="search-input" placeholder="Search by company, role, referrer, or skill..." oninput="filterTable()">
    <select id="statusFilter" class="filter-select" onchange="filterTable()">
      <option value="all">All Statuses</option>
      <option value="applied">Applied</option>
      <option value="interview">Interviewing</option>
      <option value="offer">Offer</option>
      <option value="reject">Rejected</option>
    </select>
  </div>

  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>Date Applied</th>
          <th>Company</th>
          <th>Job Title</th>
          <th>Status</th>
          <th>Referral</th>
          <th>Match</th>
          <th>Key Skills Targeted</th>
          <th>Archived CV</th>
        </tr>
      </thead>
      <tbody id="tableBody">
        {tbody_content}
      </tbody>
    </table>
  </div>
</div>

<script>
function filterTable() {{
  const query = document.getElementById("searchInput").value.toLowerCase();
  const status = document.getElementById("statusFilter").value.toLowerCase();
  const rows = document.querySelectorAll("#tableBody tr");

  rows.forEach(r => {{
    const text = (r.getAttribute("data-search") || "");
    const rowStatus = (r.getAttribute("data-status") || "");

    const matchQuery = text.includes(query);
    const matchStatus = status === "all" || rowStatus.includes(status);

    r.style.display = (matchQuery && matchStatus) ? "" : "none";
  }});
}}
</script>

</body>
</html>
"""
    TRACKER_HTML.write_text(html_content, encoding="utf-8")
    return TRACKER_HTML


