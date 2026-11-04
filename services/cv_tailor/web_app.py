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

  html, body {
    overflow-x: hidden;
    max-width: 100vw;
    width: 100%;
  }

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
  header.app-header {
    background: rgba(250, 248, 245, 0.95);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border-subtle);
    padding: 10px 24px;
    position: sticky;
    top: 0;
    z-index: 100;
    width: 100%;
  }
  .header-inner {
    max-width: 1540px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    width: 100%;
  }
  .header-brand-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    text-decoration: none;
    letter-spacing: -0.02em;
    cursor: pointer;
    flex-shrink: 0;
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
  .header-nav-container {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .nav-tabs {
    display: flex;
    gap: 4px;
    background: #F0EDE8;
    padding: 4px;
    border-radius: 12px;
    border: 1px solid var(--border-subtle);
    align-items: center;
  }
  .tab-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.84rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    align-items: center;
    gap: 7px;
    white-space: nowrap;
    flex-shrink: 0;
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
  .desktop-github-btn {
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    font-size: 0.82rem;
    flex-shrink: 0;
  }
  .mobile-github-btn {
    display: none;
    text-decoration: none;
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

  /* Landing Page Dedicated Width & Spacing (Prevents Stretched Content) */
  #view-home {
    max-width: 1140px;
    margin: 0 auto;
  }

  .stats-strip {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px 28px;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin: 36px 0 44px;
    box-shadow: var(--card-shadow);
  }
  .stat-item {
    text-align: center;
    transition: transform 0.15s ease;
  }
  .stat-item:hover {
    transform: translateY(-2px);
  }
  .stat-num {
    font-family: 'Newsreader', serif;
    font-size: 2.2rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.1;
  }
  .stat-label {
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    text-transform: uppercase;
    margin-top: 5px;
  }

  /* Refined Warm CTA Banner */
  .cta-banner {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: 20px;
    padding: 56px 36px;
    text-align: center;
    margin: 54px 0 40px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02), 0 12px 32px -4px rgba(28, 25, 23, 0.05);
    position: relative;
    overflow: hidden;
  }
  .cta-banner::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #0D9488, #F59E0B, #8B5CF6);
  }
  .cta-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #F4FBF9;
    border: 1px solid #CCFBF1;
    color: var(--accent-emerald-dark);
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 4px 14px;
    border-radius: var(--radius-pill);
    margin-bottom: 16px;
  }
  .cta-title {
    font-family: 'Newsreader', Georgia, serif;
    font-size: 2.5rem;
    font-weight: 500;
    color: var(--text-primary);
    margin: 0 0 12px;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .cta-title em {
    font-style: italic;
    color: var(--accent-emerald);
  }
  .cta-sub {
    font-size: 1.02rem;
    color: var(--text-secondary);
    max-width: 580px;
    margin: 0 auto 28px;
    line-height: 1.6;
  }
  .cta-actions {
    display: flex;
    justify-content: center;
    gap: 14px;
    flex-wrap: wrap;
  }

  /* Comprehensive App Footer */
  .app-footer {
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    border-radius: 20px;
    margin-top: 40px;
    margin-bottom: 24px;
    padding: 48px 36px 28px;
    box-shadow: var(--card-shadow);
  }
  .footer-inner {
    display: grid;
    grid-template-columns: 1.3fr 1fr 1.3fr;
    gap: 40px;
  }
  @media (max-width: 960px) {
    .footer-inner {
      grid-template-columns: 1fr;
      gap: 32px;
    }
  }
  .footer-col-main .footer-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .footer-desc {
    font-size: 0.88rem;
    line-height: 1.6;
    color: var(--text-secondary);
    margin-bottom: 20px;
    max-width: 340px;
  }
  .contrib-card {
    background: #FAF8F5;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 16px 18px;
  }
  .contrib-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .contrib-text {
    font-size: 0.82rem;
    line-height: 1.5;
    color: var(--text-secondary);
    margin: 0 0 12px 0;
  }
  .contrib-btn {
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
  }
  .footer-heading {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 14px;
  }
  .footer-links {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .footer-links li {
    margin-bottom: 9px;
  }
  .footer-links a {
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.86rem;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    transition: color 0.15s ease;
  }
  .footer-links a:hover {
    color: var(--accent-emerald-dark);
  }
  .creator-card {
    background: #FAF8F5;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 20px;
  }
  .creator-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }
  .creator-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0D9488 0%, #065F46 100%);
    color: #FFFFFF;
    font-weight: 700;
    font-size: 1rem;
    display: flex;
    align-items: center;
    justify-content: center;
    letter-spacing: 0.04em;
    box-shadow: 0 2px 6px rgba(13, 148, 136, 0.25);
  }
  .creator-name {
    font-weight: 700;
    font-size: 1rem;
    color: var(--text-primary);
  }
  .creator-title {
    font-size: 0.78rem;
    color: var(--accent-emerald-dark);
    font-weight: 500;
  }
  .creator-bio {
    font-size: 0.83rem;
    line-height: 1.5;
    color: var(--text-secondary);
    margin: 0 0 16px 0;
  }
  .creator-socials {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .social-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.15s ease;
  }
  .social-linkedin {
    background: #F0F7FF;
    color: #0A66C2;
    border: 1px solid #D0E4FF;
  }
  .social-linkedin:hover {
    background: #0A66C2;
    color: #FFFFFF;
  }
  .social-instagram {
    background: #FFF1F5;
    color: #E1306C;
    border: 1px solid #FFD1DF;
  }
  .social-instagram:hover {
    background: #E1306C;
    color: #FFFFFF;
  }
  .social-github {
    background: #FFFFFF;
    color: #18181B;
    border: 1px solid #E4E4E7;
  }
  .social-github:hover {
    background: #18181B;
    color: #FFFFFF;
  }
  .footer-bottom {
    margin-top: 36px;
    padding-top: 20px;
    border-top: 1px solid #EFECE6;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.82rem;
    color: var(--text-muted);
    flex-wrap: wrap;
    gap: 14px;
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
  .btn-amber {
    background: #D97706;
    color: #FFFFFF;
    border-color: #D97706;
    box-shadow: 0 1px 3px rgba(217, 119, 6, 0.25);
  }
  .btn-amber:hover {
    background: #B45309;
    border-color: #B45309;
    color: #FFFFFF;
    transform: translateY(-1px);
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

  /* Startup Funding & Intelligence Styles */
  .badge-round {
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    font-weight: 600;
    font-size: 0.72rem;
    padding: 2px 7px;
    border-radius: var(--radius-pill);
    display: inline-block;
  }
  .badge-amount {
    font-weight: 700;
    color: #047857;
    font-size: 0.84rem;
    margin-left: 4px;
  }
  .badge-sector {
    background: #FAF5FF;
    color: #7E22CE;
    border: 1px solid #F3E8FF;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
    display: inline-block;
  }
  .badge-country {
    color: var(--text-muted);
    font-size: 0.74rem;
  }
  .badge-fail-funding {
    color: #DC2626;
    font-weight: 600;
    font-size: 0.82rem;
  }

  /* Month Filter Pills */
  .month-pills {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 4px;
  }
  .month-pill {
    padding: 4px 11px;
    border-radius: var(--radius-pill);
    font-size: 0.74rem;
    font-weight: 500;
    cursor: pointer;
    background: #FFFFFF;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.15s;
  }
  .month-pill:hover {
    border-color: var(--border-dark);
    color: var(--text-primary);
  }
  .month-pill.active {
    background: var(--accent-emerald-dark);
    color: #FFFFFF;
    border-color: var(--accent-emerald-dark);
    font-weight: 600;
  }
  .month-pill .count-badge {
    background: rgba(0, 0, 0, 0.07);
    padding: 1px 5px;
    border-radius: 8px;
    font-size: 0.68rem;
  }
  .month-pill.active .count-badge {
    background: rgba(255, 255, 255, 0.25);
    color: #FFFFFF;
  }
  @media (max-width: 768px) {
    .month-pills {
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      flex-wrap: nowrap;
      padding-bottom: 4px;
    }
    .month-pills::-webkit-scrollbar {
      display: none;
    }
    .month-pill {
      flex-shrink: 0;
    }
  }

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

  /* ======================================================== */
  /* MOBILE & TABLET RESPONSIVE STYLESYSTEM                   */
  /* ======================================================== */
  @media (max-width: 960px) {
    .footer-inner {
      grid-template-columns: 1fr;
      gap: 32px;
    }
  }

  @media (max-width: 900px) {
    header.app-header {
      padding: 8px 12px;
    }
    .header-inner {
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
    }
    .header-brand-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
    }
    .desktop-github-btn {
      display: none !important;
    }
    .mobile-github-btn {
      display: inline-flex !important;
      align-items: center;
      gap: 5px;
      padding: 5px 10px;
      font-size: 0.78rem;
    }
    .header-nav-container {
      width: 100%;
      gap: 0;
    }
    .nav-tabs {
      width: 100%;
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding: 3px;
      border-radius: 10px;
    }
    .nav-tabs::-webkit-scrollbar {
      display: none;
    }
    .tab-btn {
      padding: 6px 11px;
      font-size: 0.78rem;
      gap: 5px;
    }
    .stats-strip {
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
      padding: 20px 18px;
    }
    .workflow-grid {
      grid-template-columns: 1fr;
      gap: 14px;
    }
  }

  @media (max-width: 768px) {
    main {
      padding: 12px 10px 36px;
    }
    .hero-section {
      padding: 24px 8px 18px;
    }
    .hero-pill {
      font-size: 0.65rem;
      padding: 4px 10px;
      letter-spacing: 0.05em;
      margin-bottom: 14px;
      line-height: 1.3;
    }
    .hero-title {
      font-size: 2.15rem;
      line-height: 1.18;
      margin-bottom: 12px;
    }
    .hero-subtitle {
      font-size: 0.94rem;
      line-height: 1.5;
      margin-bottom: 20px;
    }
    .hero-actions {
      flex-direction: column;
      width: 100%;
      gap: 10px;
      margin-bottom: 26px;
    }
    .hero-actions .btn {
      width: 100%;
      justify-content: center;
    }
    .section-heading {
      margin: 36px 0 20px;
    }
    .section-title {
      font-size: 1.7rem;
      line-height: 1.25;
    }
    .section-desc {
      font-size: 0.88rem;
    }
    .feature-grid {
      grid-template-columns: 1fr;
      gap: 14px;
      margin-top: 20px;
    }
    .feature-card {
      padding: 20px 18px;
    }
    .step-card {
      padding: 20px 18px;
    }
    .cta-banner {
      padding: 32px 18px;
      border-radius: 14px;
      margin: 36px 0 28px;
    }
    .cta-title {
      font-size: 1.85rem;
      line-height: 1.22;
    }
    .cta-sub {
      font-size: 0.9rem;
      margin-bottom: 22px;
    }
    .cta-actions {
      flex-direction: column;
      width: 100%;
      gap: 10px;
    }
    .cta-actions .btn {
      width: 100%;
      justify-content: center;
    }
    .card {
      padding: 18px 14px;
      border-radius: 12px;
    }
    .card-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 10px;
    }
    .form-row {
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .banner-actions {
      flex-direction: column;
      width: 100%;
      gap: 10px;
    }
    .banner-actions .btn {
      width: 100%;
      flex: none;
    }
    .results-tabs {
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding-bottom: 4px;
    }
    .results-tabs::-webkit-scrollbar {
      display: none;
    }
    .subtab-btn {
      flex-shrink: 0;
      padding: 7px 11px;
      font-size: 0.78rem;
    }
    .preview-frame-container {
      height: 520px;
    }
    #subtab-pdf {
      height: 520px !important;
    }
    .tex-code {
      height: 480px !important;
      font-size: 0.76rem;
      padding: 10px;
    }
    #baseTexContent {
      height: 520px !important;
      font-size: 0.76rem;
      padding: 10px;
    }
    .workspace-bar {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }
    .workspace-meta {
      flex-wrap: wrap;
      gap: 6px;
    }
    #actionDownloadButtons {
      width: 100%;
      gap: 6px;
    }
    #actionDownloadButtons .btn {
      flex: 1 1 calc(50% - 6px);
      justify-content: center;
      padding: 6px 8px;
      font-size: 0.75rem;
    }
    .sheet-pills {
      width: 100%;
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding-bottom: 6px;
      flex-wrap: nowrap;
    }
    .sheet-pills::-webkit-scrollbar {
      display: none;
    }
    .sheet-pill {
      flex-shrink: 0;
      padding: 6px 12px;
      font-size: 0.78rem;
    }
    .controls-bar {
      flex-direction: column;
      align-items: stretch;
      gap: 10px;
    }
    .search-wrapper {
      max-width: 100% !important;
      width: 100%;
    }
    .pagination-bar {
      flex-direction: column;
      align-items: center;
      gap: 10px;
      padding: 12px 10px;
    }
    .page-info {
      text-align: center;
      font-size: 0.78rem;
    }
    .page-nav {
      flex-wrap: wrap;
      justify-content: center;
      gap: 3px;
    }
    .page-btn {
      padding: 5px 8px;
      font-size: 0.76rem;
    }
    #trackerSearch {
      width: 100% !important;
    }
  }

  @media (max-width: 640px) {
    .terminal-card {
      padding: 12px 14px;
      border-radius: 10px;
    }
    .terminal-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
    }
    .terminal-body {
      font-size: 0.72rem;
      padding: 10px;
      line-height: 1.45;
    }
    .app-footer {
      padding: 26px 16px 20px;
      border-radius: 14px;
      margin-top: 28px;
    }
    .creator-card {
      padding: 16px 14px;
    }
    .creator-socials {
      gap: 6px;
    }
    .social-pill {
      padding: 6px 10px;
      font-size: 0.75rem;
    }
    .footer-bottom {
      flex-direction: column;
      align-items: flex-start;
      gap: 12px;
      margin-top: 24px;
      padding-top: 16px;
    }
    .footer-bottom-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
  }

  @media (max-width: 480px) {
    .hero-title {
      font-size: 1.78rem;
      line-height: 1.2;
    }
    .hero-subtitle {
      font-size: 0.88rem;
    }
    .stats-strip {
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      padding: 16px 12px;
      margin: 24px 0 32px;
    }
    .stat-num {
      font-size: 1.65rem;
    }
    .stat-label {
      font-size: 0.68rem;
    }
    .toast {
      bottom: 14px;
      right: 14px;
      left: 14px;
      font-size: 0.8rem;
      padding: 10px 14px;
      text-align: center;
    }
  }
