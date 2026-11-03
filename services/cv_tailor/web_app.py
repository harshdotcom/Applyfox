#!/usr/bin/env python3
"""
web_app.py - High-performance local web application & API server for Applyfox.
Features:
  - Default Frontpage / Product Overview showcasing complete platform capabilities
  - Dedicated Workspaces for CV Studio, Paginated Multi-Portal Sheets, Tracker, and Base CV
  - Editorial warm-paper minimalist design system inspired by Pi & Pixel / modern dev tools
  - On-demand server-side paginated multi-sheet directory (Master, Ashby, Greenhouse, Lever, Workday)
  - Genuine Overleaf-grade LaTeX PDF compilation engine (standalone Tectonic core)
  - Real-time job applications tracking and full version archival
"""

import csv
import json
import mimetypes
import os
import re
import shutil
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

from services.cv_tailor.directory import get_sheet_page, get_sheets_summary
from services.cv_tailor.html_preview import render_diff_html, render_resume_to_html
from services.cv_tailor.latex_compiler import compile_tex_to_pdf
from services.cv_tailor.tailor_engine import tailor_cv
from services.cv_tailor.tracker import (
    get_application,
    list_applications,
    record_application,
    update_application_status,
)


BASE_TEX_PATH = Path("data/main.tex")
MASTER_COMPANIES_CSV = Path("data/all_companies_master.csv")
PREVIEW_CACHE_DIR = Path("/tmp/applyfox_previews")
PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHED_COMPANIES: List[str] = []