</style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header class="app-header">
    <div class="header-inner">
      <div class="header-brand-row">
        <div class="brand" onclick="switchView('home')" title="Applyfox Home">
          <span style="font-size: 1.3rem;">🦊</span>
          <span>Applyfox</span>
          <span class="brand-badge">STUDIO &bull; SHEETS</span>
        </div>
        <a href="https://github.com/harshdotcom/Applyfox" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-secondary mobile-github-btn" title="Contribute on GitHub">
          <i class="fa-brands fa-github"></i> <span>GitHub</span>
        </a>
      </div>

      <div class="header-nav-container">
        <nav class="nav-tabs" aria-label="Main Navigation">
          <button class="tab-btn active" id="navBtn-home" onclick="switchView('home')">
            <i class="fa fa-sparkles"></i> <span>Overview</span>
          </button>
          <button class="tab-btn" id="navBtn-tailor" onclick="switchView('tailor')">
            <i class="fa fa-wand-magic-sparkles"></i> <span>Studio &amp; Tailor</span>
          </button>
          <button class="tab-btn" id="navBtn-startups" onclick="openStartupsView()">
            <i class="fa fa-rocket" style="color: #D97706;"></i> <span>2026 Startups (480)</span>
          </button>
          <button class="tab-btn" id="navBtn-portals" onclick="openPortalsView()">
            <i class="fa fa-table-list"></i> <span>Directory (7,406)</span>
          </button>
          <button class="tab-btn" id="navBtn-tracker" onclick="switchView('tracker')">
            <i class="fa fa-clipboard-check"></i> <span>Tracker (<span id="appCount">0</span>)</span>
          </button>
          <button class="tab-btn" id="navBtn-base-cv" onclick="switchView('base-cv')">
            <i class="fa fa-file-code"></i> <span>Base main.tex</span>
          </button>
        </nav>
        <a href="https://github.com/harshdotcom/Applyfox" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-secondary desktop-github-btn" title="Contribute on GitHub">
          <i class="fa-brands fa-github"></i> <span>GitHub</span>
        </a>
      </div>
    </div>
  </header>

  <main>
    <!-- ========================================== -->
    <!-- VIEW 0: HOME / PRODUCT OVERVIEW FRONTPAGE   -->
    <!-- ========================================== -->
    <div id="view-home">
      <div class="hero-section">
        <div class="hero-pill">
          <span class="hero-dot"></span>
          <span>7,406 VERIFIED COMPANIES &bull; 480 2026 FUNDED STARTUPS &bull; OVERLEAF LATEX CORE &bull; V2.4</span>
        </div>
        <h1 class="hero-title">
          The career application studio <span class="hero-accent">built for software engineers.</span>
        </h1>
        <p class="hero-subtitle">
          Author and tailor authentic Overleaf-grade LaTeX CVs for any JD. Explore 7,400+ verified career boards and 480 newly funded 2026 tech startups across Ashby, Greenhouse, Lever, and Workday with live salary, funding, and failure intelligence.
        </p>

        <div class="hero-actions">
          <button class="btn btn-primary btn-lg" onclick="switchView('tailor')">
            <i class="fa fa-wand-magic-sparkles"></i> Launch CV Studio &rarr;
          </button>
          <button class="btn btn-amber btn-lg" onclick="openStartupsView()">
            <i class="fa fa-rocket"></i> Explore 480 Funded Startups
          </button>
          <button class="btn btn-secondary btn-lg" onclick="openPortalsView()">
            <i class="fa fa-table-list"></i> Explore 7,406 Portal Sheets
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
        <div class="stat-item" onclick="openStartupsView()" style="cursor: pointer;" title="Explore 480 Startups funded in 2026">
          <div class="stat-num" style="color: #D97706;"><i class="fa fa-rocket" style="font-size: 0.8em; margin-right: 4px;"></i>480</div>
          <div class="stat-label" style="color: var(--text-primary); font-weight: 700;">2026 Funded Startups &rarr;</div>
        </div>
        <div class="stat-item" onclick="openFailuresView()" style="cursor: pointer;" title="Explore 23 Startup Failure Post-Mortems">
          <div class="stat-num" style="color: #E11D48;"><i class="fa fa-triangle-exclamation" style="font-size: 0.8em; margin-right: 4px;"></i>23</div>
          <div class="stat-label" style="color: var(--text-primary); font-weight: 700;">Failure Case Studies &rarr;</div>
        </div>
        <div class="stat-item" onclick="openPortalsView()" style="cursor: pointer;" title="Browse all 7,406 verified companies">
          <div class="stat-num">7,406</div>
          <div class="stat-label">Verified Companies &amp; Boards</div>
        </div>
        <div class="stat-item" onclick="switchPortalSheet('ashby'); switchView('portals');" style="cursor: pointer;" title="Browse Ashby career boards">
          <div class="stat-num">3,212</div>
          <div class="stat-label">Ashby Portals</div>
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

        <div class="feature-card" onclick="switchView('portals'); switchPortalSheet('funded_startups');">
          <div>
            <div class="feature-icon-wrapper icon-emerald" style="background: #ECFDF5; color: #047857;"><i class="fa fa-rocket"></i></div>
            <h3 class="feature-title">2026 Startup Funding &amp; Risk Intelligence</h3>
            <p class="feature-text">Track 480 tech startups that raised Series A-D funding in 2026 month-by-month (Jan&ndash;Nov), alongside 23 failure post-mortems with risk signals and engineering lessons.</p>
          </div>
          <span class="feature-link">Explore 480 Startups &rarr;</span>
        </div>

        <div class="feature-card" onclick="switchView('portals')">
          <div>
            <div class="feature-icon-wrapper icon-sky"><i class="fa fa-table-list"></i></div>
            <h3 class="feature-title">Multi-Portal Career Sheets</h3>
            <p class="feature-text">Explore 7,406 career boards with instant server-side pagination across Ashby, Greenhouse, Lever, and Workday, integrated with direct Levels.fyi salary data and Glassdoor reviews.</p>
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

      <!-- Refined Warm CTA Banner -->
      <div class="cta-banner">
        <div class="cta-pill">
          <i class="fa fa-sparkles"></i> START TAILORING TODAY
        </div>
        <h2 class="cta-title">Ready to tailor your CV <em>for your next role?</em></h2>
        <p class="cta-sub">Launch the interactive CV Studio or explore 7,008 verified career boards across top tech startups, scaleups, and unicorns.</p>
        <div class="cta-actions">
          <button class="btn btn-primary btn-lg" onclick="switchView('tailor')">
            <i class="fa fa-wand-magic-sparkles"></i> Launch CV Studio &rarr;
          </button>
          <button class="btn btn-secondary btn-lg" onclick="switchView('portals')">
            <i class="fa fa-table-list"></i> Explore 7,008 Portal Sheets
          </button>
        </div>
      </div>

      <!-- ========================================== -->
      <!-- FOOTER: CREATOR & OPEN SOURCE CONTRIBUTION -->
      <!-- ========================================== -->
      <footer class="app-footer">
        <div class="footer-inner">
          <!-- Col 1: Brand & Open Source Contributions -->
          <div class="footer-col footer-col-main">
            <div class="footer-brand">
              <span style="font-size: 1.4rem;">🦊</span>
              <span style="font-weight: 700; font-size: 1.15rem; color: var(--text-primary); letter-spacing: -0.02em;">Applyfox</span>
              <span class="brand-badge">STUDIO &bull; SHEETS</span>
            </div>
            <p class="footer-desc">
              An open-source, local-first career intelligence platform and Overleaf-grade LaTeX CV studio engineered for developers.
            </p>

            <div class="contrib-card">
              <div class="contrib-header">
                <i class="fa-brands fa-github" style="font-size: 1.15rem; color: #18181B;"></i>
                <span style="font-weight: 600; font-size: 0.88rem; color: #18181B;">Open Source Contributions</span>
              </div>
              <p class="contrib-text">
                Applyfox is open-source! We welcome community contributions &mdash; add new ATS career boards, improve CV tailoring algorithms, or submit LaTeX templates.
              </p>
              <a href="https://github.com/harshdotcom/Applyfox" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary contrib-btn">
                <i class="fa-solid fa-code-fork"></i> Star &amp; Contribute on GitHub &rarr;
              </a>
            </div>
          </div>

          <!-- Col 2: Workspace & Portal Links -->
          <div class="footer-col">
            <div class="footer-heading">WORKSPACE NAVIGATION</div>
            <ul class="footer-links">
              <li><a href="#" onclick="switchView('tailor'); return false;"><i class="fa fa-wand-magic-sparkles"></i> CV Studio &amp; Tailor</a></li>
              <li><a href="#" onclick="openStartupsView(); return false;"><i class="fa fa-rocket" style="color: #D97706;"></i> 2026 Startups Tracker (480)</a></li>
              <li><a href="#" onclick="openPortalsView(); return false;"><i class="fa fa-table-list"></i> Directory Sheets (7,406)</a></li>
              <li><a href="#" onclick="switchView('tracker'); return false;"><i class="fa fa-clipboard-check"></i> Applications Tracker</a></li>
              <li><a href="#" onclick="switchView('base-cv'); return false;"><i class="fa fa-file-code"></i> Base LaTeX main.tex</a></li>
            </ul>

            <div class="footer-heading" style="margin-top: 22px;">CAREER PORTALS &amp; STARTUPS</div>
            <ul class="footer-links">
              <li><a href="#" onclick="openStartupsView(); return false;"><i class="fa fa-rocket" style="color: #D97706;"></i> 2026 Funded Startups (480)</a></li>
              <li><a href="#" onclick="openFailuresView(); return false;"><i class="fa fa-triangle-exclamation" style="color: #E11D48;"></i> Failures &amp; Distress (23)</a></li>
              <li><a href="#" onclick="openPortalsView(); return false;"><i class="fa fa-globe"></i> Master Sheet (7,406)</a></li>
              <li><a href="#" onclick="switchView('portals'); switchPortalSheet('ashby'); return false;"><i class="fa fa-bolt"></i> Ashby Boards (3,212)</a></li>
              <li><a href="#" onclick="switchView('portals'); switchPortalSheet('greenhouse'); return false;"><i class="fa fa-seedling"></i> Greenhouse Portals (1,894)</a></li>
              <li><a href="#" onclick="switchView('portals'); switchPortalSheet('lever'); return false;"><i class="fa fa-sliders"></i> Lever Boards (1,522)</a></li>
            </ul>
          </div>

          <!-- Col 3: Creator Attribution & Profiles -->
          <div class="footer-col footer-col-creator">
            <div class="footer-heading">CRAFTED &amp; ENGINEERED BY</div>
            <div class="creator-card">
              <div class="creator-header">
                <div class="creator-avatar">HJ</div>
                <div>
                  <div class="creator-name">Harsh Jha</div>
                  <div class="creator-title">IIT Indore Alumnus &bull; Senior AI Engineer</div>
                </div>
              </div>
              <p class="creator-bio">
                Senior AI Engineer building scalable cloud-native architectures, agentic AI systems, and developer tools.
              </p>
              
              <div class="creator-socials">
                <a href="https://www.linkedin.com/in/harshjha-iiti/" target="_blank" rel="noopener noreferrer" class="social-pill social-linkedin" title="Connect on LinkedIn">
                  <i class="fa-brands fa-linkedin"></i>
                  <span>LinkedIn</span>
                  <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 0.65rem; opacity: 0.7;"></i>
                </a>
                <a href="https://www.instagram.com/jhaharsh03/" target="_blank" rel="noopener noreferrer" class="social-pill social-instagram" title="Follow on Instagram">
                  <i class="fa-brands fa-instagram"></i>
                  <span>Instagram</span>
                  <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 0.65rem; opacity: 0.7;"></i>
                </a>
                <a href="https://github.com/jhaharsh03" target="_blank" rel="noopener noreferrer" class="social-pill social-github" title="Follow on GitHub">
                  <i class="fa-brands fa-github"></i>
                  <span>GitHub</span>
                  <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 0.65rem; opacity: 0.7;"></i>
                </a>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer Bottom Copyright & Meta -->
        <div class="footer-bottom">
          <div>
            &copy; 2026 Applyfox &bull; Designed &amp; Developed by <strong>Harsh Jha</strong> &bull; Open Source under MIT License.
          </div>
          <div class="footer-bottom-badges">
            <span class="chip chip-skill"><i class="fa-solid fa-bolt"></i> Tectonic XeTeX Engine</span>
            <span class="chip chip-score"><i class="fa-solid fa-shield-halved"></i> 100% Local &amp; Private</span>
          </div>
        </div>
      </footer>
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
          <a href="#" onclick="switchView('home')">Applyfox</a> / <strong>ATS Portals &amp; 2026 Startup Sheets (7,406 Companies)</strong>
        </div>
        <div class="workspace-meta">
          <span class="chip chip-skill"><i class="fa fa-chart-line"></i> Levels.fyi Integrated</span>
          <span class="chip chip-score"><i class="fa fa-rocket"></i> 2026 Funded Tracker</span>
        </div>
      </div>

      <div class="card">
        <!-- Sheet Selector Pills -->
        <div class="sheet-tabs-container">
          <div class="sheet-pills" id="sheetPillsContainer">
            <!-- Rendered dynamically via JS -->
          </div>
        </div>

        <!-- Month Filter Pills (Visible when 2026 Funded Startups is active) -->
        <div id="monthFilterContainer" style="display: none; margin-bottom: 16px; padding: 12px 14px; background: #FAF8F5; border-radius: 10px; border: 1px dashed #D6D3D1;">
          <div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-secondary); margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
            <i class="fa fa-calendar" style="color: var(--accent-emerald);"></i> <span>Filter 2026 Funding Rounds by Month:</span>
          </div>
          <div class="month-pills" id="monthPillsContainer">
            <!-- Rendered dynamically via JS -->
          </div>
        </div>

        <!-- Search & Control Bar -->
        <div class="controls-bar">
          <div class="search-wrapper">
            <i class="fa fa-magnifying-glass"></i>
            <input type="text" id="portalSearch" class="search-input" placeholder="Search companies, startups, sectors, or rounds..." oninput="onPortalSearchInput(this.value)">
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
/* GITHUB_PAGES_EMBEDDED_DATA */
let CURRENT_TAILORED_RESULT = null;
let TRACKED_APPLICATIONS = [];
let CURRENT_PDF_PREVIEW_URL = "";

// Directory Sheets State
let CURRENT_SHEET_KEY = "funded_startups";
let CURRENT_PAGE = 1;
let CURRENT_LIMIT = 25;
let CURRENT_QUERY = "";
let CURRENT_MONTH = "";
let SEARCH_DEBOUNCE_TIMER = null;
let PORTAL_SUMMARIES = [];

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
    const activeTabId = (CURRENT_SHEET_KEY === 'funded_startups' || CURRENT_SHEET_KEY === 'startup_failures') ? 'navBtn-startups' : 'navBtn-portals';
    const btn = document.getElementById(activeTabId) || document.getElementById("navBtn-portals");
    if (btn) btn.classList.add("active");
    loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
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

function openStartupsView() {
  CURRENT_SHEET_KEY = 'funded_startups';
  CURRENT_PAGE = 1;
  CURRENT_MONTH = "";
  switchView('portals');
  renderPortalSheetsSummary(PORTAL_SUMMARIES);
}

function openFailuresView() {
  CURRENT_SHEET_KEY = 'startup_failures';
  CURRENT_PAGE = 1;
  CURRENT_MONTH = "";
  switchView('portals');
  renderPortalSheetsSummary(PORTAL_SUMMARIES);
}

function openPortalsView() {
  CURRENT_SHEET_KEY = 'master';
  CURRENT_PAGE = 1;
  CURRENT_MONTH = "";
  switchView('portals');
  renderPortalSheetsSummary(PORTAL_SUMMARIES);
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
    if (!res.ok) throw new Error("No backend");
    const data = await res.json();
    const datalist = document.getElementById("companyList");
    datalist.innerHTML = data.map(c => `<option value="${escapeHtml(c)}"></option>`).join("");
  } catch (e) {
    if (typeof EMBEDDED_ITEMS !== 'undefined') {
      const datalist = document.getElementById("companyList");
      datalist.innerHTML = EMBEDDED_ITEMS.map(c => `<option value="${escapeHtml(c.name)}"></option>`).join("");
    }
  }
}