def get_cached_companies() -> List[str]:
    """Load unique company names for quick autocomplete."""
    global CACHED_COMPANIES
    if not CACHED_COMPANIES and MASTER_COMPANIES_CSV.is_file():
        try:
            with open(MASTER_COMPANIES_CSV, encoding="utf-8") as f:
                r = csv.DictReader(f)
                seen = set()
                names = []
                for row in r:
                    name = row.get("name", "").strip()
                    if name and name.lower() not in seen:
                        seen.add(name.lower())
                        names.append(name)
                CACHED_COMPANIES = sorted(names[:5000], key=lambda x: x.lower())
        except Exception:
            CACHED_COMPANIES = []
    return CACHED_COMPANIES


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Applyfox &mdash; The Career Studio for Engineers</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
  :root {
    --bg-warm: #FAF8F5;
    --card-bg: #FFFFFF;
    --border-subtle: #E7E5E4;
    --border-hover: #D6D3D1;
    --border-dark: #18181B;
    --text-primary: #1C1917;
    --text-secondary: #78716C;
    --text-muted: #A8A29E;
    --accent-emerald: #0D9488;
    --accent-emerald-dark: #0F766E;
    --accent-emerald-light: #CCFBF1;
    --accent-amber: #D97706;
    --accent-amber-light: #FEF3C7;
    --accent-ink: #18181B;
    --accent-ink-hover: #27272A;
    --card-shadow: 0 1px 3px rgba(0, 0, 0, 0.02), 0 8px 24px -4px rgba(28, 25, 23, 0.04);
    --card-shadow-hover: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 16px 32px -4px rgba(28, 25, 23, 0.07);
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-pill: 9999px;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: var(--bg-warm);
    background-image: 
      linear-gradient(to right, rgba(0, 0, 0, 0.032) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(0, 0, 0, 0.032) 1px, transparent 1px);
    background-size: 36px 36px;
    color: var(--text-primary);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* Navigation Bar */
  header {
    background: rgba(250, 248, 245, 0.94);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border-subtle);
    padding: 12px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    text-decoration: none;
    letter-spacing: -0.02em;
    cursor: pointer;
  }
  .brand-badge {
    background: var(--accent-amber-light);
    color: var(--accent-amber);
    border: 1px solid #FDE68A;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .nav-tabs {
    display: flex;
    gap: 5px;
    background: #F0EDE8;
    padding: 4px;
    border-radius: 12px;
    border: 1px solid var(--border-subtle);
  }
  .tab-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 7px 15px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .tab-btn:hover {
    color: var(--text-primary);
  }
  .tab-btn.active {
    background: #FFFFFF;
    color: var(--text-primary);
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
  }

  /* Main Container */
  main {
    max-width: 1540px;
    margin: 0 auto;
    padding: 20px 28px 48px;
  }

  /* Workspace Compact Header */
  .workspace-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0 18px;
    margin-bottom: 6px;
    border-bottom: 1px solid #EFECE6;
  }
  .workspace-breadcrumb {
    font-size: 0.95rem;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .workspace-breadcrumb a {
    color: var(--text-secondary);
    text-decoration: none;
    font-weight: 500;
  }
  .workspace-breadcrumb a:hover {
    color: var(--text-primary);
  }
  .workspace-breadcrumb strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .workspace-meta {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  /* Editorial Hero Header (Landing Page Only) */
  .hero-section {
    text-align: center;
    padding: 56px 20px 32px;
    max-width: 960px;
    margin: 0 auto;
  }
  .hero-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-pill);
    padding: 5px 16px;
    font-size: 0.74rem;
    font-weight: 600;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
    margin-bottom: 22px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }
  .hero-dot {
    width: 6px;
    height: 6px;
    background: var(--accent-emerald);
    border-radius: 50%;
    display: inline-block;
  }
  .hero-title {
    font-family: 'Newsreader', Georgia, serif;
    font-size: 3.4rem;
    font-weight: 500;
    line-height: 1.15;
    color: var(--text-primary);
    margin: 0 0 16px;
    letter-spacing: -0.03em;
  }
  .hero-accent {
    color: var(--accent-emerald);
    font-style: italic;
    font-weight: 400;
  }
  .hero-subtitle {
    font-size: 1.12rem;
    line-height: 1.6;
    color: var(--text-secondary);
    margin: 0 auto 32px;
    max-width: 720px;
  }
  .hero-actions {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 44px;
  }

  /* Live Interactive Terminal Card */
  .terminal-card {
    background: #18181B;
    border-radius: 14px;
    padding: 16px 20px;
    color: #F4F4F5;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.25);
  }
  .terminal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 1px solid #27272A;
    margin-bottom: 14px;
  }
  .traffic-lights {
    display: flex;
    gap: 7px;
  }
  .traffic-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .dot-red { background: #EF4444; }
  .dot-yellow { background: #F59E0B; }
  .dot-green { background: #10B981; }
  .terminal-tag {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    padding: 3px 9px;
    border-radius: 5px;
    letter-spacing: 0.04em;
  }
  .terminal-body {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.6;
    color: #D4D4D8;
    background: #09090B;
    padding: 16px;
    border-radius: 8px;
    overflow-x: auto;
  }
  .terminal-token-kw { color: #F472B6; }
  .terminal-token-cmd { color: #60A5FA; }
  .terminal-token-arg { color: #34D399; }
  .terminal-token-comment { color: #71717A; font-style: italic; }

  /* Feature Cards Grid */
  .section-heading {
    text-align: center;
    margin: 50px 0 24px;
  }
  .section-tag {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent-emerald);
    margin-bottom: 8px;
    display: block;
  }
  .section-title {
    font-family: 'Newsreader', serif;
    font-size: 2.2rem;
    font-weight: 500;
    color: var(--text-primary);
    margin: 0 0 10px;
    letter-spacing: -0.02em;
  }
  .section-desc {
    font-size: 0.98rem;
    color: var(--text-secondary);
    max-width: 600px;
    margin: 0 auto;
    line-height: 1.5;
  }

  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 20px;
    margin-top: 28px;
  }
  .feature-card {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 26px;
    box-shadow: var(--card-shadow);
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    cursor: pointer;
  }
  .feature-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--card-shadow-hover);
    border-color: var(--border-hover);
  }
  .feature-icon-wrapper {
    width: 44px;
    height: 44px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
    margin-bottom: 18px;
  }
  .icon-purple { background: #FAF5FF; color: #7E22CE; border: 1px solid #F3E8FF; }
  .icon-emerald { background: #ECFDF5; color: #047857; border: 1px solid #D1FAE5; }
  .icon-sky { background: #F0F9FF; color: #0369A1; border: 1px solid #E0F2FE; }
  .icon-amber { background: #FFFBEB; color: #B45309; border: 1px solid #FEF3C7; }

  .feature-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px;
    letter-spacing: -0.01em;
  }
  .feature-text {
    font-size: 0.88rem;
    line-height: 1.55;
    color: var(--text-secondary);
    margin: 0 0 16px;
  }
  .feature-link {
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--text-primary);
    display: inline-flex;
    align-items: center;
    gap: 6px;
    text-decoration: none;
  }
  .feature-link:hover {
    color: var(--accent-emerald);
  }

  /* Workflow Steps */
  .workflow-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
    margin-top: 28px;
  }
  @media (max-width: 900px) {
    .workflow-grid { grid-template-columns: 1fr; }
  }
  .step-card {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px;
    position: relative;
    box-shadow: var(--card-shadow);
  }
  .step-num {
    font-family: 'Newsreader', serif;
    font-size: 2.2rem;
    font-weight: 600;
    color: #E7E5E4;
    line-height: 1;
    margin-bottom: 12px;
  }
  .step-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px;
  }
  .step-text {
    font-size: 0.86rem;
    line-height: 1.5;
    color: var(--text-secondary);
    margin: 0;
  }

  /* Stats Counter Strip */
  .stats-strip {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px 32px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 24px;
    margin: 44px 0;
    box-shadow: var(--card-shadow);
  }
  .stat-item {
    text-align: center;
  }
  .stat-num {
    font-family: 'Newsreader', Georgia, serif;
    font-size: 2.4rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.1;
    letter-spacing: -0.02em;
  }
  .stat-label {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-secondary);
    margin-top: 4px;
  }

  /* Call To Action Box */
  .cta-banner {
    background: #18181B;
    color: #FFFFFF;
    border-radius: 16px;
    padding: 44px 32px;
    text-align: center;
    margin: 48px 0 20px;
    box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.25);
  }
  .cta-title {
    font-family: 'Newsreader', serif;
    font-size: 2.4rem;
    font-weight: 500;
    margin: 0 0 12px;
    letter-spacing: -0.02em;
  }
  .cta-sub {
    font-size: 1.02rem;
    color: #A1A1AA;
    max-width: 580px;
    margin: 0 auto 28px;
    line-height: 1.5;
  }

  /* Cards */
  .card {
    background: var(--card-bg);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px;
    box-shadow: var(--card-shadow);
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 1px solid #F2EFE9;
  }
  .card-title {
    font-size: 1.05rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  /* Tailor 2-Column Grid Layout */
  .tailor-layout {
    display: grid;
    grid-template-columns: 460px 1fr;
    gap: 24px;
    align-items: start;
  }
  @media (max-width: 1100px) {
    .tailor-layout { grid-template-columns: 1fr; }
  }

  /* Forms */
  .form-group {
    margin-bottom: 14px;
  }
  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  label {
    display: block;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 6px;
    letter-spacing: 0.01em;
  }
  input[type="text"], input[type="url"], textarea, select {
    width: 100%;
    padding: 10px 12px;
    background: #FFFFFF;
    border: 1px solid var(--border-hover);
    border-radius: 8px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.88rem;
    transition: all 0.15s ease;
  }
  input[type="text"]:focus, input[type="url"]:focus, textarea:focus, select:focus {
    outline: none;
    border-color: var(--accent-ink);
    box-shadow: 0 0 0 3px rgba(24, 24, 27, 0.08);
  }
  textarea {
    resize: vertical;
    min-height: 120px;
    line-height: 1.45;
  }

  /* Referral Box */
  .referral-box {
    background: #FAF8F5;
    border: 1px dashed #D6D3D1;
    border-radius: 10px;
    padding: 12px 14px;
    margin-top: 6px;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
    cursor: pointer;
    user-select: none;
  }

  /* Action Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 9px 18px;
    border-radius: 8px;
    font-size: 0.88rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    border: 1px solid transparent;
    text-decoration: none;
  }
  .btn-lg {
    padding: 11px 22px;
    font-size: 0.94rem;
    border-radius: 10px;
  }
  .btn-primary {
    background: var(--accent-ink);
    color: #FFFFFF;
    border-color: var(--accent-ink);
  }
  .btn-primary:hover {
    background: var(--accent-ink-hover);
    border-color: var(--accent-ink-hover);
  }
  .btn-success {
    background: #059669;
    color: #FFFFFF;
    border-color: #059669;
  }
  .btn-success:hover {
    background: #047857;
    border-color: #047857;
  }
  .btn-secondary {
    background: #FFFFFF;
    color: var(--text-primary);
    border-color: var(--border-hover);
  }
  .btn-secondary:hover {
    background: #F5F5F4;
    border-color: #A8A29E;
  }
  .btn-sm {
    padding: 5px 10px;
    font-size: 0.78rem;
    border-radius: 6px;
  }
  .btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .banner-actions {
    display: flex;
    gap: 10px;
    margin-top: 18px;
  }

  /* Results Tabs */
  .results-tabs {
    display: flex;
    gap: 6px;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 16px;
  }
  .subtab-btn {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-secondary);
    padding: 8px 14px;
    font-size: 0.84rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .subtab-btn:hover {
    color: var(--text-primary);
  }
  .subtab-btn.active {
    color: var(--text-primary);
    border-bottom-color: var(--accent-ink);
    font-weight: 600;
  }

  /* Chips */
  .meta-chips {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .chip {
    padding: 3px 10px;
    border-radius: var(--radius-pill);
    font-size: 0.76rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .chip-score { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
  .chip-archetype { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }
  .chip-skill { background: #F5F5F4; color: #44403C; border: 1px solid #E7E5E4; font-weight: 500; }

  /* Frame Previews */
  .preview-frame-container {
    background: #E5E5E5;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    overflow: hidden;
    height: 780px;
  }
  .preview-frame {
    width: 100%;
    height: 100%;
    border: none;
  }
  .tex-code {
    width: 100%;
    height: 650px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.84rem;
    background: #FAF8F5;
    color: #1C1917;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 14px;
    line-height: 1.5;
  }

  /* Diffs */
  .diff-box {
    background: #FAF8F5;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    max-height: 260px;
    overflow-y: auto;
    line-height: 1.45;
  }
  .diff-line { padding: 1px 4px; border-radius: 3px; }
  .diff-added { background: rgba(16, 185, 129, 0.15); color: #065F46; }
  .diff-removed { background: rgba(239, 68, 68, 0.15); color: #991B1B; }
  .diff-chunk { color: #2563EB; font-weight: 600; }
  .diff-header { color: #6B7280; }

  /* Portal Directory Sheets */
  .sheet-tabs-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 20px;
  }
  .sheet-pills {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .sheet-pill {
    padding: 7px 14px;
    border-radius: var(--radius-pill);
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.15s;
  }
  .sheet-pill:hover {
    border-color: var(--border-dark);
    color: var(--text-primary);
  }
  .sheet-pill.active {
    background: var(--accent-ink);
    color: #FFFFFF;
    border-color: var(--accent-ink);
    font-weight: 600;
  }
  .sheet-pill .count-badge {
    background: rgba(0, 0, 0, 0.08);
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 0.72rem;
  }
  .sheet-pill.active .count-badge {
    background: rgba(255, 255, 255, 0.2);
    color: #FFFFFF;
  }

  /* Search & Controls Bar */
  .controls-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .search-wrapper {
    position: relative;
    flex: 1;
    max-width: 440px;
  }
  .search-wrapper i {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    font-size: 0.85rem;
  }
  .search-input {
    padding-left: 34px !important;
  }

  /* Directory & Tracker Table */
  .table-container {
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    overflow-x: auto;
    background: #FFFFFF;
  }
  table.sheet-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
    text-align: left;
  }
  table.sheet-table th {
    background: #FAF8F5;
    padding: 10px 14px;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1px solid var(--border-subtle);
  }
  table.sheet-table td {
    padding: 12px 14px;
    border-bottom: 1px solid #F5F3EF;
    vertical-align: middle;
  }
  table.sheet-table tr:hover td {
    background: #FAF8F5;
  }

  /* Portal Badges */
  .portal-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: capitalize;
  }
  .badge-ashby { background: #FAF5FF; color: #7E22CE; border: 1px solid #F3E8FF; }
  .badge-greenhouse { background: #ECFDF5; color: #047857; border: 1px solid #D1FAE5; }
  .badge-lever { background: #F0F9FF; color: #0369A1; border: 1px solid #E0F2FE; }
  .badge-workday { background: #FFFBEB; color: #B45309; border: 1px solid #FEF3C7; }
  .badge-other { background: #F5F5F4; color: #57534E; border: 1px solid #E7E5E4; }

  .ext-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--text-primary);
    text-decoration: none;
    font-size: 0.8rem;
    padding: 3px 8px;
    border-radius: 6px;
    background: #F5F5F4;
    border: 1px solid var(--border-subtle);
    transition: all 0.15s;
  }
  .ext-link:hover {
    background: #E7E5E4;
    border-color: #D6D3D1;
  }
  .intel-link {
    font-size: 0.72rem;
    padding: 2px 6px;
    border-radius: 4px;
    text-decoration: none;
    font-weight: 500;
    margin-right: 4px;
  }
  .intel-levels { background: #F5F3FF; color: #6D28D9; border: 1px solid #DDD6FE; }
  .intel-glassdoor { background: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; }

  /* Pagination Bar */
  .pagination-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: #FAF8F5;
    border-top: 1px solid var(--border-subtle);
    flex-wrap: wrap;
    gap: 12px;
  }
  .page-info {
    font-size: 0.82rem;
    color: var(--text-secondary);
  }
  .page-nav {
    display: flex;
    gap: 4px;
    align-items: center;
  }
  .page-btn {
    padding: 5px 10px;
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.15s;
  }
  .page-btn:hover:not(:disabled) {
    background: #F5F5F4;
    border-color: #A8A29E;
  }
  .page-btn.active {
    background: var(--accent-ink);
    color: #FFFFFF;
    border-color: var(--accent-ink);
    font-weight: 600;
  }
  .page-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  /* Toast notification */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #18181B;
    color: #FFFFFF;
    padding: 12px 20px;
    border-radius: 10px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.2);
    font-size: 0.88rem;
    display: none;
    z-index: 1000;
  }
</style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header>
    <div class="brand" onclick="switchView('home')" title="Applyfox Home">
      <span style="font-size: 1.3rem;">🦊</span>
      <span>Applyfox</span>
      <span class="brand-badge">STUDIO &bull; SHEETS</span>
    </div>

    <nav class="nav-tabs">
      <button class="tab-btn active" id="navBtn-home" onclick="switchView('home')">
        <i class="fa fa-sparkles"></i> Overview
      </button>
      <button class="tab-btn" id="navBtn-tailor" onclick="switchView('tailor')">
        <i class="fa fa-wand-magic-sparkles"></i> Studio &amp; Tailor
      </button>
      <button class="tab-btn" id="navBtn-portals" onclick="switchView('portals')">
        <i class="fa fa-table-list"></i> Portal Sheets (7,008)
      </button>
      <button class="tab-btn" id="navBtn-tracker" onclick="switchView('tracker')">
        <i class="fa fa-clipboard-check"></i> Tracker (<span id="appCount">0</span>)
      </button>
      <button class="tab-btn" id="navBtn-base-cv" onclick="switchView('base-cv')">
        <i class="fa fa-file-code"></i> Base main.tex
      </button>
    </nav>
  </header>

  <main>
    <!-- ========================================== -->
    <!-- VIEW 0: HOME / PRODUCT OVERVIEW FRONTPAGE   -->
    <!-- ========================================== -->
    <div id="view-home">
      <div class="hero-section">
        <div class="hero-pill">
          <span class="hero-dot"></span>
          <span>7,008 CAREER BOARDS &bull; OVERLEAF LATEX CORE &bull; V2.4</span>
        </div>
        <h1 class="hero-title">
          The career application studio <span class="hero-accent">built for code.</span>
        </h1>
        <p class="hero-subtitle">
          Author and tailor authentic Overleaf-grade LaTeX CVs for any JD. Explore 7,000+ verified career boards across Ashby, Greenhouse, Lever, and Workday with live salary and review intelligence.
        </p>

        <div class="hero-actions">
          <button class="btn btn-primary btn-lg" onclick="switchView('tailor')">
            <i class="fa fa-wand-magic-sparkles"></i> Launch CV Studio &rarr;
          </button>
          <button class="btn btn-secondary btn-lg" onclick="switchView('portals')">
            <i class="fa fa-table-list"></i> Explore 7,008 Portal Sheets
          </button>
          <button class="btn btn-secondary btn-lg" onclick="switchView('tracker')">
            <i class="fa fa-clipboard-check"></i> View My Applications
          </button>
        </div>
      </div>

      <!-- Live Interactive Terminal Architecture Showcase -->
      <div class="terminal-card" style="max-width: 960px; margin: 0 auto 36px;">
        <div class="terminal-header">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div class="traffic-lights">
              <span class="traffic-dot dot-red"></span>
              <span class="traffic-dot dot-yellow"></span>
              <span class="traffic-dot dot-green"></span>
            </div>
            <span class="terminal-tag">STANDALONE TECTONIC COMPILER &bull; XE-TEX CORE</span>
          </div>
          <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; color: #A1A1AA;">
            <i class="fa fa-bolt" style="color: #FBBF24;"></i> 1.97s BUILD &bull; 1-PAGE OVERLEAF FIT
          </div>
        </div>
        <div class="terminal-body">
          <div class="terminal-token-comment">% Applyfox intelligent JD targeting engine</div>
          <div><span class="terminal-token-cmd">\\documentclass</span>[letterpaper,11pt]{article}</div>
          <div><span class="terminal-token-cmd">\\section</span>{<span class="terminal-token-arg">PROFILE</span>}</div>
          <div>&nbsp;&nbsp;<span class="terminal-token-cmd">\\resumeItem</span>{AI-focused Engineer with <span class="terminal-token-cmd">\\textbf</span>{2.5 years of experience} building production-grade <span class="terminal-token-kw">LLM workflows</span> and <span class="terminal-token-kw">agentic AI systems</span>.}</div>
          <div><span class="terminal-token-cmd">\\section</span>{<span class="terminal-token-arg">TECHNICAL SKILLS</span>}</div>
          <div>&nbsp;&nbsp;<span class="terminal-token-cmd">\\resumeItem</span>{<span class="terminal-token-cmd">\\textbf</span>{AI/GenAI:} <span class="terminal-token-kw">LangChain, LangGraph, RAG, Tool Calling, Vector Search</span>, Python, Go}</div>
        </div>
      </div>

      <!-- Platform Statistics Strip -->
      <div class="stats-strip">
        <div class="stat-item">
          <div class="stat-num">7,008</div>
          <div class="stat-label">Verified Career Boards</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">3,212</div>
          <div class="stat-label">Ashby Portals</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">1,894</div>
          <div class="stat-label">Greenhouse Pipelines</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">1,522</div>
          <div class="stat-label">Lever Companies</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">&lt; 2.0s</div>
          <div class="stat-label">LaTeX Compilation</div>
        </div>
      </div>

      <!-- Feature Grid: What Applyfox Does -->
      <div class="section-heading">
        <span class="section-tag">ENGINEERED FOR PRODUCTION</span>
        <h2 class="section-title">Everything you need to land top tech roles</h2>
        <p class="section-desc">Applyfox is an end-to-end local platform that combines real LaTeX typesetting, career board intelligence, and meticulous application tracking.</p>
      </div>

      <div class="feature-grid">
        <div class="feature-card" onclick="switchView('tailor')">
          <div>
            <div class="feature-icon-wrapper icon-purple"><i class="fa fa-file-pdf"></i></div>
            <h3 class="feature-title">Overleaf-Grade LaTeX Engine</h3>
            <p class="feature-text">Embedded standalone Tectonic XeTeX engine that compiles genuine binary PDFs directly from LaTeX source code. Zero HTML print artifacts, pristine typography, and clickable hyperref links.</p>
          </div>
          <span class="feature-link">Open Studio &rarr;</span>
        </div>

        <div class="feature-card" onclick="switchView('tailor')">
          <div>
            <div class="feature-icon-wrapper icon-emerald"><i class="fa fa-wand-magic-sparkles"></i></div>
            <h3 class="feature-title">Intelligent JD-Tailored Sections</h3>
            <p class="feature-text">Analyzes any target job description and precisely re-aligns PROFILE, TECHNICAL SKILLS, and project tech stack headers while strictly preserving authentic candidate background.</p>
          </div>
          <span class="feature-link">Tailor a CV &rarr;</span>
        </div>

        <div class="feature-card" onclick="switchView('portals')">
          <div>
            <div class="feature-icon-wrapper icon-sky"><i class="fa fa-table-list"></i></div>
            <h3 class="feature-title">Multi-Portal Career Sheets</h3>
            <p class="feature-text">Explore 7,008 career boards with instant server-side pagination across Ashby, Greenhouse, Lever, and Workday, integrated with direct Levels.fyi salary data and Glassdoor reviews.</p>
          </div>
          <span class="feature-link">Browse Sheets &rarr;</span>
        </div>

        <div class="feature-card" onclick="switchView('tracker')">
          <div>
            <div class="feature-icon-wrapper icon-amber"><i class="fa fa-clipboard-check"></i></div>
            <h3 class="feature-title">Master Tracker &amp; Version Vault</h3>
            <p class="feature-text">Automatically records every application in your master sheet and archives the exact tailored .tex and compiled .pdf for seamless interview preparation.</p>
          </div>
          <span class="feature-link">View Tracker &rarr;</span>
        </div>
      </div>

      <!-- 3-Step Workflow -->
      <div class="section-heading" style="margin-top: 60px;">
        <span class="section-tag">SEAMLESS WORKFLOW</span>
        <h2 class="section-title">How Applyfox works</h2>
      </div>

      <div class="workflow-grid">
        <div class="step-card">
          <div class="step-num">01</div>
          <h4 class="step-title">Select Company or Paste JD</h4>
          <p class="step-text">Choose from 7,008 indexed career boards or enter your target role and paste the job responsibilities.</p>
        </div>
        <div class="step-card">
          <div class="step-num">02</div>
          <h4 class="step-title">Instant ATS Alignment</h4>
          <p class="step-text">Inspect section diffs for PROFILE, SKILLS, and PROJECTS to review targeted keyword adjustments.</p>
        </div>
        <div class="step-card">
          <div class="step-num">03</div>
          <h4 class="step-title">1-Click PDF &amp; Archive</h4>
          <p class="step-text">Compile an authentic Overleaf-quality PDF with one click, while auto-logging the application in your master tracker.</p>
        </div>
      </div>

      <!-- Call To Action Banner -->
      <div class="cta-banner">
        <h2 class="cta-title">Ready to tailor your CV for your next role?</h2>
        <p class="cta-sub">Launch the interactive CV Studio or explore 7,000+ career boards across top tech startups and unicorns.</p>
        <div style="display: flex; justify-content: center; gap: 12px; flex-wrap: wrap;">
          <button class="btn btn-primary btn-lg" style="background: #FFFFFF; color: #18181B;" onclick="switchView('tailor')">
            <i class="fa fa-wand-magic-sparkles"></i> Open CV Studio
          </button>
          <button class="btn btn-secondary btn-lg" style="background: rgba(255,255,255,0.1); color: #FFFFFF; border-color: rgba(255,255,255,0.2);" onclick="switchView('portals')">
            <i class="fa fa-table-list"></i> Browse Portal Sheets
          </button>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 1: CV STUDIO & TAILOR WORKSPACE       -->
    <!-- ========================================== -->
    <div id="view-tailor" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <a href="#" onclick="switchView('home')">Applyfox</a> / <strong>CV Studio &amp; Tailor</strong>
        </div>
        <div class="workspace-meta">
          <span class="chip chip-skill"><i class="fa fa-user"></i> Harsh Jha (IIT Indore)</span>
          <span class="chip chip-score"><i class="fa fa-bolt"></i> Tectonic XeTeX Engine Active</span>
        </div>
      </div>

      <div class="tailor-layout">
        <!-- Left Column: Input Form -->
        <div class="card">
          <div class="card-header">
            <div class="card-title"><i class="fa fa-pen-to-square"></i> Job Application Details</div>
            <span style="font-size: 0.8rem; color: var(--text-secondary);">Targeted ATS Alignment</span>
          </div>

          <form id="tailorForm" onsubmit="event.preventDefault(); handleTailor();">
            <div class="form-group">
              <label for="companyName">Target Company Name *</label>
              <input type="text" id="companyName" placeholder="e.g. Infrrd, Stripe, OpenAI, Notion..." list="companyList" required>
              <datalist id="companyList"></datalist>
            </div>

            <div class="form-row">
              <div class="form-group">
                <label for="jobTitle">Job Title / Role</label>
                <input type="text" id="jobTitle" placeholder="e.g. Python Developer (Gen AI)">
              </div>
              <div class="form-group">
                <label for="jobUrl">Job Posting / ATS URL</label>
                <input type="text" id="jobUrl" placeholder="https://jobs.ashbyhq.com/...">
              </div>
            </div>

            <!-- Referral Section -->
            <div class="referral-box">
              <label class="checkbox-label">
                <input type="checkbox" id="hasReferral" onchange="toggleReferralFields()">
                <span><i class="fa fa-user-tag" style="color: var(--accent-emerald);"></i> I have an Employee Referral for this job</span>
              </label>
              <div id="referralFields" style="display: none; margin-top: 10px;">
                <div class="form-row">
                  <div class="form-group" style="margin-bottom: 0;">
                    <label for="referralName">Referrer Name</label>
                    <input type="text" id="referralName" placeholder="e.g. Alex Doe">
                  </div>
                  <div class="form-group" style="margin-bottom: 0;">
                    <label for="referralContact">Referrer Email / LinkedIn</label>
                    <input type="text" id="referralContact" placeholder="alex@company.com">
                  </div>
                </div>
              </div>
            </div>

            <div class="form-group" style="margin-top: 14px;">
              <label for="jdText">Paste Job Description (JD) *</label>
              <textarea id="jdText" placeholder="Paste the job requirements, responsibilities, and required tech stack here..." required></textarea>
            </div>

            <div class="form-group">
              <label for="appNotes">Personal Application Notes (Optional)</label>
              <input type="text" id="appNotes" placeholder="e.g. Recruiter message sent on LinkedIn, applied via Ashby portal">
            </div>

            <div class="banner-actions">
              <button type="button" id="btnTailor" class="btn btn-primary" style="flex: 1;" onclick="handleTailor()">
                <i class="fa fa-wand-magic-sparkles"></i> 1. Tailor CV
              </button>
              <button type="button" id="btnSaveApp" class="btn btn-success" style="flex: 1;" onclick="handleSaveApplication()">
                <i class="fa fa-floppy-disk"></i> 2. Save &amp; Track Job
              </button>
            </div>
          </form>
        </div>

        <!-- Right Column: Studio Output & Preview -->
        <div class="card" id="resultsCard" style="min-height: 600px;">
          <div class="card-header">
            <div class="card-title"><i class="fa fa-eye"></i> Tailored CV Studio Preview</div>
            <div id="actionDownloadButtons" style="display: none; gap: 8px; flex-wrap: wrap;">
              <button id="btnDownloadPdf" class="btn btn-primary btn-sm" onclick="downloadPdf()"><i class="fa fa-file-pdf"></i> Download PDF</button>
              <button class="btn btn-secondary btn-sm" onclick="recompilePdf()"><i class="fa fa-arrows-rotate"></i> Recompile TeX</button>
              <button class="btn btn-secondary btn-sm" onclick="downloadTex()"><i class="fa fa-download"></i> Download .tex</button>
              <button class="btn btn-secondary btn-sm" onclick="copyTex()"><i class="fa fa-copy"></i> Copy TeX</button>
            </div>
          </div>

          <div id="emptyState" style="text-align: center; padding: 90px 20px; color: var(--text-secondary);">
            <i class="fa fa-file-invoice" style="font-size: 3rem; margin-bottom: 14px; opacity: 0.35;"></i>
            <h3 style="margin: 0 0 6px 0; color: var(--text-primary); font-family: 'Newsreader', serif; font-size: 1.6rem;">No CV tailored yet</h3>
            <p style="margin: 0 0 16px 0; font-size: 0.92rem; max-width: 480px; margin-left: auto; margin-right: auto;">Enter target company and job description on the left (or pick a company from the <strong>Portal Sheets</strong> tab) and click <strong>1. Tailor CV</strong>.</p>
            <button class="btn btn-secondary btn-sm" onclick="loadBaseCvInStudio()">
              <i class="fa fa-eye"></i> Preview Base CV Right Now
            </button>
          </div>

          <div id="outputContent" style="display: none;">
            <!-- Metadata Bar -->
            <div class="meta-chips">
              <span class="chip chip-score" id="scoreBadge">Match: 0%</span>
              <span class="chip chip-archetype" id="archetypeBadge">Archetype: -</span>
              <span id="prioritySkillsChips" style="display: flex; gap: 6px; flex-wrap: wrap;"></span>
            </div>

            <!-- Subtabs -->
            <div class="results-tabs">
              <button class="subtab-btn active" id="subtabBtn-preview" onclick="switchSubTab('preview')"><i class="fa fa-file-lines"></i> Visual Paper Preview</button>
              <button class="subtab-btn" id="subtabBtn-pdf" onclick="switchSubTab('pdf')"><i class="fa fa-file-pdf"></i> Compiled LaTeX PDF</button>
              <button class="subtab-btn" id="subtabBtn-diff" onclick="switchSubTab('diff')"><i class="fa fa-code-compare"></i> Section Diffs</button>
              <button class="subtab-btn" id="subtabBtn-tex" onclick="switchSubTab('tex')"><i class="fa fa-code"></i> LaTeX Source</button>
            </div>

            <!-- Subtab 1: Visual Paper Preview -->
            <div id="subtab-preview" class="preview-frame-container">
              <iframe id="cvPreviewFrame" class="preview-frame"></iframe>
            </div>

            <!-- Subtab 2: Compiled LaTeX PDF -->
            <div id="subtab-pdf" style="display: none; height: 780px; background: #525659; border-radius: 8px; overflow: hidden;">
              <iframe id="pdfPreviewFrame" style="width: 100%; height: 100%; border: none;"></iframe>
            </div>

            <!-- Subtab 3: Diffs -->
            <div id="subtab-diff" style="display: none;">
              <div id="diffViewContainer"></div>
            </div>

            <!-- Subtab 4: TeX Code -->
            <div id="subtab-tex" style="display: none;">
              <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.82rem; color: var(--text-secondary);"><i class="fa fa-pencil"></i> You can edit this LaTeX source directly and click <strong>Recompile TeX</strong> to update both previews.</span>
                <button class="btn btn-primary btn-sm" onclick="recompilePdf()"><i class="fa fa-arrows-rotate"></i> Recompile TeX</button>
              </div>
              <textarea id="tailoredTexArea" class="tex-code" style="height: 650px;"></textarea>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 2: PORTAL SHEETS WORKSPACE            -->
    <!-- ========================================== -->
    <div id="view-portals" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <a href="#" onclick="switchView('home')">Applyfox</a> / <strong>ATS Career Portal Sheets (7,008 Boards)</strong>
        </div>
        <div class="workspace-meta">
          <span class="chip chip-skill"><i class="fa fa-chart-line"></i> Levels.fyi Integrated</span>
          <span class="chip chip-score"><i class="fa fa-star"></i> Glassdoor Reviews</span>
        </div>
      </div>

      <div class="card">
        <!-- Sheet Selector Pills -->
        <div class="sheet-tabs-container">
          <div class="sheet-pills" id="sheetPillsContainer">
            <!-- Rendered dynamically via JS -->
          </div>
        </div>

        <!-- Search & Control Bar -->
        <div class="controls-bar">
          <div class="search-wrapper">
            <i class="fa fa-magnifying-glass"></i>
            <input type="text" id="portalSearch" class="search-input" placeholder="Search companies by name, slug, or portal..." oninput="onPortalSearchInput(this.value)">
          </div>

          <div style="display: flex; gap: 10px; align-items: center;">
            <span style="font-size: 0.82rem; color: var(--text-secondary);">Per page:</span>
            <select id="portalLimitSelect" onchange="onPortalLimitChange(this.value)" style="width: auto; padding: 6px 10px; font-size: 0.82rem;">
              <option value="25" selected>25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        <!-- Paginated Table -->
        <div class="table-container">
          <table class="sheet-table" id="portalTable">
            <thead>
              <tr>
                <th style="width: 50px;">#</th>
                <th>Company Name</th>
                <th>Portal / ATS</th>
                <th>Open Roles</th>
                <th>Career Board</th>
                <th>Intelligence Links</th>
                <th style="text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody id="portalTableBody">
              <tr>
                <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                  <i class="fa fa-spinner fa-spin"></i> Loading directory sheet...
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Pagination Footer -->
          <div class="pagination-bar" id="portalPaginationBar">
            <div class="page-info" id="portalPageInfo">Showing 0 of 0</div>
            <div class="page-nav" id="portalPageNav"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 3: APPLICATIONS TRACKER WORKSPACE      -->
    <!-- ========================================== -->
    <div id="view-tracker" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <a href="#" onclick="switchView('home')">Applyfox</a> / <strong>Applications Tracker ("The Sheet")</strong>
        </div>
        <div class="workspace-meta">
          <a href="/api/export_csv" class="btn btn-secondary btn-sm" style="text-decoration: none;"><i class="fa fa-file-csv"></i> Export CSV</a>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title"><i class="fa fa-table"></i> Master Tracked Applications</div>
          <div style="display: flex; gap: 8px;">
            <input type="text" id="trackerSearch" placeholder="Search company or title..." oninput="filterTrackerTable()" style="width: 250px; padding: 6px 10px;">
          </div>
        </div>

        <div class="table-container">
          <table class="sheet-table" id="trackerTable">
            <thead>
              <tr>
                <th>Date Applied</th>
                <th>Company</th>
                <th>Job Title</th>
                <th>Status</th>
                <th>Referral</th>
                <th>Match Score</th>
                <th>Key Skills Targeted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="trackerTableBody">
              <tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 40px;">No job applications tracked yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 4: BASE CV LATEX SOURCE WORKSPACE     -->
    <!-- ========================================== -->
    <div id="view-base-cv" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <a href="#" onclick="switchView('home')">Applyfox</a> / <strong>Base CV LaTeX Source &mdash; data/main.tex</strong>
        </div>
        <div class="workspace-meta">
          <span class="chip chip-skill"><i class="fa fa-graduation-cap"></i> IIT Indore</span>
        </div>
      </div>

      <div class="card">
        <textarea id="baseTexContent" class="tex-code" style="height: 750px;" readonly></textarea>
      </div>
    </div>
  </main>

  <div id="toast" class="toast"></div>

<script>
let CURRENT_TAILORED_RESULT = null;
let TRACKED_APPLICATIONS = [];
let CURRENT_PDF_PREVIEW_URL = "";

// Directory Sheets State
let CURRENT_SHEET_KEY = "master";
let CURRENT_PAGE = 1;
let CURRENT_LIMIT = 25;
let CURRENT_QUERY = "";
let SEARCH_DEBOUNCE_TIMER = null;

// Initialize
window.addEventListener("DOMContentLoaded", () => {
  loadCompaniesAutocomplete();
  loadBaseTex();
  loadTrackerData();
  loadPortalSheetsSummary();
});

// View Navigation: 'home', 'tailor', 'portals', 'tracker', 'base-cv'
function switchView(viewName) {
  document.getElementById("view-home").style.display = (viewName === 'home') ? 'block' : 'none';
  document.getElementById("view-tailor").style.display = (viewName === 'tailor') ? 'block' : 'none';
  document.getElementById("view-portals").style.display = (viewName === 'portals') ? 'block' : 'none';
  document.getElementById("view-tracker").style.display = (viewName === 'tracker') ? 'block' : 'none';
  document.getElementById("view-base-cv").style.display = (viewName === 'base-cv') ? 'block' : 'none';

  const btns = document.querySelectorAll(".nav-tabs .tab-btn");
  btns.forEach(b => b.classList.remove("active"));
  
  if (viewName === 'home') {
    const btn = document.getElementById("navBtn-home");
    if (btn) btn.classList.add("active");
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'tailor') {
    const btn = document.getElementById("navBtn-tailor");
    if (btn) btn.classList.add("active");
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'portals') {
    const btn = document.getElementById("navBtn-portals");
    if (btn) btn.classList.add("active");
    loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'tracker') {
    const btn = document.getElementById("navBtn-tracker");
    if (btn) btn.classList.add("active");
    loadTrackerData();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'base-cv') {
    const btn = document.getElementById("navBtn-base-cv");
    if (btn) btn.classList.add("active");
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

// Subtabs in CV Studio
function switchSubTab(subTabName) {
  document.getElementById("subtab-preview").style.display = (subTabName === 'preview') ? 'block' : 'none';
  document.getElementById("subtab-pdf").style.display = (subTabName === 'pdf') ? 'block' : 'none';
  document.getElementById("subtab-diff").style.display = (subTabName === 'diff') ? 'block' : 'none';
  document.getElementById("subtab-tex").style.display = (subTabName === 'tex') ? 'block' : 'none';

  document.querySelectorAll(".subtab-btn").forEach(btn => btn.classList.remove("active"));
  const btn = document.getElementById("subtabBtn-" + subTabName);
  if (btn) btn.classList.add("active");

  if (subTabName === 'pdf') {
    const frame = document.getElementById("pdfPreviewFrame");
    if (!frame.src || frame.src === "about:blank" || frame.src.endsWith("#empty")) {
      loadCompiledPdfPreview();
    }
  }
}

async function loadCompiledPdfPreview() {
  const tex = document.getElementById("tailoredTexArea").value;
  if (!tex) return;
  const frame = document.getElementById("pdfPreviewFrame");
  showToast("Compiling LaTeX preview via TeX engine...");
  try {
    const res = await fetch("/api/preview_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailored_tex: tex })
    });
    const data = await res.json();
    if (res.ok && data.preview_url) {
      CURRENT_PDF_PREVIEW_URL = data.preview_url;
      frame.src = data.preview_url;
      showToast("LaTeX PDF preview loaded");
    } else {
      showToast("PDF compile notice: " + (data.error || "Unable to preview PDF"));
    }
  } catch (e) {
    showToast("Error loading PDF preview: " + e.message);
  }
}

async function recompilePdf() {
  const tex = document.getElementById("tailoredTexArea").value;
  if (!tex) {
    showToast("No LaTeX source to compile.");
    return;
  }
  const company = document.getElementById("companyName").value.trim() || "CV";
  showToast("Recompiling LaTeX with TeX engine...");

  try {
    const res = await fetch("/api/recompile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailored_tex: tex, company: company })
    });
    const data = await res.json();
    if (!res.ok) {
      alert("LaTeX Recompile Error: " + (data.error || "Failed to compile."));
      showToast("Recompilation error");
      return;
    }

    if (data.preview_html) {
      document.getElementById("cvPreviewFrame").srcdoc = data.preview_html;
    }
    if (data.preview_url) {
      CURRENT_PDF_PREVIEW_URL = data.preview_url;
      document.getElementById("pdfPreviewFrame").src = data.preview_url;
    }

    if (CURRENT_TAILORED_RESULT) {
      CURRENT_TAILORED_RESULT.tailored_tex = tex;
      CURRENT_TAILORED_RESULT.preview_html = data.preview_html;
    }

    showToast("LaTeX successfully recompiled!");
  } catch (e) {
    showToast("Recompile failed: " + e.message);
  }
}

function toggleReferralFields() {
  const checked = document.getElementById("hasReferral").checked;
  document.getElementById("referralFields").style.display = checked ? "block" : "none";
}

async function loadCompaniesAutocomplete() {
  try {
    const res = await fetch("/api/companies");
    const data = await res.json();
    const datalist = document.getElementById("companyList");
    datalist.innerHTML = data.map(c => `<option value="${escapeHtml(c)}"></option>`).join("");
  } catch (e) {}
}

async function loadBaseTex() {
  try {
    const res = await fetch("/api/base_tex");
    const text = await res.text();
    document.getElementById("baseTexContent").value = text;
  } catch(e) {}
}

// -------------------------------------------------------------
// PORTAL DIRECTORY SHEETS (PAGINATED & ISOLATED SHEET LOADING)
// -------------------------------------------------------------
async function loadPortalSheetsSummary() {
  try {
    const res = await fetch("/api/portals/summary");
    const summaries = await res.json();
    const container = document.getElementById("sheetPillsContainer");

    container.innerHTML = summaries.map(s => {
      const activeClass = (s.key === CURRENT_SHEET_KEY) ? "active" : "";
      return `
        <button class="sheet-pill ${activeClass}" onclick="switchPortalSheet('${s.key}')">
          <i class="fa ${s.icon}"></i>
          <span>${s.title}</span>
          <span class="count-badge">${s.total_count.toLocaleString()}</span>
        </button>
      `;
    }).join("");
  } catch (e) {
    console.error("Failed to load sheet summaries", e);
  }
}

function switchPortalSheet(sheetKey) {
  CURRENT_SHEET_KEY = sheetKey;
  CURRENT_PAGE = 1;
  loadPortalSheetsSummary();
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY);
}

function onPortalSearchInput(val) {
  clearTimeout(SEARCH_DEBOUNCE_TIMER);
  SEARCH_DEBOUNCE_TIMER = setTimeout(() => {
    CURRENT_QUERY = val.trim();
    CURRENT_PAGE = 1;
    loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY);
  }, 250);
}

function onPortalLimitChange(val) {
  CURRENT_LIMIT = parseInt(val, 10) || 25;
  CURRENT_PAGE = 1;
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY);
}

async function loadPortalSheetPage(sheetKey, page, limit, query) {
  const tbody = document.getElementById("portalTableBody");
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fa fa-spinner fa-spin"></i> Loading ${sheetKey} sheet page ${page}...</td></tr>`;

  try {
    const params = new URLSearchParams({
      sheet: sheetKey,
      page: page,
      limit: limit,
      q: query
    });
    const res = await fetch(`/api/portals?${params.toString()}`);
    const data = await res.json();

    renderPortalTable(data);
    renderPortalPagination(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #DC2626; padding: 40px;">Failed to load sheet data: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderPortalTable(data) {
  const tbody = document.getElementById("portalTableBody");
  if (!data.items || data.items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 50px;">No companies found matching "<strong>${escapeHtml(CURRENT_QUERY)}</strong>" in ${escapeHtml(data.sheet_title)}.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.items.map((item, idx) => {
    const ats = (item.ats || "").toLowerCase();
    let badgeClass = "badge-other";
    if (ats.includes("ashby")) badgeClass = "badge-ashby";
    if (ats.includes("greenhouse")) badgeClass = "badge-greenhouse";
    if (ats.includes("lever")) badgeClass = "badge-lever";
    if (ats.includes("workday")) badgeClass = "badge-workday";

    const jobsHtml = item.open_jobs 
      ? `<span style="font-weight: 600; color: #047857; font-size: 0.78rem;">${item.open_jobs} open roles</span>`
      : `<span style="color: var(--text-muted); font-size: 0.78rem;">Verified Board</span>`;

    const rowIndex = data.start_index + idx;

    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.78rem; font-family: monospace;">${rowIndex}</td>
        <td>
          <div style="font-weight: 600; color: var(--text-primary); font-size: 0.92rem;">${escapeHtml(item.name)}</div>
          <div style="font-size: 0.74rem; color: var(--text-muted); font-family: monospace;">slug: ${escapeHtml(item.slug)}</div>
        </td>
        <td>
          <span class="portal-badge ${badgeClass}"><i class="fa fa-tag"></i> ${escapeHtml(item.ats.toUpperCase())}</span>
        </td>
        <td>${jobsHtml}</td>
        <td>
          <a class="ext-link" href="${escapeHtml(item.board_url)}" target="_blank" rel="noopener noreferrer">
            <span>Career Portal</span> <i class="fa fa-arrow-up-right-from-square" style="font-size: 0.7rem;"></i>
          </a>
        </td>
        <td style="white-space: nowrap;">
          <a class="intel-link intel-levels" href="${escapeHtml(item.levels_url)}" target="_blank" rel="noopener noreferrer" title="View salaries on Levels.fyi">
            <i class="fa fa-chart-line"></i> Levels.fyi
          </a>
          <a class="intel-link intel-glassdoor" href="${escapeHtml(item.glassdoor_url)}" target="_blank" rel="noopener noreferrer" title="View reviews on Glassdoor">
            <i class="fa fa-star"></i> Glassdoor
          </a>
        </td>
        <td style="text-align: right; white-space: nowrap;">
          <button class="btn btn-sm btn-primary" onclick="useCompanyInStudio('${escapeHtml(item.name).replace(/'/g, "\\\\'")}', '${escapeHtml(item.board_url).replace(/'/g, "\\\\'")}')">
            <i class="fa fa-wand-magic-sparkles"></i> Tailor CV
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderPortalPagination(data) {
  const info = document.getElementById("portalPageInfo");
  info.innerHTML = `Showing ${data.start_index}&ndash;${data.end_index} of <strong>${data.total_filtered.toLocaleString()}</strong> companies in <strong>${escapeHtml(data.sheet_title)}</strong>`;

  const nav = document.getElementById("portalPageNav");
  const totalPages = data.total_pages;
  const current = data.page;

  let btnsHtml = `
    <button class="page-btn" onclick="gotoPortalPage(1)" ${current <= 1 ? 'disabled' : ''} title="First Page">&laquo;</button>
    <button class="page-btn" onclick="gotoPortalPage(${current - 1})" ${current <= 1 ? 'disabled' : ''}>Prev</button>
  `;

  const startP = Math.max(1, current - 2);
  const endP = Math.min(totalPages, current + 2);

  for (let p = startP; p <= endP; p++) {
    const active = (p === current) ? "active" : "";
    btnsHtml += `<button class="page-btn ${active}" onclick="gotoPortalPage(${p})">${p}</button>`;
  }

  btnsHtml += `
    <button class="page-btn" onclick="gotoPortalPage(${current + 1})" ${current >= totalPages ? 'disabled' : ''}>Next</button>
    <button class="page-btn" onclick="gotoPortalPage(${totalPages})" ${current >= totalPages ? 'disabled' : ''} title="Last Page">&raquo;</button>
  `;

  nav.innerHTML = btnsHtml;
}

function gotoPortalPage(page) {
  CURRENT_PAGE = page;
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY);
}

function useCompanyInStudio(name, url) {
  switchView('tailor');
  document.getElementById("companyName").value = name;
  if (url) {
    document.getElementById("jobUrl").value = url;
  }
  document.getElementById("jdText").focus();
  showToast(`Pre-filled ${name} in Studio! Paste the Job Description to tailor.`);
}

async function loadBaseCvInStudio() {
  showToast("Loading Base CV into Studio...");
  try {
    const res = await fetch("/api/base_tex");
    const data = await res.json();
    if (!data.tex) throw new Error("Base LaTeX source not found");
    
    document.getElementById("tailoredTexArea").value = data.tex;
    document.getElementById("companyName").value = "Base Master CV";
    document.getElementById("jobTitle").value = "Software Development Engineer";

    const recompileRes = await fetch("/api/recompile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailored_tex: data.tex, company: "Base Master CV" })
    });
    const recompileData = await recompileRes.json();
    if (recompileData.preview_html) {
      document.getElementById("cvPreviewFrame").srcdoc = recompileData.preview_html;
    }
    if (recompileData.preview_url) {
      CURRENT_PDF_PREVIEW_URL = recompileData.preview_url;
      document.getElementById("pdfPreviewFrame").src = recompileData.preview_url;
    }

    document.getElementById("emptyState").style.display = "none";
    document.getElementById("outputContent").style.display = "block";
    document.getElementById("actionDownloadButtons").style.display = "flex";
    document.getElementById("scoreBadge").textContent = "Base Profile";
    document.getElementById("archetypeBadge").textContent = "Master Template";
    document.getElementById("prioritySkillsChips").innerHTML = '<span class="chip chip-skill"><i class="fa fa-code"></i> data/main.tex</span>';
    switchSubTab("preview");
    showToast("Base CV loaded in Studio!");
  } catch (e) {
    showToast("Failed to load base CV: " + e.message);
  }
}

// -------------------------------------------------------------
// CV TAILORING & SAVING WORKFLOW
// -------------------------------------------------------------
async function handleTailor() {
  const company = document.getElementById("companyName").value.trim();
  const title = document.getElementById("jobTitle").value.trim();
  const url = document.getElementById("jobUrl").value.trim();
  const jd = document.getElementById("jdText").value.trim();
  const hasRef = document.getElementById("hasReferral").checked;
  const refName = document.getElementById("referralName").value.trim();
  const refContact = document.getElementById("referralContact").value.trim();

  if (!company || !jd) {
    showToast("Please provide both Company Name and Job Description.");
    alert("Please provide both Company Name and Job Description.");
    return false;
  }

  const btnTailor = document.getElementById("btnTailor");
  const origHtml = btnTailor ? btnTailor.innerHTML : "";
  if (btnTailor) {
    btnTailor.disabled = true;
    btnTailor.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Tailoring CV...';
  }
  showToast("Analyzing JD & tailoring CV...");

  try {
    const resp = await fetch("/api/tailor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company: company,
        job_title: title,
        job_url: url,
        jd: jd,
        has_referral: hasRef,
        referral_name: refName,
        referral_contact: refContact
      })
    });

    const data = await resp.json();
    if (!resp.ok) {
      showToast("Error: " + (data.error || "Failed to tailor CV"));
      alert("Error: " + (data.error || "Failed to tailor CV"));
      return false;
    }

    CURRENT_TAILORED_RESULT = data;

    // Display Output
    document.getElementById("emptyState").style.display = "none";
    document.getElementById("outputContent").style.display = "block";
    document.getElementById("actionDownloadButtons").style.display = "flex";

    // Set Metadata
    document.getElementById("scoreBadge").textContent = `Match: ${data.analysis.match_score}%`;
    document.getElementById("archetypeBadge").textContent = `Archetype: ${data.analysis.archetype.replace('_', ' ')}`;

    const chips = data.analysis.top_priorities.map(s => `<span class="chip chip-skill">${s}</span>`).join("");
    document.getElementById("prioritySkillsChips").innerHTML = chips;

    // Render Preview Iframe
    const frame = document.getElementById("cvPreviewFrame");
    frame.srcdoc = data.preview_html;

    // Reset PDF preview frame so it loads fresh on next view
    document.getElementById("pdfPreviewFrame").src = "about:blank";

    // Set Diff HTML
    document.getElementById("diffViewContainer").innerHTML = `
      <div style="margin-bottom: 16px;">
        <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">PROFILE Changes</h4>
        <div class="diff-box">${renderDiffLines(data.profile_diff)}</div>
      </div>
      <div style="margin-bottom: 16px;">
        <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">TECHNICAL SKILLS Changes</h4>
        <div class="diff-box">${renderDiffLines(data.skills_diff)}</div>
      </div>
      <div>
        <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">PROJECTS Changes</h4>
        <div class="diff-box">${renderDiffLines(data.projects_diff)}</div>
      </div>
    `;

    // Set TeX Source
    document.getElementById("tailoredTexArea").value = data.tailored_tex;

    showToast(`Successfully tailored CV for ${company}! Click 'Save & Track Job' to record it.`);
    return true;
  } catch (e) {
    showToast("Request failed: " + e.message);
    return false;
  } finally {
    if (btnTailor) {
      btnTailor.disabled = false;
      btnTailor.innerHTML = origHtml;
    }
  }
}

function renderDiffLines(diffStr) {
  if (!diffStr || !diffStr.trim()) return '<div style="color: #64748b; padding: 4px;">No changes made to this section.</div>';
  return diffStr.split('\\n').map(line => {
    let cls = 'diff-context';
    if (line.startsWith('+')) cls = 'diff-added';
    else if (line.startsWith('-')) cls = 'diff-removed';
    else if (line.startsWith('@@')) cls = 'diff-chunk';
    else if (line.startsWith('---') || line.startsWith('+++')) cls = 'diff-header';
    return `<div class="diff-line ${cls}">${escapeHtml(line)}</div>`;
  }).join('');
}

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text || '').replace(/[&<>"']/g, m => map[m]);
}

async function handleSaveApplication() {
  const btnSave = document.getElementById("btnSaveApp");
  const origHtml = btnSave ? btnSave.innerHTML : "";

  if (!CURRENT_TAILORED_RESULT) {
    const comp = document.getElementById("companyName").value.trim();
    const jd = document.getElementById("jdText").value.trim();
    if (!comp || !jd) {
      showToast("Please provide both Company Name and Job Description first.");
      alert("Please provide both Company Name and Job Description first.");
      return;
    }
    showToast("Tailoring CV before saving to tracker...");
    const ok = await handleTailor();
    if (!ok || !CURRENT_TAILORED_RESULT) return;
  }

  if (btnSave) {
    btnSave.disabled = true;
    btnSave.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Saving...';
  }

  const notes = document.getElementById("appNotes").value.trim();
  const payload = {
    company: CURRENT_TAILORED_RESULT.metadata.company_name,
    job_title: CURRENT_TAILORED_RESULT.metadata.job_title,
    job_url: CURRENT_TAILORED_RESULT.metadata.job_url,
    tailored_tex: CURRENT_TAILORED_RESULT.tailored_tex,
    metadata: CURRENT_TAILORED_RESULT.metadata,
    has_referral: CURRENT_TAILORED_RESULT.metadata.referral.has_referral,
    referral_name: CURRENT_TAILORED_RESULT.metadata.referral.referral_name,
    referral_contact: CURRENT_TAILORED_RESULT.metadata.referral.referral_contact,
    notes: notes,
    preview_html: CURRENT_TAILORED_RESULT.preview_html
  };

  try {
    const res = await fetch("/api/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Recorded application ${data.application_id} in sheet!`);
      loadTrackerData();
    } else {
      showToast("Error saving: " + data.error);
    }
  } catch (e) {
    showToast("Error saving application: " + e.message);
  } finally {
    if (btnSave) {
      btnSave.disabled = false;
      btnSave.innerHTML = origHtml;
    }
  }
}

// -------------------------------------------------------------
// TRACKER & ARCHIVES
// -------------------------------------------------------------
async function loadTrackerData() {
  try {
    const res = await fetch("/api/applications");
    const data = await res.json();
    TRACKED_APPLICATIONS = data;
    document.getElementById("appCount").textContent = data.length;
    renderTrackerTable(data);
  } catch (e) {
    console.error("Failed to load applications", e);
  }
}

function renderTrackerTable(apps) {
  const tbody = document.getElementById("trackerTableBody");
  if (!apps || apps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 40px;">No job applications tracked yet.</td></tr>';
    return;
  }

  tbody.innerHTML = apps.map(a => {
    let statusClass = "status-applied";
    const st = (a.status || "").toLowerCase();
    if (st.includes("interview")) statusClass = "status-interviewing";
    if (st.includes("offer")) statusClass = "status-offer";
    if (st.includes("reject")) statusClass = "status-rejected";

    const refHtml = a.has_referral 
      ? `<span class="chip chip-archetype" style="font-size: 0.72rem;"><i class="fa fa-user-check"></i> ${escapeHtml(a.referral_name || "Referred")}</span>`
      : `<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>`;

    const skillsHtml = (a.key_skills_matched || []).slice(0, 4).map(s => `<span class="chip chip-skill" style="font-size:0.7rem; padding: 2px 6px;">${escapeHtml(s)}</span>`).join(" ");

    return `
      <tr>
        <td style="white-space: nowrap; font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(a.applied_date || "-")}</td>
        <td><strong>${escapeHtml(a.company || "-")}</strong></td>
        <td>${escapeHtml(a.job_title || "-")}</td>
        <td>
          <select onchange="updateStatus('${a.application_id}', this.value)" style="padding: 4px 8px; font-size: 0.8rem; width: auto; border-color: var(--border-hover);">
            <option value="Applied" ${a.status === 'Applied' ? 'selected' : ''}>Applied</option>
            <option value="Interviewing" ${a.status === 'Interviewing' ? 'selected' : ''}>Interviewing</option>
            <option value="Offer" ${a.status === 'Offer' ? 'selected' : ''}>Offer</option>
            <option value="Rejected" ${a.status === 'Rejected' ? 'selected' : ''}>Rejected</option>
          </select>
        </td>
        <td>${refHtml}</td>
        <td><span class="chip chip-score">${a.match_score}%</span></td>
        <td>${skillsHtml}</td>
        <td style="white-space: nowrap;">
          <button class="btn btn-secondary btn-sm" onclick="viewArchivedCV('${a.application_id}')"><i class="fa fa-eye"></i> View CV</button>
          <a class="btn btn-primary btn-sm" href="/api/application/${a.application_id}/download_pdf" download><i class="fa fa-file-pdf"></i> PDF</a>
          <a class="btn btn-secondary btn-sm" href="/api/application/${a.application_id}/download_tex" download><i class="fa fa-download"></i> .tex</a>
        </td>
      </tr>
    `;
  }).join("");
}

function filterTrackerTable() {
  const q = document.getElementById("trackerSearch").value.toLowerCase();
  const filtered = TRACKED_APPLICATIONS.filter(a => 
    (a.company && a.company.toLowerCase().includes(q)) ||
    (a.job_title && a.job_title.toLowerCase().includes(q)) ||
    (a.referral_name && a.referral_name.toLowerCase().includes(q))
  );
  renderTrackerTable(filtered);
}

async function updateStatus(appId, newStatus) {
  try {
    await fetch(`/api/application/${appId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Updated status for ${appId} to ${newStatus}`);
    loadTrackerData();
  } catch (e) {
    showToast("Failed to update status");
  }
}

async function viewArchivedCV(appId) {
  try {
    const res = await fetch(`/api/application/${appId}`);
    const data = await res.json();
    if (!res.ok) {
      showToast("Could not load archive");
      return;
    }

    CURRENT_TAILORED_RESULT = {
      tailored_tex: data.tailored_tex,
      preview_html: data.preview_html,
      analysis: {
        match_score: data.match_score,
        archetype: data.metadata?.archetype || "GENERAL_SDE",
        top_priorities: data.key_skills_matched || []
      },
      metadata: data.metadata || {}
    };

    switchView('tailor');
    document.getElementById("companyName").value = data.company || "";
    document.getElementById("jobTitle").value = data.job_title || "";
    document.getElementById("jobUrl").value = data.job_url || "";
    document.getElementById("hasReferral").checked = data.has_referral;
    toggleReferralFields();
    document.getElementById("referralName").value = data.referral_name || "";
    document.getElementById("referralContact").value = data.referral_contact || "";
    document.getElementById("appNotes").value = data.notes || "";

    document.getElementById("emptyState").style.display = "none";
    document.getElementById("outputContent").style.display = "block";
    document.getElementById("actionDownloadButtons").style.display = "flex";

    document.getElementById("scoreBadge").textContent = `Match: ${data.match_score}%`;
    document.getElementById("archetypeBadge").textContent = `Archetype: ${(data.metadata?.archetype || 'SDE').replace('_', ' ')}`;
    document.getElementById("prioritySkillsChips").innerHTML = (data.key_skills_matched || []).map(s => `<span class="chip chip-skill">${s}</span>`).join("");

    const frame = document.getElementById("cvPreviewFrame");
    frame.srcdoc = data.preview_html || "Preview not available";
    document.getElementById("tailoredTexArea").value = data.tailored_tex || "";

    document.getElementById("pdfPreviewFrame").src = `/api/application/${appId}/preview_pdf`;
    showToast(`Loaded archived CV for ${data.company} (${appId})`);
  } catch (e) {
    showToast("Error loading archived CV: " + e.message);
  }
}

// -------------------------------------------------------------
// DOWNLOAD HANDLERS
// -------------------------------------------------------------
async function downloadPdf() {
  const tex = document.getElementById("tailoredTexArea").value;
  if (!tex) {
    showToast("No CV tailored yet!");
    return;
  }
  const company = document.getElementById("companyName").value.trim() || "Company";
  const btn = document.getElementById("btnDownloadPdf");
  const origHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Compiling...';
  }
  showToast("Compiling LaTeX with TeX engine to produce authentic Overleaf-grade PDF...");

  try {
    const res = await fetch("/api/compile_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailored_tex: tex, company: company })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: "LaTeX compilation failed" }));
      alert("LaTeX Compilation Error: " + (err.error || "Failed to compile."));
      throw new Error(err.error || "Compilation failed");
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Harsh_Jha_CV_${company.replace(/\\s+/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast("Genuine Overleaf-grade PDF downloaded successfully!");
  } catch (e) {
    showToast("Download failed: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

function copyTex() {
  const tex = document.getElementById("tailoredTexArea").value;
  navigator.clipboard.writeText(tex).then(() => {
    showToast("Copied LaTeX source to clipboard!");
  });
}

function downloadTex() {
  const tex = document.getElementById("tailoredTexArea").value;
  const company = document.getElementById("companyName").value.trim() || "company";
  const blob = new Blob([tex], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Harsh_Jha_CV_${company.replace(/\\s+/g, '_')}.tex`;
  a.click();
  URL.revokeObjectURL(url);
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.style.display = "block";
  setTimeout(() => { toast.style.display = "none"; }, 3500);
}
</script>
</body>
</html>
"""


class CVAppRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler implementing REST API and UI serving."""

    def log_message(self, format, *args):
        # Clean logging
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

        elif path == "/api/companies":
            comps = get_cached_companies()
            self.send_json(200, comps)

        elif path == "/api/portals/summary":
            summaries = get_sheets_summary()
            self.send_json(200, summaries)

        elif path == "/api/portals":
            qs = urllib.parse.parse_qs(parsed.query)
            sheet = qs.get("sheet", ["master"])[0]
            try:
                page = int(qs.get("page", [1])[0])
            except (ValueError, TypeError):
                page = 1
            try:
                limit = int(qs.get("limit", [25])[0])
            except (ValueError, TypeError):
                limit = 25
            q = qs.get("q", [""])[0]

            data = get_sheet_page(sheet_key=sheet, page=page, limit=limit, query=q)
            self.send_json(200, data)

        elif path == "/api/base_tex":
            if BASE_TEX_PATH.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(BASE_TEX_PATH.read_bytes())
            else:
                self.send_json(404, {"error": "Base main.tex not found"})

        elif path == "/api/applications":
            apps = list_applications()
            self.send_json(200, apps)

        elif path == "/api/export_csv":
            tracker_csv = Path("data/job_applications_tracker.csv")
            if tracker_csv.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="job_applications_tracker.csv"')
                self.end_headers()
                self.wfile.write(tracker_csv.read_bytes())
            else:
                self.send_json(404, {"error": "Tracker CSV not created yet."})

        elif path.startswith("/api/application/") and path.endswith("/download_tex"):
            app_id = path.split("/")[3]
            app = get_application(app_id)
            if app and "tailored_tex" in app:
                filename = f"Harsh_Jha_CV_{app.get('company', 'job')}.tex"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.end_headers()
                self.wfile.write(app["tailored_tex"].encode("utf-8"))
            else:
                self.send_json(404, {"error": "Application archive not found"})

        elif path.startswith("/api/application/") and path.endswith("/download_pdf"):
            app_id = path.split("/")[3]
            app = get_application(app_id)
            if app:
                archive_dir = Path(app.get("archive_dir", ""))
                pdf_file = archive_dir / "tailored_cv.pdf"
                tex_file = archive_dir / "tailored_cv.tex"
                if not pdf_file.is_file() and tex_file.is_file():
                    compile_tex_to_pdf(tex_file, archive_dir, "tailored_cv.pdf")
                if pdf_file.is_file():
                    safe_company = re.sub(r'[^a-zA-Z0-9_-]', '_', app.get('company', 'job'))
                    filename = f"Harsh_Jha_CV_{safe_company}.pdf"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.end_headers()
                    self.wfile.write(pdf_file.read_bytes())
                    return
            self.send_json(404, {"error": "PDF not found or compilation failed"})

        elif path.startswith("/api/application/") and path.endswith("/preview_pdf"):
            app_id = path.split("/")[3]
            app = get_application(app_id)
            if app:
                archive_dir = Path(app.get("archive_dir", ""))
                pdf_file = archive_dir / "tailored_cv.pdf"
                tex_file = archive_dir / "tailored_cv.tex"
                if not pdf_file.is_file() and tex_file.is_file():
                    compile_tex_to_pdf(tex_file, archive_dir, "tailored_cv.pdf")
                if pdf_file.is_file():
                    safe_company = re.sub(r'[^a-zA-Z0-9_-]', '_', app.get('company', 'job'))
                    filename = f"Harsh_Jha_CV_{safe_company}.pdf"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'inline; filename="{filename}"')
                    self.end_headers()
                    self.wfile.write(pdf_file.read_bytes())
                    return
            self.send_json(404, {"error": "PDF not found or compilation failed"})

        elif path.startswith("/api/temp_pdf/"):
            fname = Path(path.split("/")[-1]).name
            target = PREVIEW_CACHE_DIR / fname
            if target.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'inline; filename="{fname}"')
                self.end_headers()
                self.wfile.write(target.read_bytes())
                return
            self.send_json(404, {"error": "Preview PDF expired or not found"})

        elif path.startswith("/api/application/"):
            app_id = path.split("/")[3]
            app = get_application(app_id)
            if app:
                self.send_json(200, app)
            else:
                self.send_json(404, {"error": "Application not found"})

        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON payload"})
            return

        if path == "/api/tailor":
            company = payload.get("company", "").strip()
            title = payload.get("job_title", "").strip()
            url = payload.get("job_url", "").strip()
            jd = payload.get("jd", "").strip()
            has_ref = payload.get("has_referral", False)
            ref_name = payload.get("referral_name", "").strip()
            ref_contact = payload.get("referral_contact", "").strip()

            if not company or not jd:
                self.send_json(400, {"error": "Both company name and job description are required."})
                return

            try:
                res = tailor_cv(
                    base_tex_path=BASE_TEX_PATH,
                    jd_text=jd,
                    company_name=company,
                    job_title=title or None,
                    job_url=url or None,
                    referral_name=ref_name if has_ref else None,
                    referral_contact=ref_contact if has_ref else None,
                )

                preview_html = render_resume_to_html(res.tailored_tex, title_badge=company)

                self.send_json(200, {
                    "tailored_tex": res.tailored_tex,
                    "profile_diff": res.profile_diff,
                    "skills_diff": res.skills_diff,
                    "projects_diff": res.projects_diff,
                    "preview_html": preview_html,
                    "analysis": {
                        "target_title": res.analysis.target_title,
                        "archetype": res.analysis.archetype,
                        "match_score": res.analysis.match_score,
                        "top_priorities": res.analysis.top_priorities,
                        "matched_skills": res.analysis.matched_skills
                    },
                    "metadata": res.metadata
                })
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == "/api/apply":
            company = payload.get("company", "").strip()
            title = payload.get("job_title", "").strip()
            url = payload.get("job_url", "").strip()
            tex = payload.get("tailored_tex", "")
            meta = payload.get("metadata", {})
            has_ref = payload.get("has_referral", False)
            ref_name = payload.get("referral_name", "").strip()
            ref_contact = payload.get("referral_contact", "").strip()
            notes = payload.get("notes", "").strip()
            preview_html = payload.get("preview_html", "")

            if not company or not tex:
                self.send_json(400, {"error": "Company and tailored_tex required."})
                return

            try:
                record = record_application(
                    company=company,
                    job_title=title,
                    tailored_tex=tex,
                    metadata=meta,
                    job_url=url,
                    has_referral=has_ref,
                    referral_name=ref_name,
                    referral_contact=ref_contact,
                    notes=notes,
                    preview_html=preview_html
                )
                self.send_json(200, record)
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path.startswith("/api/application/") and path.endswith("/status"):
            app_id = path.split("/")[3]
            new_status = payload.get("status", "Applied")
            notes = payload.get("notes")
            updated = update_application_status(app_id, new_status, notes=notes)
            if updated:
                self.send_json(200, {"success": True, "application_id": app_id, "status": new_status})
            else:
                self.send_json(404, {"error": "Application not found"})

        elif path == "/api/compile_pdf":
            tex = payload.get("tailored_tex", "").strip()
            company = payload.get("company", "Company").strip()
            if not tex:
                self.send_json(400, {"error": "tailored_tex is required"})
                return

            session_id = uuid.uuid4().hex[:8]
            temp_compile_dir = PREVIEW_CACHE_DIR / f"compile_{session_id}"
            try:
                ok, pdf_path, msg = compile_tex_to_pdf(tex, temp_compile_dir, "tailored_cv.pdf")
                if ok and pdf_path and pdf_path.is_file():
                    safe_company = re.sub(r'[^a-zA-Z0-9_-]', '_', company)
                    filename = f"Harsh_Jha_CV_{safe_company}.pdf"
                    pdf_bytes = pdf_path.read_bytes()
                    shutil.rmtree(temp_compile_dir, ignore_errors=True)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.end_headers()
                    self.wfile.write(pdf_bytes)
                else:
                    shutil.rmtree(temp_compile_dir, ignore_errors=True)
                    self.send_json(500, {"error": f"LaTeX Compilation Failed: {msg}"})
            except Exception as e:
                shutil.rmtree(temp_compile_dir, ignore_errors=True)
                self.send_json(500, {"error": f"Compilation execution error: {str(e)}"})

        elif path == "/api/preview_pdf":
            tex = payload.get("tailored_tex", "").strip()
            if not tex:
                self.send_json(400, {"error": "tailored_tex is required"})
                return

            token = uuid.uuid4().hex[:12]
            temp_out = PREVIEW_CACHE_DIR / f"preview_{token}"
            try:
                ok, pdf_path, msg = compile_tex_to_pdf(tex, temp_out, f"preview_{token}.pdf")
                if ok and pdf_path and pdf_path.is_file():
                    target_pdf = PREVIEW_CACHE_DIR / f"preview_{token}.pdf"
                    shutil.move(str(pdf_path), str(target_pdf))
                    shutil.rmtree(temp_out, ignore_errors=True)
                    self.send_json(200, {"success": True, "preview_url": f"/api/temp_pdf/preview_{token}.pdf"})
                else:
                    shutil.rmtree(temp_out, ignore_errors=True)
                    self.send_json(500, {"error": f"LaTeX Preview Compilation Failed: {msg}"})
            except Exception as e:
                shutil.rmtree(temp_out, ignore_errors=True)
                self.send_json(500, {"error": f"Execution error: {str(e)}"})

        elif path == "/api/recompile":
            tex = payload.get("tailored_tex", "").strip()
            company = payload.get("company", "CV").strip()
            if not tex:
                self.send_json(400, {"error": "tailored_tex is required"})
                return

            # Re-render HTML preview
            preview_html = render_resume_to_html(tex, title_badge=company)

            # Also compile PDF preview
            token = uuid.uuid4().hex[:12]
            temp_out = PREVIEW_CACHE_DIR / f"preview_{token}"
            preview_url = None
            try:
                ok, pdf_path, msg = compile_tex_to_pdf(tex, temp_out, f"preview_{token}.pdf")
                if ok and pdf_path and pdf_path.is_file():
                    target_pdf = PREVIEW_CACHE_DIR / f"preview_{token}.pdf"
                    shutil.move(str(pdf_path), str(target_pdf))
                    shutil.rmtree(temp_out, ignore_errors=True)
                    preview_url = f"/api/temp_pdf/preview_{token}.pdf"
                else:
                    shutil.rmtree(temp_out, ignore_errors=True)
            except Exception:
                shutil.rmtree(temp_out, ignore_errors=True)

            self.send_json(200, {
                "success": True,
                "preview_html": preview_html,
                "preview_url": preview_url
            })

        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def send_json(self, status_code: int, data: Any):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def run_server(port: int = 8080):
    """Start local web server."""
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, CVAppRequestHandler)
    print(f"\n=======================================================")
    print(f" Applyfox CV Studio & Multi-Portal Sheets Engine")
    print(f" Access URL: http://127.0.0.1:{port}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server(8080)