async function loadBaseTex() {
  try {
    const res = await fetch("/api/base_tex");
    if (!res.ok) throw new Error("No backend");
    const data = await res.json();
    document.getElementById("baseTexContent").value = data.tex || "";
  } catch(e) {
    if (typeof EMBEDDED_BASE_TEX !== 'undefined') {
      document.getElementById("baseTexContent").value = EMBEDDED_BASE_TEX;
    }
  }
}

// -------------------------------------------------------------
// PORTAL DIRECTORY SHEETS (PAGINATED & ISOLATED SHEET LOADING)
// -------------------------------------------------------------
async function loadPortalSheetsSummary() {
  try {
    const res = await fetch("/api/portals/summary");
    if (!res.ok) throw new Error("No backend");
    PORTAL_SUMMARIES = await res.json();
    renderPortalSheetsSummary(PORTAL_SUMMARIES);
  } catch (e) {
    if (typeof EMBEDDED_SUMMARIES !== 'undefined') {
      PORTAL_SUMMARIES = EMBEDDED_SUMMARIES;
      renderPortalSheetsSummary(PORTAL_SUMMARIES);
    }
  }
}

function renderPortalSheetsSummary(summaries) {
  const container = document.getElementById("sheetPillsContainer");
  if (!container || !Array.isArray(summaries)) return;
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

  const activeSummary = summaries.find(s => s.key === CURRENT_SHEET_KEY);
  if (activeSummary && activeSummary.months) {
    renderMonthFilterPills(activeSummary.months);
  } else {
    const wrapper = document.getElementById("monthFilterContainer");
    if (wrapper) wrapper.style.display = 'none';
  }
}

function renderMonthFilterPills(months) {
  const container = document.getElementById("monthPillsContainer");
  const wrapper = document.getElementById("monthFilterContainer");
  if (!wrapper || !container) return;

  if (CURRENT_SHEET_KEY !== 'funded_startups') {
    wrapper.style.display = 'none';
    return;
  }

  wrapper.style.display = 'block';
  if (!months || !Array.isArray(months)) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = months.map(m => {
    const isActive = (CURRENT_MONTH === m.name || (CURRENT_MONTH === "" && m.name === "All Months")) ? "active" : "";
    return `
      <button class="month-pill ${isActive}" onclick="filterByMonth('${m.name}')">
        <span>${escapeHtml(m.name)}</span>
        <span class="count-badge">${m.count}</span>
      </button>
    `;
  }).join("");
}

function filterByMonth(monthName) {
  CURRENT_MONTH = (monthName === "All Months") ? "" : monthName;
  CURRENT_PAGE = 1;
  const summary = PORTAL_SUMMARIES.find(s => s.key === 'funded_startups');
  if (summary && summary.months) {
    renderMonthFilterPills(summary.months);
  }
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
}

function switchPortalSheet(sheetKey) {
  CURRENT_SHEET_KEY = sheetKey;
  CURRENT_PAGE = 1;
  CURRENT_MONTH = "";
  const btns = document.querySelectorAll(".nav-tabs .tab-btn");
  btns.forEach(b => b.classList.remove("active"));
  const activeTabId = (CURRENT_SHEET_KEY === 'funded_startups' || CURRENT_SHEET_KEY === 'startup_failures') ? 'navBtn-startups' : 'navBtn-portals';
  const activeTab = document.getElementById(activeTabId);
  if (activeTab) activeTab.classList.add("active");

  renderPortalSheetsSummary(PORTAL_SUMMARIES);
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
}

function onPortalSearchInput(val) {
  clearTimeout(SEARCH_DEBOUNCE_TIMER);
  SEARCH_DEBOUNCE_TIMER = setTimeout(() => {
    CURRENT_QUERY = val.trim();
    CURRENT_PAGE = 1;
    loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
  }, 250);
}

function onPortalLimitChange(val) {
  CURRENT_LIMIT = parseInt(val, 10) || 25;
  CURRENT_PAGE = 1;
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
}

function renderPortalTableHeader(kind) {
  const thead = document.querySelector("#portalTable thead");
  if (!thead) return;
  if (kind === "funded_startups") {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Startup &amp; Sector</th>
        <th>Round &amp; Capital</th>
        <th style="min-width: 200px;">What They Are Building</th>
        <th>Month &amp; Lead Investors</th>
        <th>Intelligence</th>
        <th style="text-align: right;">Action</th>
      </tr>
    `;
  } else if (kind === "startup_failures") {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Company &amp; Sector</th>
        <th>Pre-Failure Capital</th>
        <th>When &amp; What Happened</th>
        <th style="min-width: 200px;">Precise Reason</th>
        <th style="min-width: 180px;">Key Lesson</th>
        <th style="text-align: right;">Action</th>
      </tr>
    `;
  } else {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Company Name</th>
        <th>Portal / ATS</th>
        <th>Open Roles</th>
        <th>Career Board</th>
        <th>Intelligence Links</th>
        <th style="text-align: right;">Action</th>
      </tr>
    `;
  }
}

async function loadPortalSheetPage(sheetKey, page, limit, query, month = "") {
  const tbody = document.getElementById("portalTableBody");
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fa fa-spinner fa-spin"></i> Loading ${escapeHtml(sheetKey)} sheet page ${page}...</td></tr>`;

  const searchInput = document.getElementById("portalSearch");
  if (searchInput) {
    if (sheetKey === 'funded_startups') {
      searchInput.placeholder = "Search 480 funded startups by name, sector (e.g. AI), round, or investor...";
    } else if (sheetKey === 'startup_failures') {
      searchInput.placeholder = "Search failed / distressed startups by name, reason, lesson, or sector...";
    } else {
      searchInput.placeholder = "Search companies by name, slug, or portal...";
    }
  }

  try {
    const params = new URLSearchParams({
      sheet: sheetKey,
      page: page,
      limit: limit,
      q: query || "",
      month: month || ""
    });
    const res = await fetch(`/api/portals?${params.toString()}`);
    if (!res.ok) throw new Error("API not reachable");
    const data = await res.json();

    const kind = data.kind || (sheetKey === 'funded_startups' ? 'funded_startups' : (sheetKey === 'startup_failures' ? 'startup_failures' : 'standard'));
    renderPortalTableHeader(kind);
    renderPortalTable(data);
    renderPortalPagination(data);
  } catch (e) {
    handleStaticPortalFallback(sheetKey, page, limit, query, month);
  }
}

function handleStaticPortalFallback(sheetKey, page, limit, query, month) {
  let filtered = [];
  let title = "Directory Sheets";
  let kind = "standard";

  if (sheetKey === 'funded_startups') {
    kind = "funded_startups";
    title = "2026 Funded Startups";
    filtered = (typeof EMBEDDED_FUNDED_STARTUPS !== 'undefined') ? EMBEDDED_FUNDED_STARTUPS : [];
    if (month && month.toLowerCase() !== 'all' && month.toLowerCase() !== 'all months') {
      filtered = filtered.filter(i => (i.month || '').toLowerCase() === month.toLowerCase());
    }
    if (query) {
      const q = query.toLowerCase();
      filtered = filtered.filter(i => 
        (i.name || '').toLowerCase().includes(q) ||
        (i.sector || '').toLowerCase().includes(q) ||
        (i.country || '').toLowerCase().includes(q) ||
        (i.round || '').toLowerCase().includes(q) ||
        (i.what_they_build || '').toLowerCase().includes(q) ||
        (i.lead_investors || '').toLowerCase().includes(q)
      );
    }
  } else if (sheetKey === 'startup_failures') {
    kind = "startup_failures";
    title = "Failures & Distress 2026";
    filtered = (typeof EMBEDDED_FAILURES !== 'undefined') ? EMBEDDED_FAILURES : [];
    if (query) {
      const q = query.toLowerCase();
      filtered = filtered.filter(i => 
        (i.name || '').toLowerCase().includes(q) ||
        (i.sector || '').toLowerCase().includes(q) ||
        (i.country || '').toLowerCase().includes(q) ||
        (i.what_happened || '').toLowerCase().includes(q) ||
        (i.precise_reason || '').toLowerCase().includes(q) ||
        (i.lesson || '').toLowerCase().includes(q)
      );
    }
  } else {
    filtered = (typeof EMBEDDED_ITEMS !== 'undefined') ? EMBEDDED_ITEMS : [];
    if (sheetKey !== 'master') {
      filtered = filtered.filter(i => (i.ats || '').toLowerCase().includes(sheetKey.toLowerCase()));
    }
    if (query) {
      const q = query.toLowerCase();
      filtered = filtered.filter(i => (i.name || '').toLowerCase().includes(q) || (i.slug || '').toLowerCase().includes(q));
    }
    title = sheetKey.toUpperCase() + " Portals";
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const curPage = Math.min(page, totalPages);
  const start = (curPage - 1) * limit;
  const end = start + limit;
  const slice = filtered.slice(start, end);

  const staticData = {
    sheet_key: sheetKey,
    sheet_title: title,
    sheet_subtitle: "Verified Tech Companies & Startups",
    kind: kind,
    total_in_sheet: total,
    total_filtered: total,
    page: curPage,
    limit: limit,
    total_pages: totalPages,
    has_next: curPage < totalPages,
    has_prev: curPage > 1,
    start_index: total === 0 ? 0 : start + 1,
    end_index: Math.min(end, total),
    items: slice
  };

  renderPortalTableHeader(kind);
  renderPortalTable(staticData);
  renderPortalPagination(staticData);
}

function renderPortalTable(data) {
  const tbody = document.getElementById("portalTableBody");
  if (!data.items || data.items.length === 0) {
    const filterInfo = CURRENT_MONTH ? ` for ${CURRENT_MONTH}` : "";
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 50px;">No records found matching "<strong>${escapeHtml(CURRENT_QUERY || CURRENT_MONTH)}</strong>"${filterInfo} in ${escapeHtml(data.sheet_title)}.</td></tr>`;
    return;
  }

  const kind = data.kind || (data.sheet_key === 'funded_startups' ? 'funded_startups' : (data.sheet_key === 'startup_failures' ? 'startup_failures' : 'standard'));

  if (kind === "funded_startups") {
    tbody.innerHTML = data.items.map((item, idx) => {
      const rowIndex = data.start_index + idx;
      const safeComp = escapeHtml(item.name);
      const safeJsName = safeComp.replace(/'/g, "\\'");
      const websiteUrl = item.website || item.google_jobs_url;
      const safeJsUrl = escapeHtml(websiteUrl).replace(/'/g, "\\'");
      
      const roundBadge = item.round ? `<span class="badge-round">${escapeHtml(item.round)}</span>` : "";
      const amountBadge = item.amount ? `<span class="badge-amount">${escapeHtml(item.amount)}</span>` : "";
      const sectorBadge = item.sector ? `<span class="badge-sector">${escapeHtml(item.sector)}</span>` : "";
      const locationText = item.country ? `<span class="badge-country"><i class="fa-solid fa-location-dot" style="font-size: 0.68rem;"></i> ${escapeHtml(item.country)}</span>` : "";

      const websiteBtn = item.website ? `
        <a class="ext-link" href="${escapeHtml(item.website)}" target="_blank" rel="noopener noreferrer" style="margin-right: 4px;">
          <span>Website</span> <i class="fa fa-arrow-up-right-from-square" style="font-size: 0.68rem;"></i>
        </a>
      ` : "";

      return `
        <tr>
          <td style="color: var(--text-muted); font-size: 0.78rem; font-family: monospace;">${rowIndex}</td>
          <td>
            <div style="font-weight: 600; color: var(--text-primary); font-size: 0.94rem;">${safeComp}</div>
            <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 3px;">
              ${sectorBadge}
              ${locationText}
            </div>
          </td>
          <td>
            <div style="display: flex; align-items: center; gap: 4px;">
              ${roundBadge}
              ${amountBadge}
            </div>
            ${item.valuation && item.valuation !== 'N/D' ? `<div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 3px;">Val: ${escapeHtml(item.valuation)}</div>` : ''}
          </td>
          <td>
            <div style="font-size: 0.83rem; line-height: 1.45; color: var(--text-primary); max-width: 320px;">
              ${escapeHtml(item.what_they_build || 'High-growth technology startup.')}
            </div>
          </td>
          <td>
            <div style="font-weight: 600; font-size: 0.82rem; color: var(--text-primary);"><i class="fa fa-calendar-check" style="color: var(--accent-emerald); font-size: 0.75rem;"></i> ${escapeHtml(item.month || item.announced_date)}</div>
            ${item.lead_investors ? `<div style="font-size: 0.74rem; color: var(--text-secondary); margin-top: 2px;">Lead: <strong>${escapeHtml(item.lead_investors)}</strong></div>` : ''}
          </td>
          <td style="white-space: nowrap;">
            ${websiteBtn}
            <a class="intel-link intel-levels" href="${escapeHtml(item.levels_url)}" target="_blank" rel="noopener noreferrer" title="View salaries on Levels.fyi">
              <i class="fa fa-chart-line"></i> Salaries
            </a>
            <a class="intel-link intel-glassdoor" href="${escapeHtml(item.glassdoor_url)}" target="_blank" rel="noopener noreferrer" title="View reviews on Glassdoor">
              <i class="fa fa-star"></i> Reviews
            </a>
          </td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-sm btn-primary" onclick="useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
              <i class="fa fa-wand-magic-sparkles"></i> Tailor CV
            </button>
          </td>
        </tr>
      `;
    }).join("");
    return;
  }

  if (kind === "startup_failures") {
    tbody.innerHTML = data.items.map((item, idx) => {
      const rowIndex = data.start_index + idx;
      const safeComp = escapeHtml(item.name);
      const safeJsName = safeComp.replace(/'/g, "\\'");
      const sectorBadge = item.sector ? `<span class="badge-sector" style="background: #FFF1F2; color: #BE123C; border-color: #FECDD3;">${escapeHtml(item.sector)}</span>` : "";
      const countryText = item.country ? `<span class="badge-country"><i class="fa-solid fa-location-dot" style="font-size: 0.68rem;"></i> ${escapeHtml(item.country)}</span>` : "";

      return `
        <tr>
          <td style="color: var(--text-muted); font-size: 0.78rem; font-family: monospace;">${rowIndex}</td>
          <td>
            <div style="font-weight: 600; color: #991B1B; font-size: 0.94rem;"><i class="fa fa-skull-crossbones" style="font-size: 0.8rem; opacity: 0.7;"></i> ${safeComp}</div>
            <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 3px;">
              ${sectorBadge}
              ${countryText}
            </div>
          </td>
          <td>
            <div class="badge-fail-funding">${escapeHtml(item.funding_before_failure || 'N/A')}</div>
          </td>
          <td>
            <div style="font-size: 0.76rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 3px;"><i class="fa fa-clock"></i> ${escapeHtml(item.when_date)}</div>
            <div style="font-size: 0.82rem; line-height: 1.4; color: var(--text-primary); max-width: 280px;">${escapeHtml(item.what_happened)}</div>
          </td>
          <td>
            <div style="font-size: 0.82rem; line-height: 1.4; color: #7F1D1D; background: #FEF2F2; padding: 6px 8px; border-radius: 6px; border: 1px solid #FEE2E2; max-width: 280px;">
              <strong>Risk Signal:</strong> ${escapeHtml(item.precise_reason)}
            </div>
          </td>
          <td>
            <div style="font-size: 0.8rem; line-height: 1.4; color: #1E3A8A; background: #EFF6FF; padding: 6px 8px; border-radius: 6px; border: 1px solid #DBEAFE; max-width: 260px;">
              <i class="fa fa-lightbulb" style="color: #F59E0B;"></i> ${escapeHtml(item.lesson)}
            </div>
          </td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-sm btn-secondary" onclick="useCompanyInStudio('${safeJsName}', '${escapeHtml(item.google_jobs_url).replace(/'/g, "\\\\'")}')">
              <i class="fa fa-file-pen"></i> Tailor / Track
            </button>
          </td>
        </tr>
      `;
    }).join("");
    return;
  }

  // Standard Sheet rendering (Master, Ashby, Greenhouse, Lever, Workday)
  tbody.innerHTML = data.items.map((item, idx) => {
    const ats = (item.ats || "").toLowerCase();
    let badgeClass = "badge-other";
    if (ats.includes("ashby")) badgeClass = "badge-ashby";
    if (ats.includes("greenhouse")) badgeClass = "badge-greenhouse";
    if (ats.includes("lever")) badgeClass = "badge-lever";
    if (ats.includes("workday")) badgeClass = "badge-workday";
    if (ats.includes("funded")) badgeClass = "badge-greenhouse";

    const jobsHtml = item.open_jobs 
      ? `<span style="font-weight: 600; color: #047857; font-size: 0.78rem;">${escapeHtml(item.open_jobs)}</span>`
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
  loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, CURRENT_MONTH);
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
    if (typeof EMBEDDED_BASE_TEX !== 'undefined') {
      document.getElementById("tailoredTexArea").value = EMBEDDED_BASE_TEX;
      document.getElementById("companyName").value = "Base Master CV";
      document.getElementById("jobTitle").value = "Software Development Engineer";
      document.getElementById("cvPreviewFrame").srcdoc = EMBEDDED_PREVIEW_HTML;
      document.getElementById("emptyState").style.display = "none";
      document.getElementById("outputContent").style.display = "block";
      document.getElementById("actionDownloadButtons").style.display = "flex";
      document.getElementById("scoreBadge").textContent = "Base Profile";
      document.getElementById("archetypeBadge").textContent = "Master Template";
      document.getElementById("prioritySkillsChips").innerHTML = '<span class="chip chip-skill"><i class="fa fa-code"></i> data/main.tex</span>';
      switchSubTab("preview");
      showToast("Base CV loaded in Studio!");
      return;
    }
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
      if (typeof EMBEDDED_BASE_TEX !== 'undefined') {
        simulateStaticTailor(company, title, jd);
        return true;
      }
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
    if (typeof EMBEDDED_BASE_TEX !== 'undefined') {
      simulateStaticTailor(company, title, jd);
      return true;
    }
    showToast("Request failed: " + e.message);
    return false;
  } finally {
    if (btnTailor) {
      btnTailor.disabled = false;
      btnTailor.innerHTML = origHtml;
    }
  }
}

function simulateStaticTailor(company, title, jd) {
  const jdLower = (jd || "").toLowerCase();
  const candidateSkills = ["Python", "Go", "TypeScript", "LangChain", "LangGraph", "RAG", "LLM APIs", "Docker", "Kubernetes", "PostgreSQL", "Redis", "FastAPI", "AWS", "REST APIs", "Microservices"];
  let matched = candidateSkills.filter(s => jdLower.includes(s.toLowerCase()));
  if (matched.length === 0) matched = ["Python", "LangChain", "REST APIs", "Docker", "PostgreSQL", "FastAPI"];

  const simScore = Math.min(98, Math.max(76, 70 + matched.length * 4));
  let simTex = (typeof EMBEDDED_BASE_TEX !== 'undefined') ? EMBEDDED_BASE_TEX : "";

  const simData = {
    success: true,
    company: company,
    job_title: title || "Software Engineer",
    tailored_tex: simTex,
    preview_html: (typeof EMBEDDED_PREVIEW_HTML !== 'undefined') ? EMBEDDED_PREVIEW_HTML : "",
    analysis: {
      match_score: simScore,
      archetype: jdLower.includes("ai") ? "ai_engineer" : "backend_engineer",
      top_priorities: matched.slice(0, 6),
      profile_summary: "AI-focused Software Development Engineer tailored for " + company
    },
    profile_diff: "--- Base Profile\\n+++ Tailored Profile\\n@@ -1,3 +1,3 @@\\n- AI-focused Software Development Engineer with 2.5 years experience\\n+ AI-focused Engineer tailored for " + company + ": specializing in " + matched.slice(0, 3).join(", "),
    skills_diff: "--- Base Technical Skills\\n+++ Tailored Skills\\n@@ -1,4 +1,4 @@\\n- AI/GenAI: LLMs, LangChain, RAG, Prompt Engineering\\n+ AI/GenAI: " + matched.join(", "),
    projects_diff: "--- Base Project Tech Stack\\n+++ Tailored Project Tech Stack\\n@@ -1,2 +1,2 @@\\n- VitaTrack.ai [Go, Python, FastAPI, PostgreSQL, AWS Bedrock]\\n+ VitaTrack.ai [Go, Python, " + matched.slice(0, 3).join(", ") + "]"
  };

  CURRENT_TAILORED_RESULT = simData;
  document.getElementById("emptyState").style.display = "none";
  document.getElementById("outputContent").style.display = "block";
  document.getElementById("actionDownloadButtons").style.display = "flex";
  document.getElementById("scoreBadge").textContent = `Match: ${simData.analysis.match_score}%`;
  document.getElementById("archetypeBadge").textContent = `Archetype: ${simData.analysis.archetype.replace('_', ' ')}`;
  document.getElementById("prioritySkillsChips").innerHTML = simData.analysis.top_priorities.map(s => `<span class="chip chip-skill">${s}</span>`).join("");
  document.getElementById("cvPreviewFrame").srcdoc = simData.preview_html;
  document.getElementById("tailoredTexArea").value = simData.tailored_tex;

  document.getElementById("diffViewContainer").innerHTML = `
    <div style="margin-bottom: 16px;">
      <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">PROFILE Changes</h4>
      <div class="diff-box">${renderDiffLines(simData.profile_diff)}</div>
    </div>
    <div style="margin-bottom: 16px;">
      <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">TECHNICAL SKILLS Changes</h4>
      <div class="diff-box">${renderDiffLines(simData.skills_diff)}</div>
    </div>
    <div>
      <h4 style="color: var(--accent-emerald); margin: 0 0 6px 0;">PROJECTS Changes</h4>
      <div class="diff-box">${renderDiffLines(simData.projects_diff)}</div>
    </div>
  `;

  showToast(`Tailored CV generated for ${company}! (GitHub Pages Interactive Demo)`);
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
    if (typeof EMBEDDED_BASE_TEX !== 'undefined') {
      downloadTex();
      alert(`Downloaded tailored LaTeX source (.tex)!

Note: To compile binary Overleaf PDFs directly via the embedded Tectonic XeTeX engine, run Applyfox locally or via Docker:

$ python3 cv_service.py serve`);
      return;
    }
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
            month = qs.get("month", [""])[0]

            data = get_sheet_page(sheet_key=sheet, page=page, limit=limit, query=q, month=month)
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


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Start web server."""
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, CVAppRequestHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"\n=======================================================")
    print(f" Applyfox CV Studio & Multi-Portal Sheets Engine")
    print(f" Access URL: http://{display_host}:{port}")
    if host == "0.0.0.0":
        print(f" Bound to 0.0.0.0 (Ready for Cloud & Docker deployment)")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server("0.0.0.0", int(os.getenv("PORT", "8080")))
