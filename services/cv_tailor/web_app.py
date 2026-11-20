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

from services.cv_tailor.directory import get_roles_page, get_sheet_page, get_sheets_summary
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
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#121210">
<link rel="icon" href="static/favicon.ico" sizes="48x48">
<link rel="icon" href="static/favicon.svg" type="image/svg+xml">
<link rel="icon" href="static/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="static/apple-touch-icon.png">
<link rel="manifest" href="static/site.webmanifest">
<script>
  /* Theme: dark by default (set on <html> above, so it applies even before
     this runs). A choice made with the toggle is stored and restored here,
     before first paint, so the page never flashes the wrong theme. */
  (function () {
    try {
      var saved = localStorage.getItem("applyfox-theme");
      if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
    } catch (e) {}
    syncThemeColor();
  })();
  function syncThemeColor() {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", currentTheme() === "dark" ? "#121210" : "#f3f2ee");
  }
  function currentTheme() {
    var set = document.documentElement.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function toggleTheme() {
    var next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("applyfox-theme", next); } catch (e) {}
    syncThemeColor();
    var btn = document.getElementById("themeToggle");
    if (btn) btn.setAttribute("aria-label", next === "dark" ? "Switch to light theme" : "Switch to dark theme");
  }
</script>
<title>Applyfox &mdash; Career Studio</title>
<link rel="preconnect" href="https://api.fontshare.com">
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=zodiak@400,401,500&f[]=switzer@400,500,600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
/*__APP_CSS__*/
</style>
</head>
<body>

  <header class="app-header">
    <div class="header-inner">
      <button type="button" class="brand" onclick="switchView('home')" title="Applyfox home" aria-label="Applyfox home"><svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><defs><mask id="af-cut-header"><rect width="32" height="32" fill="#fff"/><path d="M10.5 17 L14.5 21 L22 13.5" fill="none" stroke="#000" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></mask></defs><path d="M5 4.5 L12.5 11 H19.5 L27 4.5 V17 L16 28 L5 17 Z" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" mask="url(#af-cut-header)"/></svg><span>Apply<em>fox</em></span></button>

      <div class="header-nav-container">
        <nav class="nav-tabs" aria-label="Main navigation">
          <button class="tab-btn active" id="navBtn-home" onclick="switchView('home')">Overview</button>
          <button class="tab-btn" id="navBtn-tailor" onclick="switchView('tailor')">CV Studio</button>
          <button class="tab-btn" id="navBtn-startups" onclick="openStartupsView()">Startups <span class="tab-count">480</span></button>
          <button class="tab-btn" id="navBtn-portals" onclick="openPortalsView()">Directory <span class="tab-count">7,406</span></button>
          <button class="tab-btn" id="navBtn-tracker" onclick="switchView('tracker')">Tracker <span class="tab-count" id="appCount">0</span></button>
          <button class="tab-btn" id="navBtn-base-cv" onclick="switchView('base-cv')">Base CV</button>
        </nav>
      </div>

      <div class="header-actions">
        <nav class="header-links" aria-label="Elsewhere">
          <a href="https://harshdotcom.github.io/AI-Systems/" target="_blank" rel="noopener" title="The Central Library — free books on building systems">Library <span aria-hidden="true">&nearr;</span></a>
          <a href="https://harshdotcom.github.io/AI-Systems/harsh-jha.html" target="_blank" rel="noopener me" title="About Harsh Jha">About <span aria-hidden="true">&nearr;</span></a>
        </nav>
        <button type="button" id="themeToggle" class="icon-btn theme-toggle" onclick="toggleTheme()" title="Toggle light / dark" aria-label="Toggle light / dark theme">
          <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>
          <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        </button>
        <a href="https://github.com/harshdotcom/Applyfox" target="_blank" rel="noopener noreferrer" class="icon-btn" title="Applyfox on GitHub" aria-label="Applyfox on GitHub">
          <i class="fa-brands fa-github"></i>
        </a>
      </div>
    </div>
  </header>

  <main>
    <!-- ========================================== -->
    <!-- VIEW 0: HOME                               -->
    <!-- ========================================== -->
    <div id="view-home">

      <section class="hero-section">
        <span class="eyebrow">Open-source career studio &middot; 37,193 verified roles</span>
        <h1 class="hero-title">Find the role. Tailor the CV. <em>Track every application.</em></h1>
        <p class="hero-subtitle">
          Applyfox indexes open positions straight from official career boards across engineering, design, IT, legal and operations &mdash; then typesets a LaTeX CV aligned to the job description you paste in.
        </p>

        <div class="hero-search-wrapper">
          <div class="hero-search-bar">
            <div class="hero-search-field">
              <i class="fa fa-magnifying-glass"></i>
              <input type="text" id="homeSearchInput" placeholder="Search roles, e.g. Product Designer" onkeydown="if(event.key === 'Enter') executeHomeSearch()">
            </div>
            <div class="hero-search-filter">
              <select id="homeSearchDiscipline" aria-label="Discipline">
                <option value="">All disciplines</option>
                <option value="Software & AI">Software &amp; AI</option>
                <option value="Graphic & UI/UX">Design &amp; UI/UX</option>
                <option value="IT & Cloud">IT &amp; Cloud</option>
                <option value="Legal & Compliance">Legal &amp; Compliance</option>
                <option value="Product & Operations">Product &amp; Ops</option>
              </select>
            </div>
            <button class="btn btn-primary hero-search-btn" onclick="executeHomeSearch()">Search roles</button>
          </div>
          <div class="hero-trending-chips">
            <span class="hero-trending-label">Popular</span>
            <button class="hero-trending-chip" onclick="quickJumpSearch('Legal')">Legal &amp; Compliance</button>
            <button class="hero-trending-chip" onclick="quickJumpSearch('UI UX')">UI/UX Designer</button>
            <button class="hero-trending-chip" onclick="quickJumpSearch('Full Stack')">Full Stack</button>
            <button class="hero-trending-chip" onclick="quickJumpSearch('IT Cloud')">IT &amp; Cloud</button>
            <button class="hero-trending-chip" onclick="quickJumpSearch('Product')">Product</button>
            <button class="hero-trending-chip" onclick="quickJumpSearch('Remote')">Remote</button>
          </div>
        </div>

        <div class="hero-actions">
          <button class="btn btn-primary btn-lg" onclick="switchView('tailor')">Open CV Studio</button>
          <button class="arrow-link" onclick="openStartupsView()">Explore 2026 funded startups <span aria-hidden="true">&rarr;</span></button>
        </div>
      </section>

      <div class="stats-strip">
        <button class="stat-item" onclick="openRolesFeedView()" title="Browse all open positions">
          <div class="stat-num">37,193</div>
          <div class="stat-label">Open positions</div>
        </button>
        <button class="stat-item" onclick="openPortalsView()" title="Browse the company directory">
          <div class="stat-num">7,406</div>
          <div class="stat-label">Verified career boards</div>
        </button>
        <button class="stat-item" onclick="openStartupsView()" title="Startups funded in 2026">
          <div class="stat-num">480</div>
          <div class="stat-label">Startups funded in 2026</div>
        </button>
        <button class="stat-item" onclick="openFailuresView()" title="Startup failure post-mortems">
          <div class="stat-num">23</div>
          <div class="stat-label">Failure post-mortems</div>
        </button>
      </div>

      <!-- 01 · How it works -->
      <section class="home-section">
        <div class="section-aside">
          <span class="section-index">01</span>
          <h2 class="section-title">How it works</h2>
          <p class="section-desc">From a job posting to a sent application in three steps.</p>
        </div>
        <div class="steps">
          <div class="step">
            <span class="step-num">01</span>
            <h3 class="step-title">Discover</h3>
            <p class="step-text">Search live roles indexed directly from Ashby, Greenhouse, Lever and Workday boards &mdash; no aggregators, no stale reposts.</p>
          </div>
          <div class="step">
            <span class="step-num">02</span>
            <h3 class="step-title">Tailor</h3>
            <p class="step-text">Paste the job description. Your profile, skills and project headers are re-aligned to its terminology without inventing experience.</p>
          </div>
          <div class="step">
            <span class="step-num">03</span>
            <h3 class="step-title">Apply &amp; track</h3>
            <p class="step-text">Compile a one-page LaTeX PDF, draft a note to the hiring manager, and archive the exact version you sent.</p>
          </div>
        </div>
      </section>

      <!-- 02 · Disciplines -->
      <section class="home-section">
        <div class="section-aside">
          <span class="section-index">02</span>
          <h2 class="section-title">Every discipline</h2>
          <p class="section-desc">Roles are classified across five fields. Pick one to open the filtered feed.</p>
        </div>
        <div class="discipline-index">
          <button class="discipline-row" onclick="searchByRole('Software &amp; AI')">
            <span class="discipline-name">Software &amp; AI</span>
            <span class="discipline-focus">Full stack, backend, ML, cloud infrastructure</span>
            <span class="discipline-pay">$165k&ndash;240k</span>
            <span class="discipline-go" aria-hidden="true">&rarr;</span>
          </button>
          <button class="discipline-row" onclick="searchByRole('Graphic &amp; UI/UX')">
            <span class="discipline-name">Design &amp; UI/UX</span>
            <span class="discipline-focus">Product design, brand identity, design systems</span>
            <span class="discipline-pay">$130k&ndash;185k</span>
            <span class="discipline-go" aria-hidden="true">&rarr;</span>
          </button>
          <button class="discipline-row" onclick="searchByRole('IT &amp; Cloud')">
            <span class="discipline-name">IT, Cloud &amp; Security</span>
            <span class="discipline-focus">DevOps, SRE, systems administration, InfoSec</span>
            <span class="discipline-pay">$140k&ndash;210k</span>
            <span class="discipline-go" aria-hidden="true">&rarr;</span>
          </button>
          <button class="discipline-row" onclick="searchByRole('Legal &amp; Compliance')">
            <span class="discipline-name">Legal &amp; Compliance</span>
            <span class="discipline-focus">In-house counsel, commercial contracts, privacy</span>
            <span class="discipline-pay">$185k&ndash;275k</span>
            <span class="discipline-go" aria-hidden="true">&rarr;</span>
          </button>
          <button class="discipline-row" onclick="searchByRole('Product &amp; Operations')">
            <span class="discipline-name">Product &amp; Operations</span>
            <span class="discipline-focus">Product management, TPM, BizOps, growth</span>
            <span class="discipline-pay">$145k&ndash;220k</span>
            <span class="discipline-go" aria-hidden="true">&rarr;</span>
          </button>
        </div>
      </section>

      <!-- 03 · What's inside -->
      <section class="home-section">
        <div class="section-aside">
          <span class="section-index">03</span>
          <h2 class="section-title">What&rsquo;s inside</h2>
          <p class="section-desc">Local-first. Your CVs and applications never leave your machine.</p>
        </div>
        <div class="feature-list">
          <button class="feature-item" onclick="switchView('tailor')">
            <div class="feature-title">LaTeX engine <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">An embedded Tectonic XeTeX compiler produces real PDFs with clean typography and working links.</p>
          </button>
          <button class="feature-item" onclick="switchView('tailor')">
            <div class="feature-title">JD-aware tailoring <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">Section-level diffs show exactly what changed in your profile, skills and projects.</p>
          </button>
          <button class="feature-item" onclick="openStartupsView()">
            <div class="feature-title">Funding &amp; risk intelligence <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">480 startups that raised in 2026, month by month, alongside 23 failure post-mortems.</p>
          </button>
          <button class="feature-item" onclick="openPortalsView()">
            <div class="feature-title">Company directory <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">7,406 career boards with salary and review links for every company.</p>
          </button>
          <button class="feature-item" onclick="switchView('tracker')">
            <div class="feature-title">Application tracker <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">Every application is logged with the exact .tex and .pdf you sent.</p>
          </button>
          <button class="feature-item" onclick="switchView('tailor')">
            <div class="feature-title">Outreach drafts <span aria-hidden="true">&rarr;</span></div>
            <p class="feature-text">Cold email, LinkedIn and recruiter notes written for the specific company and role.</p>
          </button>
        </div>
      </section>

      <!-- 04 · Further reading -->
      <section class="home-section">
        <div class="section-aside">
          <span class="section-index">04</span>
          <h2 class="section-title">Further reading</h2>
          <p class="section-desc">More from the author of Applyfox.</p>
        </div>
        <div class="discipline-index">
          <a class="discipline-row" href="https://harshdotcom.github.io/AI-Systems/" target="_blank" rel="noopener">
            <span class="discipline-name">The Central Library</span>
            <span class="discipline-focus">Seventeen free books on AI engineering, backends, cloud and distributed systems</span>
            <span class="discipline-pay">3,000 chapters</span>
            <span class="discipline-go" aria-hidden="true">&nearr;</span>
          </a>
          <a class="discipline-row" href="https://harshdotcom.github.io/AI-Systems/harsh-jha.html" target="_blank" rel="noopener me">
            <span class="discipline-name">About Harsh Jha</span>
            <span class="discipline-focus">Experience, projects and reading across generative AI and backend engineering</span>
            <span class="discipline-pay">Profile</span>
            <span class="discipline-go" aria-hidden="true">&nearr;</span>
          </a>
        </div>
      </section>

      <div class="cta-banner">
        <h2 class="cta-title">Your next application, <em>properly typeset.</em></h2>
        <div class="cta-actions">
          <button class="btn btn-primary btn-lg" onclick="switchView('tailor')">Open CV Studio</button>
          <button class="btn btn-secondary btn-lg" onclick="openRolesFeedView()">Browse open roles</button>
        </div>
      </div>

      <footer class="app-footer">
        <div class="footer-inner">
          <div>
            <div class="footer-brand"><svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><defs><mask id="af-cut-footer"><rect width="32" height="32" fill="#fff"/><path d="M10.5 17 L14.5 21 L22 13.5" fill="none" stroke="#000" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></mask></defs><path d="M5 4.5 L12.5 11 H19.5 L27 4.5 V17 L16 28 L5 17 Z" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" mask="url(#af-cut-footer)"/></svg><span>Applyfox</span></div>
            <p class="footer-desc">An open-source, local-first career studio for engineers, designers, IT specialists, lawyers and operators. Contributions welcome on <a href="https://github.com/harshdotcom/Applyfox" target="_blank" rel="noopener noreferrer">GitHub</a>.</p>
          </div>

          <div>
            <div class="footer-heading">Workspace</div>
            <ul class="footer-links">
              <li><a href="#" onclick="switchView('tailor'); return false;">CV Studio</a></li>
              <li><a href="#" onclick="switchView('tracker'); return false;">Application tracker</a></li>
              <li><a href="#" onclick="switchView('base-cv'); return false;">Base CV source</a></li>
              <li><a href="#" onclick="openRolesFeedView(); return false;">Open roles feed</a></li>
            </ul>
          </div>

          <div>
            <div class="footer-heading">Directory</div>
            <ul class="footer-links">
              <li><a href="#" onclick="openStartupsView(); return false;">Funded startups <span class="count">480</span></a></li>
              <li><a href="#" onclick="openFailuresView(); return false;">Failures &amp; distress <span class="count">23</span></a></li>
              <li><a href="#" onclick="openAtsSheet('ashby'); return false;">Ashby <span class="count">3,212</span></a></li>
              <li><a href="#" onclick="openAtsSheet('greenhouse'); return false;">Greenhouse <span class="count">1,894</span></a></li>
              <li><a href="#" onclick="openAtsSheet('lever'); return false;">Lever <span class="count">1,522</span></a></li>
            </ul>
          </div>

          <div>
            <div class="footer-heading">Made by</div>
            <a class="creator-name" href="https://harshdotcom.github.io/AI-Systems/harsh-jha.html" target="_blank" rel="noopener me">Harsh Jha</a>
            <div class="creator-title">AI Lead &middot; Formee Holdings</div>
            <ul class="footer-links">
              <li><a href="https://harshdotcom.github.io/AI-Systems/harsh-jha.html" target="_blank" rel="noopener me">About &nearr;</a></li>
              <li><a href="https://harshdotcom.github.io/AI-Systems/" target="_blank" rel="noopener">The Central Library &nearr;</a></li>
              <li><a href="https://www.linkedin.com/in/harshjha-iiti/" target="_blank" rel="noopener noreferrer">LinkedIn &nearr;</a></li>
              <li><a href="https://github.com/jhaharsh03" target="_blank" rel="noopener noreferrer">GitHub &nearr;</a></li>
              <li><a href="https://www.instagram.com/jhaharsh03/" target="_blank" rel="noopener noreferrer">Instagram &nearr;</a></li>
            </ul>
          </div>
        </div>

        <div class="footer-bottom">
          <span>&copy; 2026 Applyfox &middot; MIT License</span>
          <span>Runs locally &middot; Tectonic XeTeX</span>
        </div>
      </footer>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 1: CV STUDIO                          -->
    <!-- ========================================== -->
    <div id="view-tailor" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <span class="eyebrow"><a href="#" onclick="switchView('home'); return false;">Applyfox</a> / Studio</span>
          <h1 class="workspace-title">CV Studio</h1>
        </div>
        <div class="workspace-meta">
          <span class="meta-item">Harsh Jha &middot; IIT Indore</span>
          <span class="meta-item"><span class="sync-dot"></span> Tectonic XeTeX ready</span>
        </div>
      </div>

      <div class="tailor-layout">
        <!-- Left: job details -->
        <div class="card">
          <div class="card-header">
            <div class="card-title">Job details</div>
            <span class="card-kicker">Step 1 of 2</span>
          </div>

          <form id="tailorForm" onsubmit="event.preventDefault(); handleTailor();">
            <div class="form-group">
              <label for="companyName">Company</label>
              <input type="text" id="companyName" placeholder="e.g. Stripe, OpenAI, Notion" list="companyList" required>
              <datalist id="companyList"></datalist>
            </div>

            <div class="form-group">
              <label for="jobTitle">Role</label>
              <input type="text" id="jobTitle" placeholder="e.g. Senior Software Engineer">
              <div class="role-presets">
                <button type="button" class="role-quick-btn" onclick="setRolePreset('Senior Software & AI Engineer')">Software / AI</button>
                <button type="button" class="role-quick-btn" onclick="setRolePreset('Senior Graphic & UI/UX Designer')">Design</button>
                <button type="button" class="role-quick-btn" onclick="setRolePreset('IT Systems & Cloud Infrastructure Specialist')">IT &amp; Cloud</button>
                <button type="button" class="role-quick-btn" onclick="setRolePreset('Corporate Legal Counsel & Compliance')">Legal</button>
                <button type="button" class="role-quick-btn" onclick="setRolePreset('Technical Product Manager')">Product</button>
              </div>
            </div>

            <div class="form-group">
              <label for="jobUrl">Posting URL</label>
              <input type="text" id="jobUrl" placeholder="https://jobs.ashbyhq.com/&hellip;">
            </div>

            <div class="referral-box">
              <label class="checkbox-label">
                <input type="checkbox" id="hasReferral" onchange="toggleReferralFields()">
                <span>I have an employee referral</span>
              </label>
              <div id="referralFields" style="display: none; margin-top: 14px;">
                <div class="form-row">
                  <div class="form-group" style="margin-bottom: 0;">
                    <label for="referralName">Referrer name</label>
                    <input type="text" id="referralName" placeholder="Alex Doe">
                  </div>
                  <div class="form-group" style="margin-bottom: 0;">
                    <label for="referralContact">Email or LinkedIn</label>
                    <input type="text" id="referralContact" placeholder="alex@company.com">
                  </div>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label for="jdText">Job description</label>
              <textarea id="jdText" placeholder="Paste the requirements, responsibilities and stack&hellip;" required></textarea>
            </div>

            <div class="form-group">
              <label for="appNotes">Notes <span style="text-transform: none; letter-spacing: 0; color: var(--ink-faint);">(optional)</span></label>
              <input type="text" id="appNotes" placeholder="e.g. Messaged recruiter on LinkedIn">
            </div>

            <div class="banner-actions">
              <button type="button" id="btnTailor" class="btn btn-primary" style="flex: 1;" onclick="handleTailor()">Tailor CV</button>
              <button type="button" id="btnSaveApp" class="btn btn-secondary" style="flex: 1;" onclick="handleSaveApplication()">Save to tracker</button>
            </div>
          </form>
        </div>

        <!-- Right: output -->
        <div class="card" id="resultsCard" style="min-height: 600px;">
          <div class="card-header">
            <div class="card-title">Preview</div>
            <div id="actionDownloadButtons" style="display: none; gap: 8px; flex-wrap: wrap;">
              <button id="btnDownloadPdf" class="btn btn-primary btn-sm" onclick="downloadPdf()">Download PDF</button>
              <button class="btn btn-secondary btn-sm" onclick="recompilePdf()">Recompile</button>
              <button class="btn btn-secondary btn-sm" onclick="downloadTex()">.tex</button>
              <button class="btn btn-secondary btn-sm" onclick="copyTex()">Copy</button>
            </div>
          </div>

          <div id="emptyState" class="empty-state">
            <h3>Nothing tailored yet</h3>
            <p>Add a company and paste a job description, then choose <em>Tailor CV</em>. You can also pick a company from the Directory.</p>
            <button class="btn btn-secondary btn-sm" onclick="loadBaseCvInStudio()">Preview base CV</button>
          </div>

          <div id="outputContent" style="display: none;">
            <div class="meta-chips">
              <span class="chip chip-score" id="scoreBadge">Match: 0%</span>
              <span class="chip chip-archetype" id="archetypeBadge">Archetype: -</span>
              <span id="prioritySkillsChips" style="display: flex; gap: 6px; flex-wrap: wrap;"></span>
            </div>

            <div class="results-tabs" style="margin-bottom: 18px;">
              <button class="subtab-btn active" id="subtabBtn-preview" onclick="switchSubTab('preview')">Paper</button>
              <button class="subtab-btn" id="subtabBtn-pdf" onclick="switchSubTab('pdf')">PDF</button>
              <button class="subtab-btn" id="subtabBtn-diff" onclick="switchSubTab('diff')">Changes</button>
              <button class="subtab-btn" id="subtabBtn-tex" onclick="switchSubTab('tex')">LaTeX</button>
              <button class="subtab-btn" id="subtabBtn-outreach" onclick="switchSubTab('outreach')">Outreach</button>
            </div>

            <div id="subtab-preview" class="preview-frame-container">
              <iframe id="cvPreviewFrame" class="preview-frame"></iframe>
            </div>

            <div id="subtab-pdf" style="display: none; height: 780px; overflow: hidden;">
              <iframe id="pdfPreviewFrame" style="width: 100%; height: 100%; border: none;"></iframe>
            </div>

            <div id="subtab-diff" style="display: none;">
              <div id="diffViewContainer"></div>
            </div>

            <div id="subtab-tex" style="display: none;">
              <div style="margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
                <span class="hint">Edit the source directly, then recompile to refresh both previews.</span>
                <button class="btn btn-primary btn-sm" onclick="recompilePdf()">Recompile</button>
              </div>
              <textarea id="tailoredTexArea" class="tex-code" style="height: 650px;"></textarea>
            </div>

            <div id="subtab-outreach" style="display: none;">
              <div class="notice">
                <strong>Outreach drafts</strong>
                A short, specific note to the hiring lead usually outperforms a portal application on its own. These drafts are written for the company and role above.
              </div>
              <div id="outreachContentContainer">
                <div class="hint" style="text-align: center; padding: 40px;">Tailor a CV or choose a company to generate drafts.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 2: DIRECTORY & STARTUPS               -->
    <!-- ========================================== -->
    <div id="view-portals" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <span class="eyebrow"><a href="#" onclick="switchView('home'); return false;">Applyfox</a> / Directory</span>
          <h1 class="workspace-title">Companies &amp; open roles</h1>
        </div>
        <div class="workspace-meta">
          <button class="sync-badge" onclick="openSystemStatusModal()" title="Sync schedule and data freshness">
            <span class="sync-dot"></span>
            <span>Synced weekly &middot; Sundays 00:00 UTC</span>
          </button>
        </div>
      </div>

      <nav class="dir-tabs" id="directoryTabs" role="tablist" aria-label="Directory sections">
        <button class="dir-tab" role="tab" data-tab="startups" onclick="selectDirectoryTab('startups')">Startups <span class="dir-count" data-count="funded_startups">480</span></button>
        <button class="dir-tab" role="tab" data-tab="failures" onclick="selectDirectoryTab('failures')">Failures <span class="dir-count" data-count="startup_failures">23</span></button>
        <button class="dir-tab" role="tab" data-tab="companies" onclick="selectDirectoryTab('companies')">Companies <span class="dir-count" data-count="master">7,406</span></button>
        <button class="dir-tab" role="tab" data-tab="roles" onclick="selectDirectoryTab('roles')">Open roles <span class="dir-count">37,193</span></button>
      </nav>

      <div class="filter-bar">
        <div class="search-wrapper">
          <i class="fa fa-magnifying-glass"></i>
          <input type="text" id="portalSearch" class="search-input" placeholder="Search" aria-label="Search" oninput="onPortalSearchInput(this.value)">
        </div>
        <div class="filter-selects">
          <select id="portalRoleSelect" class="filter-select" onchange="filterByRole(this.value)" aria-label="Role">
            <option value="">Any role</option>
            <optgroup label="Software &amp; AI Engineering">
                <option value="Software &amp; AI">All Software &amp; AI Roles</option>
                <option value="Senior Full Stack Engineer">Senior Full Stack Engineer</option>
                <option value="Senior Backend Engineer">Senior Backend Engineer</option>
                <option value="AI &amp; Machine Learning Engineer">AI &amp; Machine Learning Engineer</option>
                <option value="Senior AI Research Engineer">Senior AI Research Engineer</option>
                <option value="Frontend Systems Engineer">Frontend Systems Engineer</option>
                <option value="Staff Cloud &amp; DevOps Engineer">Staff Cloud &amp; DevOps Engineer</option>
                <option value="Mobile Engineer">Mobile Engineer</option>
            </optgroup>
            <optgroup label="Graphic &amp; UI/UX Design">
                <option value="Graphic &amp; UI/UX">All Design &amp; Creative Roles</option>
                <option value="Senior Product Designer">Senior Product Designer (UI/UX)</option>
                <option value="Graphic &amp; Brand Identity Designer">Graphic &amp; Brand Designer</option>
                <option value="Lead UI/UX Designer">Lead UI/UX Designer</option>
                <option value="Visual &amp; Marketing Content Designer">Visual &amp; Marketing Designer</option>
                <option value="Design Systems Specialist">Design Systems Specialist</option>
            </optgroup>
            <optgroup label="IT &amp; Cloud Systems">
                <option value="IT &amp; Cloud">All IT &amp; Cloud Roles</option>
                <option value="IT Systems Administrator">IT Systems Administrator</option>
                <option value="Cloud Infrastructure &amp; SRE">Cloud Infrastructure &amp; SRE</option>
                <option value="Enterprise IT &amp; Network Security">Enterprise IT &amp; Security</option>
                <option value="Corporate IT Support Specialist">Corporate IT Support</option>
            </optgroup>
            <optgroup label="Legal &amp; Compliance">
                <option value="Legal &amp; Compliance">All Legal &amp; Compliance Roles</option>
                <option value="Corporate Legal Counsel">Corporate Legal Counsel</option>
                <option value="Commercial Contracts &amp; Licensing">Commercial Contracts Manager</option>
                <option value="Regulatory &amp; Privacy Compliance">Regulatory &amp; Privacy Compliance</option>
                <option value="Intellectual Property &amp; Technology Counsel">IP &amp; Technology Counsel</option>
            </optgroup>
            <optgroup label="Product &amp; Operations">
                <option value="Product &amp; Operations">All Product &amp; Ops Roles</option>
                <option value="Senior Technical Product Manager">Senior Technical Product Manager</option>
                <option value="Product Operations &amp; Strategy Lead">Product Operations Lead</option>
                <option value="BizOps &amp; Growth Operations Associate">BizOps &amp; Strategy Lead</option>
            </optgroup>
          </select>
          <select id="portalLevelSelect" class="filter-select" onchange="onPortalLevelChange(this.value)" aria-label="Seniority">
            <option value="">Any seniority</option>
            <option value="Entry">Entry / Junior</option>
            <option value="Mid">Mid-level</option>
            <option value="Senior">Senior</option>
            <option value="Lead">Lead / Staff</option>
            <option value="Director">Executive</option>
          </select>
          <select id="portalModeSelect" class="filter-select" onchange="filterByWorkMode(this.value)" aria-label="Work mode">
            <option value="">Any work mode</option>
            <option value="Remote">Remote</option>
            <option value="Hybrid">Hybrid</option>
            <option value="Onsite">Onsite</option>
          </select>
          <select id="portalMonthSelect" class="filter-select" onchange="filterByMonth(this.value)" aria-label="Funding month" hidden>
            <option value="">Any month</option>
          </select>
          <select id="portalAtsSelect" class="filter-select" onchange="switchPortalSheet(this.value)" aria-label="Applicant tracking system" hidden>
            <option value="master">All ATS</option>
            <option value="ashby">Ashby</option>
            <option value="greenhouse">Greenhouse</option>
            <option value="lever">Lever</option>
            <option value="workday">Workday</option>
          </select>
          <button type="button" class="filter-clear" id="filterClear" onclick="clearAllFilters()" hidden>Clear</button>
        </div>
      </div>

      <div class="table-container">
        <table class="sheet-table" id="portalTable">
          <thead>
            <tr>
              <th style="width: 50px;">#</th>
              <th>Company</th>
              <th>ATS</th>
              <th>Open roles</th>
              <th>Careers</th>
              <th>Research</th>
              <th style="text-align: right;"></th>
            </tr>
          </thead>
          <tbody id="portalTableBody">
            <tr>
              <td colspan="7" style="text-align: center; padding: 40px;">Loading&hellip;</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pagination-bar" id="portalPaginationBar">
        <div class="page-info" id="portalPageInfo">Showing 0 of 0</div>
        <div class="pagination-right">
          <select id="portalLimitSelect" class="filter-select filter-select-sm" onchange="onPortalLimitChange(this.value)" aria-label="Rows per page">
            <option value="25" selected>25 per page</option>
            <option value="50">50 per page</option>
            <option value="100">100 per page</option>
          </select>
          <div class="page-nav" id="portalPageNav"></div>
        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 3: APPLICATION TRACKER                -->
    <!-- ========================================== -->
    <div id="view-tracker" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <span class="eyebrow"><a href="#" onclick="switchView('home'); return false;">Applyfox</a> / Tracker</span>
          <h1 class="workspace-title">Applications</h1>
        </div>
        <div class="workspace-meta">
          <input type="text" id="trackerSearch" placeholder="Search company or title" oninput="filterTrackerTable()" style="width: 240px; height: 34px;">
          <a href="/api/export_csv" class="btn btn-secondary btn-sm">Export CSV</a>
        </div>
      </div>

      <div class="table-container">
        <table class="sheet-table" id="trackerTable">
          <thead>
            <tr>
              <th>Applied</th>
              <th>Company</th>
              <th>Role</th>
              <th>Status</th>
              <th>Referral</th>
              <th>Match</th>
              <th>Key skills</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="trackerTableBody">
            <tr><td colspan="8" style="text-align: center; padding: 40px;">No applications tracked yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 4: BASE CV SOURCE                     -->
    <!-- ========================================== -->
    <div id="view-base-cv" style="display: none;">
      <div class="workspace-bar">
        <div class="workspace-breadcrumb">
          <span class="eyebrow"><a href="#" onclick="switchView('home'); return false;">Applyfox</a> / Base CV</span>
          <h1 class="workspace-title">main.tex</h1>
        </div>
        <div class="workspace-meta">
          <span class="meta-item mono">data/main.tex &middot; read-only</span>
        </div>
      </div>

      <textarea id="baseTexContent" class="tex-code" style="height: 750px;" readonly></textarea>
    </div>
  </main>

  <div id="toast" class="toast"></div>

  <!-- Company Profile Dossier Modal ("Company Page") -->
  <div id="companyModalOverlay" class="modal-overlay" onclick="if(event.target === this) closeCompanyModal()">
    <div class="modal-card">
      <button class="modal-close-btn" onclick="closeCompanyModal()" title="Close">&times;</button>
      <div id="companyModalBody"></div>
    </div>
  </div>

<script>
/*__SELECT_JS__*/
</script>
<script>
/* GITHUB_PAGES_EMBEDDED_DATA */
let CURRENT_TAILORED_RESULT = null;
let TRACKED_APPLICATIONS = [];
let CURRENT_PDF_PREVIEW_URL = "";

// Directory Sheets & Roles Feed State
let CURRENT_DIRECTORY_MODE = "companies"; // "companies" | "roles"
let CURRENT_SHEET_KEY = "funded_startups";
let CURRENT_PAGE = 1;
let CURRENT_LIMIT = 25;
let CURRENT_QUERY = "";
let CURRENT_MONTH = "";
let CURRENT_ROLE = "";
let CURRENT_WORK_MODE = "";
let CURRENT_LEVEL = "";
let SEARCH_DEBOUNCE_TIMER = null;
let PORTAL_SUMMARIES = [];
let CURRENT_OUTREACH_TEMPLATES = null;

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
    const activeTabId = (CURRENT_DIRECTORY_MODE !== 'roles' && (CURRENT_SHEET_KEY === 'funded_startups' || CURRENT_SHEET_KEY === 'startup_failures')) ? 'navBtn-startups' : 'navBtn-portals';
    const btn = document.getElementById(activeTabId) || document.getElementById("navBtn-portals");
    if (btn) btn.classList.add("active");
    refreshDirectoryView();
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

function openStartupsView() { setDirectoryTab('startups'); switchView('portals'); }
function openFailuresView() { setDirectoryTab('failures'); switchView('portals'); }
function openPortalsView()  { setDirectoryTab('companies'); CURRENT_SHEET_KEY = 'master'; switchView('portals'); }
function openRolesFeedView() { setDirectoryTab('roles'); switchView('portals'); }
function openAtsSheet(key)  { setDirectoryTab('companies'); CURRENT_SHEET_KEY = key; switchView('portals'); }

function executeHomeSearch() {
  const query = (document.getElementById("homeSearchInput")?.value || "").trim();
  const discipline = (document.getElementById("homeSearchDiscipline")?.value || "").trim();
  
  CURRENT_QUERY = query;
  CURRENT_ROLE = discipline;
  setDirectoryTab('roles');
  switchView('portals');
  
  const msg = query ? `Showing live openings matching "${query}"` : "Viewing 37,000+ open roles";
  showToast(msg);
}

function quickJumpSearch(term) {
  const input = document.getElementById("homeSearchInput");
  if (input) input.value = term;
  executeHomeSearch();
}

function searchByRole(discipline) {
  CURRENT_ROLE = discipline;
  setDirectoryTab('roles');
  switchView('portals');
}

function filterByRole(role)       { CURRENT_ROLE = role || "";      CURRENT_PAGE = 1; refreshDirectoryView(); }
function onPortalRoleChange(val)   { filterByRole(val); }
function filterByWorkMode(mode)    { CURRENT_WORK_MODE = mode || ""; CURRENT_PAGE = 1; refreshDirectoryView(); }
function onPortalLevelChange(val)  { CURRENT_LEVEL = val || "";      CURRENT_PAGE = 1; refreshDirectoryView(); }

function setRolePreset(title) {
  const input = document.getElementById("jobTitle");
  if (input) {
    input.value = title;
    input.focus();
    showToast(`Role selected: ${title}`);
  }
}

// Subtabs in CV Studio
function switchSubTab(subTabName) {
  document.getElementById("subtab-preview").style.display = (subTabName === 'preview') ? 'block' : 'none';
  document.getElementById("subtab-pdf").style.display = (subTabName === 'pdf') ? 'block' : 'none';
  document.getElementById("subtab-diff").style.display = (subTabName === 'diff') ? 'block' : 'none';
  document.getElementById("subtab-tex").style.display = (subTabName === 'tex') ? 'block' : 'none';
  const outreachEl = document.getElementById("subtab-outreach");
  if (outreachEl) outreachEl.style.display = (subTabName === 'outreach') ? 'block' : 'none';

  document.querySelectorAll(".subtab-btn").forEach(btn => btn.classList.remove("active"));
  const btn = document.getElementById("subtabBtn-" + subTabName);
  if (btn) btn.classList.add("active");

  if (subTabName === 'pdf') {
    const frame = document.getElementById("pdfPreviewFrame");
    if (!frame.src || frame.src === "about:blank" || frame.src.endsWith("#empty")) {
      loadCompiledPdfPreview();
    }
  } else if (subTabName === 'outreach') {
    renderOutreachTab();
  }
}

// Outreach & Recruiter DM Pitch Generator
function generateOutreachTemplates(company, jobTitle, matchedSkills, matchScore) {
  const safeComp = company || "Target Company";
  const safeTitle = jobTitle || "Software Engineer";
  const skillsList = (matchedSkills && matchedSkills.length > 0) ? matchedSkills.slice(0, 4).join(", ") : "Cloud Architectures, Agentic AI, and Full-Stack Systems";
  const score = matchScore ? `${matchScore}%` : "95%+";

  const emailSubject = `Application & Introduction: ${safeTitle} - Harsh Jha (${score} match)`;
  const emailBody = `Hi Team,

I hope you're having a productive week.

I recently reviewed the ${safeTitle} opening at ${safeComp} and was immediately drawn to your engineering direction. With 2.5+ years building production-grade agentic AI, low-latency microservices, and distributed cloud workflows, I've developed key strengths directly aligned with your tech stack (${skillsList}).

A few highlights relevant to ${safeComp}:
• Production AI & Cloud: Built VitaTrack.ai and agentic LLM pipelines handling high-throughput semantic retrieval and tool execution.
• Scalable Systems: Deep hands-on experience across Python, Go, TypeScript, FastAPI, PostgreSQL, and Docker/K8s.
• High Ownership: IIT Indore alumnus focused on clean, maintainable, resilient code with end-to-end delivery.

I've attached my tailored LaTeX CV for your review. Would you or the engineering hiring lead be open to a 10-minute introductory conversation next week?

Best regards,
Harsh Jha
IIT Indore Alumnus • Senior AI Engineer
LinkedIn: linkedin.com/in/harshjha-iiti
GitHub: github.com/jhaharsh03`;

  const linkedinDm = `Hi [Name], I noticed you're leading talent/engineering at ${safeComp}. I recently tailored my CV for the ${safeTitle} opening—my background in ${skillsList} aligns closely with what the team is building. Would love to connect and share my portfolio!`;

  const recruiterNote = `Hello [Recruiter Name],

I hope this finds you well. I just submitted my tailored application for the ${safeTitle} position at ${safeComp}.

Given my strong track record in ${skillsList} and building scalable agentic systems, I believe I can make an immediate impact on the team's key milestones this quarter.

I'd welcome the chance to briefly introduce myself and learn more about the interview timeline. Thank you for your time and consideration!

Warm regards,
Harsh Jha (linkedin.com/in/harshjha-iiti)`;

  CURRENT_OUTREACH_TEMPLATES = {
    company: safeComp,
    title: safeTitle,
    emailSubject: emailSubject,
    emailBody: emailBody,
    linkedinDm: linkedinDm,
    recruiterNote: recruiterNote
  };
}

function renderOutreachTab() {
  const container = document.getElementById("outreachContentContainer");
  if (!container) return;

  const comp = document.getElementById("companyName")?.value.trim() || (CURRENT_TAILORED_RESULT?.company) || "";
  const title = document.getElementById("jobTitle")?.value.trim() || (CURRENT_TAILORED_RESULT?.job_title) || "";
  const skills = CURRENT_TAILORED_RESULT?.analysis?.top_priorities || ["Python", "Go", "Docker", "REST APIs"];
  const score = CURRENT_TAILORED_RESULT?.analysis?.match_score || 92;

  if (!comp) {
    container.innerHTML = `
      <div style="text-align: center; color: var(--text-muted); padding: 40px; background: var(--bg-raised); border-radius: 8px; border: 1px dashed var(--border-subtle);">
        <i class="fa fa-paper-plane" style="font-size: 2rem; color: var(--border-dark); margin-bottom: 12px; display: block;"></i>
        <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">No Target Company Selected</div>
        <div style="font-size: 0.82rem;">Select a company from the Directory or enter a company name in Studio to generate outreach messages.</div>
      </div>
    `;
    return;
  }

  generateOutreachTemplates(comp, title, skills, score);
  const t = CURRENT_OUTREACH_TEMPLATES;

  container.innerHTML = `
    <!-- Outreach Card 1: Cold Email to Hiring Manager -->
    <div class="outreach-card">
      <div class="outreach-header">
        <div>
          <span style="font-weight: 700; font-size: 0.88rem; color: var(--text-primary);">
            <i class="fa fa-envelope" style="color: var(--accent-emerald);"></i> 1. Direct Cold Email to Hiring Lead
          </span>
          <span style="font-size: 0.74rem; color: var(--text-muted); margin-left: 6px;">(Best for engineering managers / directors)</span>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="copyOutreachTemplate('email')">
          <i class="fa fa-copy"></i> Copy Full Email
        </button>
      </div>
      <div style="font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">
        Subject: <span style="color: var(--text-primary); font-family: var(--font-mono);">${escapeHtml(t.emailSubject)}</span>
      </div>
      <div class="outreach-body">${escapeHtml(t.emailBody)}</div>
    </div>

    <!-- Outreach Card 2: LinkedIn Connection Request -->
    <div class="outreach-card">
      <div class="outreach-header">
        <div>
          <span style="font-weight: 700; font-size: 0.88rem; color: var(--text-primary);">
            <i class="fa-brands fa-linkedin" style="color: var(--ink-subtle);"></i> 2. LinkedIn Connection Note (&lt; 300 chars)
          </span>
          <span style="font-size: 0.74rem; color: var(--text-muted); margin-left: 6px;">(Optimal for adding hiring managers on LinkedIn)</span>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="copyOutreachTemplate('linkedin')">
          <i class="fa fa-copy"></i> Copy Note
        </button>
      </div>
      <div class="outreach-body">${escapeHtml(t.linkedinDm)}</div>
      <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 6px; text-align: right;">${t.linkedinDm.length} / 300 characters</div>
    </div>

    <!-- Outreach Card 3: Recruiter InMail / Talent Partner DM -->
    <div class="outreach-card">
      <div class="outreach-header">
        <div>
          <span style="font-weight: 700; font-size: 0.88rem; color: var(--text-primary);">
            <i class="fa fa-user-tie" style="color: var(--ink-subtle);"></i> 3. Recruiter &amp; Talent Partner Direct Message
          </span>
          <span style="font-size: 0.74rem; color: var(--text-muted); margin-left: 6px;">(For in-house technical recruiters)</span>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="copyOutreachTemplate('recruiter')">
          <i class="fa fa-copy"></i> Copy Message
        </button>
      </div>
      <div class="outreach-body">${escapeHtml(t.recruiterNote)}</div>
    </div>
  `;
}

function copyOutreachTemplate(kind) {
  if (!CURRENT_OUTREACH_TEMPLATES) return;
  if (kind === 'email') {
    const full = CURRENT_OUTREACH_TEMPLATES.emailSubject + "\\n\\n" + CURRENT_OUTREACH_TEMPLATES.emailBody;
    copyTextToClipboard(full, "Cold Email copied to clipboard!");
  } else if (kind === 'linkedin') {
    copyTextToClipboard(CURRENT_OUTREACH_TEMPLATES.linkedinDm, "LinkedIn connection note copied!");
  } else if (kind === 'recruiter') {
    copyTextToClipboard(CURRENT_OUTREACH_TEMPLATES.recruiterNote, "Recruiter message copied!");
  }
}

function copyTextToClipboard(text, successMsg = "Copied to clipboard!") {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(successMsg);
    }).catch(() => {
      fallbackCopyText(text, successMsg);
    });
  } else {
    fallbackCopyText(text, successMsg);
  }
}

function fallbackCopyText(text, successMsg) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    showToast(successMsg);
  } catch (e) {
    showToast("Failed to copy");
  }
  document.body.removeChild(ta);
}

// 1-Click Role Bookmark
async function quickBookmarkRole(company, title, url) {
  const bookmarkData = {
    company: company,
    job_title: title || "Open Role",
    job_url: url || "",
    status: "Bookmarked",
    notes: "Saved via directory quick bookmark."
  };

  try {
    const res = await fetch("/api/bookmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bookmarkData)
    });
    if (res.ok) {
      showToast(`Bookmarked ${company} - ${bookmarkData.job_title} in Tracker!`);
      loadTrackerData();
      return;
    }
  } catch (e) {
    // Fallback for static GitHub pages using localStorage
  }

  // LocalStorage fallback for GitHub Pages
  try {
    let saved = JSON.parse(localStorage.getItem("applyfox_bookmarks") || "[]");
    saved.unshift({
      ...bookmarkData,
      id: "bm_" + Date.now(),
      created_at: new Date().toISOString()
    });
    localStorage.setItem("applyfox_bookmarks", JSON.stringify(saved));
    showToast(`Bookmarked ${company} - ${bookmarkData.job_title} (saved locally)!`);
  } catch (e) {
    showToast(`Bookmarked ${company}!`);
  }
}

// System Status Modal
function openSystemStatusModal() {
  const overlay = document.getElementById("companyModalOverlay");
  const body = document.getElementById("companyModalBody");
  if (!overlay || !body) return;

  body.innerHTML = `
    <div style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px; margin-bottom: 20px;">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <span class="sync-dot" style="width: 10px; height: 10px;"></span>
        <h2 style="font-family: var(--font-display); font-size: 1.85rem; font-weight: 600; color: var(--text-primary); margin: 0;">
          Applyfox Routine Update Pipeline
        </h2>
        <span class="sync-badge" style="cursor: default;">
          <span class="sync-dot"></span> Live Sync &bull; Sundays 00:00 UTC
        </span>
      </div>
      <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 6px;">
        Automated weekend routine sync engine powered by GitHub Actions &amp; Python automation.
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 20px;">
      <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Sync Cadence</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: var(--ink); margin-top: 4px;">Every Sunday 00:00 UTC</div>
      </div>
      <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Companies Tracked</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-top: 4px;">7,406 Companies</div>
      </div>
      <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Indexed Open Roles</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-top: 4px;">36,288 Roles</div>
      </div>
      <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Supported Fields</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: var(--accent-emerald); margin-top: 4px;">5 Disciplines</div>
      </div>
    </div>

    <div style="margin-bottom: 20px;">
      <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 8px 0;">Routine Update Pipeline Stages</h4>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div style="padding: 10px 14px; background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 8px; font-size: 0.82rem;">
          <strong>Stage 1: Multi-Discipline Role Enrichment</strong> &bull; Scrapes &amp; verifies open roles across Software &amp; AI, UI/UX Design, IT Infrastructure, Legal, and Operations.
        </div>
        <div style="padding: 10px 14px; background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 8px; font-size: 0.82rem;">
          <strong>Stage 2: 2026 Funding &amp; Distress Audits</strong> &bull; Ingests newest Series A&ndash;D funding rounds, lead investors, and company health signals.
        </div>
        <div style="padding: 10px 14px; background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 8px; font-size: 0.82rem;">
          <strong>Stage 3: Automated Static Compilation</strong> &bull; Rebuilds single-file, zero-dependency bundles (<code>index.html</code> and <code>docs/index.html</code>) for instant edge delivery.
        </div>
        <div style="padding: 10px 14px; background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: 8px; font-size: 0.82rem;">
          <strong>Stage 4: GitHub Actions Deployment</strong> &bull; Automatically commits fresh data and triggers GitHub Pages deployment with zero downtime.
        </div>
      </div>
    </div>

    <div style="display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid var(--border-subtle); padding-top: 16px;">
      <button class="btn btn-secondary" onclick="closeCompanyModal()">Close</button>
      <a class="btn btn-primary" href="https://github.com/harshdotcom/Applyfox/actions" target="_blank" rel="noopener noreferrer">
        <i class="fa-solid fa-code-branch"></i> View GitHub Actions Runs &rarr;
      </a>
    </div>
  `;
  overlay.classList.add("active");
  document.body.style.overflow = "hidden";
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

/* ------------------------------------------------------------------
   Directory: one tab row + one filter row.
   The CURRENT_* variables are the single source of truth; every control
   changes state and calls refreshDirectoryView(), which syncs the UI from
   that state and issues exactly one request.
------------------------------------------------------------------ */
const ATS_SHEETS = ["master", "ashby", "greenhouse", "lever", "workday"];

function currentDirectoryTab() {
  if (CURRENT_DIRECTORY_MODE === "roles") return "roles";
  if (CURRENT_SHEET_KEY === "funded_startups") return "startups";
  if (CURRENT_SHEET_KEY === "startup_failures") return "failures";
  return "companies";
}

// Change tab state without loading (callers load once afterwards).
function setDirectoryTab(tab) {
  CURRENT_PAGE = 1;
  if (tab === "roles") {
    CURRENT_DIRECTORY_MODE = "roles";
    return;
  }
  CURRENT_DIRECTORY_MODE = "companies";
  const next = tab === "startups" ? "funded_startups"
             : tab === "failures" ? "startup_failures"
             : (ATS_SHEETS.includes(CURRENT_SHEET_KEY) ? CURRENT_SHEET_KEY : "master");
  if (next !== "funded_startups") CURRENT_MONTH = "";   // month only exists on Startups
  CURRENT_SHEET_KEY = next;
}

function selectDirectoryTab(tab) {
  setDirectoryTab(tab);
  refreshDirectoryView();
}

// Kept for existing callers (footer links, company modal, etc.)
function switchDirectoryMode(mode) {
  selectDirectoryTab(mode === "roles" ? "roles" : (currentDirectoryTab() === "roles" ? "companies" : currentDirectoryTab()));
}
function switchPortalSheet(sheetKey) {
  CURRENT_DIRECTORY_MODE = "companies";
  CURRENT_SHEET_KEY = sheetKey;
  if (sheetKey !== "funded_startups") CURRENT_MONTH = "";
  CURRENT_PAGE = 1;
  refreshDirectoryView();
}
function filterByMonth(month) {
  CURRENT_MONTH = (month === "All Months") ? "" : (month || "");
  CURRENT_PAGE = 1;
  refreshDirectoryView();
}
function applyQuickSearch(term) {
  CURRENT_QUERY = term || "";
  CURRENT_PAGE = 1;
  refreshDirectoryView();
}
function renderPortalSheetsSummary() { syncDirectoryControls(); }

function clearAllFilters() {
  CURRENT_QUERY = "";
  CURRENT_ROLE = "";
  CURRENT_WORK_MODE = "";
  CURRENT_LEVEL = "";
  CURRENT_MONTH = "";
  if (ATS_SHEETS.includes(CURRENT_SHEET_KEY)) CURRENT_SHEET_KEY = "master";
  const input = document.getElementById("portalSearch");
  if (input) input.value = "";
  CURRENT_PAGE = 1;
  refreshDirectoryView();
}

// Failed/distressed startups have no roles, so role / seniority / work-mode
// filters would always return zero rows there. They are hidden and not sent.
function tabUsesRoleFilters(tab) { return tab !== "failures"; }

function setSelectValue(id, value, defaultValue = "") {
  const el = document.getElementById(id);
  if (!el) return;
  const v = value || defaultValue;
  if (v && !Array.from(el.options).some(o => o.value === v)) {
    el.add(new Option(v, v));   // never show "Any" while a filter is actually applied
  }
  el.value = v;
  el.classList.toggle("is-set", v !== defaultValue);
}

function setHidden(id, hidden) {
  const el = document.getElementById(id);
  if (el) el.hidden = hidden;
}

let MONTH_OPTIONS_KEY = "";
function renderMonthOptions() {
  const el = document.getElementById("portalMonthSelect");
  const summary = PORTAL_SUMMARIES.find(s => s.key === "funded_startups");
  if (!el || !summary || !Array.isArray(summary.months)) return;
  const months = summary.months.filter(m => m.name !== "All Months");
  const key = months.map(m => m.name + m.count).join("|");
  if (key === MONTH_OPTIONS_KEY) return;
  MONTH_OPTIONS_KEY = key;
  el.innerHTML = `<option value="">Any month</option>` +
    months.map(m => `<option value="${escapeHtml(m.name)}">${escapeHtml(m.name)} &middot; ${m.count}</option>`).join("");
}

function syncDirectoryControls() {
  const tab = currentDirectoryTab();

  // Tabs + live counts
  document.querySelectorAll("#directoryTabs .dir-tab").forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("#directoryTabs [data-count]").forEach(el => {
    const s = PORTAL_SUMMARIES.find(x => x.key === el.dataset.count);
    if (s) el.textContent = Number(s.total_count).toLocaleString();
  });

  // Main nav: Startups/Failures live under "Startups", the rest under "Directory"
  document.querySelectorAll(".nav-tabs .tab-btn").forEach(b => b.classList.remove("active"));
  const navBtn = document.getElementById((tab === "startups" || tab === "failures") ? "navBtn-startups" : "navBtn-portals");
  if (navBtn && document.getElementById("view-portals").style.display !== "none") navBtn.classList.add("active");

  // Which filters apply to this tab
  const roleFilters = tabUsesRoleFilters(tab);
  setHidden("portalRoleSelect", !roleFilters);
  setHidden("portalLevelSelect", !roleFilters);
  setHidden("portalModeSelect", !roleFilters);
  setHidden("portalMonthSelect", tab !== "startups");
  setHidden("portalAtsSelect", tab !== "companies");

  renderMonthOptions();
  setSelectValue("portalRoleSelect", CURRENT_ROLE);
  setSelectValue("portalLevelSelect", CURRENT_LEVEL);
  setSelectValue("portalModeSelect", CURRENT_WORK_MODE);
  setSelectValue("portalMonthSelect", CURRENT_MONTH);
  setSelectValue("portalAtsSelect", ATS_SHEETS.includes(CURRENT_SHEET_KEY) ? CURRENT_SHEET_KEY : "master", "master");
  setSelectValue("portalLimitSelect", String(CURRENT_LIMIT), "25");

  // Search box mirrors state (but never fights the user mid-typing)
  const input = document.getElementById("portalSearch");
  if (input) {
    if (document.activeElement !== input) input.value = CURRENT_QUERY;
    input.placeholder = {
      startups: "Search startups, sectors or investors",
      failures: "Search companies, reasons or sectors",
      companies: "Search companies",
      roles: "Search roles, companies or skills",
    }[tab];
  }

  // "Clear" appears only when something is actually filtering this tab
  const active = !!CURRENT_QUERY
    || (roleFilters && !!(CURRENT_ROLE || CURRENT_LEVEL || CURRENT_WORK_MODE))
    || (tab === "startups" && !!CURRENT_MONTH)
    || (tab === "companies" && CURRENT_SHEET_KEY !== "master");
  setHidden("filterClear", !active);
}

function onPortalSearchInput(val) {
  clearTimeout(SEARCH_DEBOUNCE_TIMER);
  SEARCH_DEBOUNCE_TIMER = setTimeout(() => {
    CURRENT_QUERY = val.trim();
    CURRENT_PAGE = 1;
    refreshDirectoryView();
  }, 250);
}

function onPortalLimitChange(val) {
  CURRENT_LIMIT = parseInt(val, 10) || 25;
  CURRENT_PAGE = 1;
  refreshDirectoryView();
}

function refreshDirectoryView() {
  syncDirectoryControls();
  const tab = currentDirectoryTab();
  const roleFilters = tabUsesRoleFilters(tab);
  const role  = roleFilters ? CURRENT_ROLE : "";
  const mode  = roleFilters ? CURRENT_WORK_MODE : "";
  const level = roleFilters ? CURRENT_LEVEL : "";
  if (tab === "roles") {
    loadRolesFeedPage(CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, role, mode, level);
  } else {
    const month = (tab === "startups") ? CURRENT_MONTH : "";
    loadPortalSheetPage(CURRENT_SHEET_KEY, CURRENT_PAGE, CURRENT_LIMIT, CURRENT_QUERY, month, role, mode, level);
  }
}

async function loadRolesFeedPage(page, limit, query, discipline = "", workMode = "", level = "") {
  const tbody = document.getElementById("portalTableBody");
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fa fa-spinner fa-spin"></i> Loading live open roles feed (page ${page})...</td></tr>`;

  let data = null;
  try {
    const params = new URLSearchParams({
      page: page,
      limit: limit,
      q: query || "",
      discipline: discipline || "",
      work_mode: workMode || "",
      level: level || ""
    });
    const res = await fetch(`/api/roles?${params.toString()}`);
    if (!res.ok) throw new Error("API not reachable");
    data = await res.json();
  } catch (e) {
    handleStaticRolesFeedFallback(page, limit, query, discipline, workMode, level);
    return;
  }

  if (data) {
    renderRolesFeedTableHeader();
    renderRolesFeedTable(data);
    renderRolesFeedPagination(data);
  }
}

function renderRolesFeedTableHeader() {
  const thead = document.querySelector("#portalTable head") || document.querySelector("#portalTable thead");
  if (!thead) return;
  thead.innerHTML = `
    <tr>
      <th style="width: 50px;">#</th>
      <th style="min-width: 220px;">Role</th>
      <th>Company</th>
      <th>Department</th>
      <th>Location</th>
      <th style="min-width: 150px;">Est. pay</th>
      <th style="text-align: right; min-width: 170px;"></th>
    </tr>
  `;
}

function renderRolesFeedTable(data) {
  const tbody = document.getElementById("portalTableBody");
  if (!data.items || data.items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 50px;">
          <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 6px;">No open roles found matching "<strong>${escapeHtml(CURRENT_QUERY || CURRENT_ROLE || CURRENT_WORK_MODE || '')}</strong>"</div>
          <div style="font-size: 0.84rem; color: var(--text-muted); margin-bottom: 14px;">Try searching for broader keywords like <em>Legal</em>, <em>UI UX</em>, <em>DevOps</em>, or clear your filters.</div>
          <button class="btn btn-sm btn-secondary" onclick="clearAllFilters()">Clear filters</button>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = data.items.map((item, idx) => {
    const rowIndex = data.start_index + idx;
    const safeTitle = escapeHtml(item.title || "Open Role");
    const safeComp = escapeHtml(item.company || "Company");
    const safeJsTitle = safeTitle.replace(/'/g, "\\'");
    const safeJsComp = safeComp.replace(/'/g, "\\'");
    const safeBoardUrl = escapeHtml(item.board_url || "").replace(/'/g, "\\'");
    const safeItemData = encodeURIComponent(JSON.stringify(item));

    const ats = (item.ats || "").toLowerCase();
    let badgeClass = "badge-other";
    if (ats.includes("ashby")) badgeClass = "badge-ashby";
    if (ats.includes("greenhouse")) badgeClass = "badge-greenhouse";
    if (ats.includes("lever")) badgeClass = "badge-lever";
    if (ats.includes("workday")) badgeClass = "badge-workday";

    let deptIcon = "fa-briefcase";
    const dLower = (item.department || "").toLowerCase();
    if (dLower.includes("engineer") || dLower.includes("software") || dLower.includes("ai")) deptIcon = "fa-code";
    else if (dLower.includes("design") || dLower.includes("ui") || dLower.includes("ux")) deptIcon = "fa-pen-nib";
    else if (dLower.includes("cloud") || dLower.includes("it") || dLower.includes("sys")) deptIcon = "fa-server";
    else if (dLower.includes("legal") || dLower.includes("compliance")) deptIcon = "fa-scale-balanced";
    else if (dLower.includes("product") || dLower.includes("ops")) deptIcon = "fa-cubes";

    let locIcon = "fa-location-dot";
    const locLower = (item.location || "").toLowerCase();
    if (locLower.includes("remote")) locIcon = "fa-globe";
    else if (locLower.includes("hybrid")) locIcon = "fa-building";

    const skillsHtml = Array.isArray(item.skills) 
      ? item.skills.slice(0, 3).map(s => `<span class="skill-pill-sm">${escapeHtml(s)}</span>`).join("")
      : "";

    const salaryHtml = item.salary_estimate 
      ? `<span class="salary-badge"><i class="fa fa-sack-dollar"></i> ${escapeHtml(item.salary_estimate)}</span>`
      : "";

    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.78rem; font-family: var(--font-mono);">${rowIndex}</td>
        <td>
          <div class="role-feed-title">
            <span style="font-weight: 600; color: var(--text-primary); cursor: pointer;" onclick="useCompanyInStudio('${safeJsComp}', '${safeBoardUrl}', '${safeJsTitle}')" title="Tailor CV for this position">${safeTitle}</span>
            <span class="badge-level">${escapeHtml(item.level || 'Mid')}</span>
          </div>
          <div style="margin-top: 4px;">
            ${skillsHtml}
          </div>
        </td>
        <td>
          <div class="company-name-clickable" onclick="openCompanyModal('${safeItemData}')" title="Click to view company profile">
            <span>${safeComp}</span>
            <i class="fa fa-circle-info" style="font-size: 0.72rem; color: var(--accent-emerald);"></i>
          </div>
          <div style="margin-top: 4px;">
            <span class="portal-badge ${badgeClass}"><i class="fa fa-tag"></i> ${escapeHtml((item.ats || 'ATS').toUpperCase())}</span>
          </div>
        </td>
        <td>
          <div style="font-size: 0.82rem; font-weight: 500; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
            <i class="fa ${deptIcon}" style="color: var(--accent-emerald); font-size: 0.75rem;"></i>
            <span>${escapeHtml(item.department || 'General')}</span>
          </div>
        </td>
        <td>
          <div style="font-size: 0.82rem; color: var(--text-secondary); display: flex; align-items: center; gap: 5px;">
            <i class="fa ${locIcon}" style="color: var(--text-muted); font-size: 0.75rem;"></i>
            <span>${escapeHtml(item.location || 'Flexible')}</span>
          </div>
        </td>
        <td>
          <div>${salaryHtml}</div>
        </td>
        <td style="text-align: right; white-space: nowrap;">
          <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
            <button class="btn btn-sm btn-secondary" onclick="useCompanyInStudio('${safeJsComp}', '${safeBoardUrl}', '${safeJsTitle}')" title="Pre-fill CV Studio for this exact role">
              Tailor CV
            </button>
            <button class="btn btn-sm btn-secondary" onclick="openOutreachForRole('${safeJsComp}', '${safeJsTitle}', '${safeBoardUrl}')" title="Generate Hiring Manager Outreach">
              <i class="fa fa-paper-plane"></i>
            </button>
            <a class="ext-link" href="${escapeHtml(item.google_jobs_url || item.board_url)}" target="_blank" rel="noopener noreferrer" title="Search opening on Google Jobs" style="padding: 4px 7px;">
              <i class="fa fa-arrow-up-right-from-square"></i>
            </a>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderRolesFeedPagination(data) {
  const info = document.getElementById("portalPageInfo");
  if (info) {
    info.innerHTML = `Showing ${data.start_index}&ndash;${data.end_index} of <strong>${data.total_filtered.toLocaleString()}</strong> open positions in <strong>Live Roles Feed</strong>`;
  }

  const nav = document.getElementById("portalPageNav");
  if (!nav) return;
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

function handleStaticRolesFeedFallback(page, limit, query, discipline, workMode, level) {
  let allRoles = [];
  const compPool = (typeof EMBEDDED_ITEMS !== 'undefined' ? EMBEDDED_ITEMS : []).concat(
    typeof EMBEDDED_FUNDED_STARTUPS !== 'undefined' ? EMBEDDED_FUNDED_STARTUPS : []
  );

  let rIdx = 1;
  compPool.forEach(c => {
    if (Array.isArray(c.roles)) {
      c.roles.forEach(r => {
        const title = r.title || 'Specialist';
        const dept = r.department || 'Engineering';
        const lvl = r.level || 'Mid';
        const loc = r.location || 'Remote';
        let salary = "$140k – $185k";
        let skills = ["Core Competency", "Domain Knowledge", "Agile Execution"];
        const dLower = dept.toLowerCase();
        if (dLower.includes("legal")) {
          salary = "$180k – $250k";
          skills = ["Contracts", "Compliance", "Risk Assessment"];
        } else if (dLower.includes("design") || dLower.includes("ui") || dLower.includes("ux")) {
          salary = "$135k – $180k";
          skills = ["Figma", "UI/UX", "User Research", "Design Systems"];
        } else if (dLower.includes("cloud") || dLower.includes("it")) {
          salary = "$145k – $195k";
          skills = ["AWS/GCP", "Kubernetes", "Linux", "Security"];
        }

        allRoles.push({
          id: `role_${rIdx++}`,
          title: title,
          company: c.name || "Tech Company",
          slug: c.slug || "",
          ats: c.ats || "ATS",
          department: dept,
          level: lvl,
          location: loc,
          type: r.type || "Full-time",
          salary_estimate: salary,
          skills: skills,
          board_url: c.board_url || c.website || `https://www.google.com/search?q=${encodeURIComponent(c.name + ' careers')}`,
          google_jobs_url: `https://www.google.com/search?q=${encodeURIComponent(c.name + ' ' + title + ' job')}`
        });
      });
    }
  });

  let filtered = allRoles;

  // Filter discipline
  if (discipline && discipline.toLowerCase() !== 'all' && discipline.toLowerCase() !== 'all disciplines') {
    const dLower = discipline.toLowerCase();
    filtered = filtered.filter(r => r.department.toLowerCase().includes(dLower) || r.title.toLowerCase().includes(dLower) || dLower.includes(r.department.toLowerCase()));
  }

  // Filter workMode
  if (workMode && workMode.toLowerCase() !== 'all' && workMode.toLowerCase() !== 'all locations') {
    const wLower = workMode.toLowerCase();
    filtered = filtered.filter(r => r.location.toLowerCase().includes(wLower));
  }

  // Filter level
  if (level && level.toLowerCase() !== 'all' && level.toLowerCase() !== 'all seniorities') {
    const lLower = level.toLowerCase();
    filtered = filtered.filter(r => r.level.toLowerCase().includes(lLower));
  }

  // Filter query
  if (query && query.trim()) {
    const qNorm = query.toLowerCase().replace(/[^a-z0-9]/g, " ");
    const tokens = qNorm.split(" ").filter(t => t.length > 0);
    filtered = filtered.filter(r => {
      const text = `${r.title} ${r.company} ${r.department} ${r.level} ${r.location} ${r.skills.join(" ")}`.toLowerCase().replace(/[^a-z0-9]/g, " ");
      if (text.includes(qNorm)) return true;
      if (tokens.every(t => text.includes(t))) return true;
      if (tokens.some(t => ["ui", "ux", "uiux", "design", "graphic"].includes(t)) && (text.includes("ui") || text.includes("ux") || text.includes("design"))) return true;
      if (tokens.some(t => ["legal", "law", "lawyer", "counsel", "compliance"].includes(t)) && (text.includes("legal") || text.includes("compliance") || text.includes("counsel"))) return true;
      if (tokens.some(t => ["it", "sysadmin", "cloud", "infra", "security"].includes(t)) && (text.includes("it") || text.includes("cloud") || text.includes("security") || text.includes("systems"))) return true;
      return false;
    });
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const curPage = Math.min(page, totalPages);
  const start = (curPage - 1) * limit;
  const end = start + limit;
  const slice = filtered.slice(start, end);

  const staticData = {
    kind: "roles_feed",
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

  renderRolesFeedTableHeader();
  renderRolesFeedTable(staticData);
  renderRolesFeedPagination(staticData);
}

function openOutreachForRole(company, title, boardUrl) {
  switchView('tailor');
  const compInput = document.getElementById("companyName");
  if (compInput) compInput.value = company;
  const titleInput = document.getElementById("jobTitle");
  if (titleInput) titleInput.value = title;
  const urlInput = document.getElementById("jobUrl");
  if (urlInput && boardUrl) urlInput.value = boardUrl;
  switchSubTab('outreach');
  renderOutreachTab();
  showToast(`Generated custom cold outreach for ${company} (${title})!`);
}

function matchesCompanyStatic(item, query, kind) {
  if (!query || !query.trim()) return true;
  const qNorm = query.toLowerCase().replace(/[^a-z0-9]/g, " ");
  const tokens = qNorm.split(" ").filter(t => t.length > 0);
  if (tokens.length === 0) return true;

  const compFields = [
    item.name || "",
    item.slug || "",
    item.ats || "",
    item.sector || "",
    item.what_they_build || "",
    item.lead_investors || "",
    item.country || "",
    item.round || "",
    item.what_happened || "",
    item.precise_reason || "",
    item.lesson || ""
  ].join(" ").toLowerCase().replace(/[^a-z0-9]/g, " ");

  const roles = Array.isArray(item.roles) ? item.roles : [];
  const roleStrings = roles.map(r => {
    if (typeof r === "string") return r.toLowerCase().replace(/[^a-z0-9]/g, " ");
    return `${r.title || ""} ${r.department || ""} ${r.level || ""} ${r.location || ""}`.toLowerCase().replace(/[^a-z0-9]/g, " ");
  });

  if (compFields.includes(qNorm)) return true;
  if (roleStrings.some(rn => rn.includes(qNorm))) return true;

  if (tokens.every(t => compFields.includes(t))) return true;
  if (roleStrings.some(rn => tokens.every(t => rn.includes(t)))) return true;

  // Synonyms & domain mapping
  if (tokens.some(t => ["ui", "ux", "uiux", "design", "designer", "graphic", "figma", "frontend"].includes(t))) {
    if (roleStrings.some(rn => rn.includes("ui") || rn.includes("ux") || rn.includes("design") || rn.includes("graphic"))) return true;
  }
  if (tokens.some(t => ["legal", "law", "lawyer", "counsel", "compliance", "contracts", "attorney", "regulatory"].includes(t))) {
    if (roleStrings.some(rn => rn.includes("legal") || rn.includes("compliance") || rn.includes("counsel") || rn.includes("contracts"))) return true;
  }
  if (tokens.some(t => ["it", "sysadmin", "devops", "cloud", "infra", "infrastructure", "security", "sre", "network"].includes(t))) {
    if (roleStrings.some(rn => rn.split(" ").includes("it") || rn.includes("cloud") || rn.includes("systems") || rn.includes("security") || rn.includes("infrastructure"))) return true;
  }
  if (tokens.some(t => ["pm", "product", "ops", "operations", "tpm", "program"].includes(t))) {
    if (roleStrings.some(rn => rn.includes("product") || rn.includes("operations"))) return true;
  }

  return false;
}

function sortAndRenderRolesHtml(rolesList, item, safeJsName, safeJsUrl, safeItemData) {
  if (!rolesList || rolesList.length === 0) {
    return item.open_jobs 
      ? `<span style="font-weight: 600; color: var(--ink); font-size: 0.78rem;">${escapeHtml(item.open_jobs)}</span>`
      : `<span style="color: var(--text-muted); font-size: 0.78rem;">Verified Board</span>`;
  }

  const qNorm = (CURRENT_QUERY || "").toLowerCase().replace(/[^a-z0-9]/g, " ");
  const qTokens = qNorm.split(" ").filter(t => t.length > 0);
  const rLower = (CURRENT_ROLE || "").toLowerCase().trim();

  function isRoleMatched(r) {
    const t = (typeof r === 'string' ? r : (r.title || "")).toLowerCase();
    const d = (typeof r === 'string' ? "" : (r.department || "")).toLowerCase();
    const combined = `${t} ${d}`;
    if (rLower && (t.includes(rLower) || d.includes(rLower) || rLower.includes(d))) return true;
    if (qTokens.length > 0) {
      if (combined.includes(qNorm)) return true;
      if (qTokens.every(tk => combined.includes(tk))) return true;
      if (qTokens.some(tk => ["ui", "ux", "uiux", "design", "graphic"].includes(tk)) && (t.includes("ui") || t.includes("ux") || t.includes("design") || d.includes("design"))) return true;
      if (qTokens.some(tk => ["legal", "counsel", "compliance", "law", "contracts"].includes(tk)) && (t.includes("legal") || t.includes("counsel") || t.includes("compliance") || d.includes("legal"))) return true;
      if (qTokens.some(tk => ["it", "cloud", "devops", "sysadmin", "infrastructure"].includes(tk)) && (t.includes("it") || t.includes("cloud") || t.includes("devops") || d.includes("cloud") || d.includes("it"))) return true;
      if (qTokens.some(tk => ["pm", "product", "ops", "operations"].includes(tk)) && (t.includes("product") || d.includes("product") || t.includes("operations") || d.includes("operations"))) return true;
    }
    return false;
  }

  const sortedRoles = [...rolesList].sort((a, b) => {
    const ma = isRoleMatched(a) ? 1 : 0;
    const mb = isRoleMatched(b) ? 1 : 0;
    return mb - ma;
  });

  const shownRoles = sortedRoles.slice(0, 3);
  const remaining = sortedRoles.length - shownRoles.length;

  return `
    <div class="role-tag-list">
      ${shownRoles.map(r => {
        const titleStr = typeof r === 'string' ? r : (r.title || '');
        const safeTitle = escapeHtml(titleStr);
        const safeRoleJs = safeTitle.replace(/'/g, "\\'");
        const isMatch = isRoleMatched(r);
        const highlightClass = isMatch ? "highlighted match-highlight" : "";
        const roleIcon = isMatch ? "fa-star" : "fa-briefcase";
        return `<span class="role-tag-pill ${highlightClass}" onclick="useCompanyInStudio('${safeJsName}', '${safeJsUrl}', '${safeRoleJs}')" title="1-Click Tailor CV for ${safeTitle}"><i class="fa ${roleIcon}" style="font-size: 0.65rem; opacity: 0.8;"></i> ${safeTitle}</span><a class="role-search-link" href="https://www.google.com/search?q=${encodeURIComponent(item.name + ' ' + titleStr + ' job posting')}" target="_blank" rel="noopener noreferrer" title="Search Google for ${safeTitle} opening" onclick="event.stopPropagation();"><i class="fa fa-arrow-up-right-from-square"></i></a>`;
      }).join("")}
      ${remaining > 0 ? `<span class="role-tag-more" onclick="openCompanyModal('${safeItemData}')" title="Click to view all ${rolesList.length} open roles in dossier">+${remaining} more</span>` : ''}
    </div>
  `;
}

function renderPortalTableHeader(kind) {
  const thead = document.querySelector("#portalTable head") || document.querySelector("#portalTable thead");
  if (!thead) return;
  if (kind === "funded_startups") {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Startup</th>
        <th>Round</th>
        <th style="min-width: 260px;">Building &middot; open roles</th>
        <th>Announced</th>
        <th>Research</th>
        <th style="text-align: right;"></th>
      </tr>
    `;
  } else if (kind === "startup_failures") {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Company</th>
        <th>Raised</th>
        <th>What happened</th>
        <th style="min-width: 200px;">Reason</th>
        <th style="min-width: 180px;">Lesson</th>
        <th style="text-align: right;"></th>
      </tr>
    `;
  } else {
    thead.innerHTML = `
      <tr>
        <th style="width: 50px;">#</th>
        <th>Company</th>
        <th>ATS</th>
        <th style="min-width: 240px;">Open roles</th>
        <th>Careers</th>
        <th>Research</th>
        <th style="text-align: right;"></th>
      </tr>
    `;
  }
}

async function loadPortalSheetPage(sheetKey, page, limit, query, month = "", role = "", workMode = "", level = "") {
  const tbody = document.getElementById("portalTableBody");
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fa fa-spinner fa-spin"></i> Loading ${escapeHtml(sheetKey)} sheet page ${page}...</td></tr>`;

  const searchInput = document.getElementById("portalSearch");
  if (searchInput) {
    if (sheetKey === 'funded_startups') {
      searchInput.placeholder = "Search startups, sectors, rounds or investors";
    } else if (sheetKey === 'startup_failures') {
      searchInput.placeholder = "Search by company, reason or sector";
    } else {
      searchInput.placeholder = "Search companies or ATS";
    }
  }

  let data = null;
  try {
    const params = new URLSearchParams({
      sheet: sheetKey,
      page: page,
      limit: limit,
      q: query || "",
      month: month || "",
      role: role || "",
      work_mode: workMode || "",
      level: level || ""
    });
    const res = await fetch(`/api/portals?${params.toString()}`);
    if (!res.ok) throw new Error("API not reachable");
    data = await res.json();
  } catch (e) {
    handleStaticPortalFallback(sheetKey, page, limit, query, month, role, workMode, level);
    return;
  }

  if (data) {
    const kind = data.kind || (sheetKey === 'funded_startups' ? 'funded_startups' : (sheetKey === 'startup_failures' ? 'startup_failures' : 'standard'));
    renderPortalTableHeader(kind);
    renderPortalTable(data);
    renderPortalPagination(data);
  }
}

function handleStaticPortalFallback(sheetKey, page, limit, query, month, role = "", workMode = "", level = "") {
  // If running on backend server without static embeds and server is offline, show reconnect UI
  if (typeof EMBEDDED_ITEMS === 'undefined' && typeof EMBEDDED_FUNDED_STARTUPS === 'undefined') {
    const tbody = document.getElementById("portalTableBody");
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <div style="font-size: 1.05rem; font-weight: 600; color: var(--accent); margin-bottom: 8px;">
            <i class="fa fa-triangle-exclamation"></i> Server Connection Reconnecting
          </div>
          <div style="font-size: 0.84rem; margin-bottom: 16px; color: var(--text-secondary);">
            The local Applyfox backend server is starting or reloading.
          </div>
          <button class="btn btn-sm btn-primary" onclick="refreshDirectoryView()">
            <i class="fa fa-rotate-right"></i> Retry Connection
          </button>
        </td>
      </tr>
    `;
    return;
  }

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
      filtered = filtered.filter(i => matchesCompanyStatic(i, query, "funded_startups"));
    }
  } else if (sheetKey === 'startup_failures') {
    kind = "startup_failures";
    title = "Failures & Distress 2026";
    filtered = (typeof EMBEDDED_FAILURES !== 'undefined') ? EMBEDDED_FAILURES : [];
    if (query) {
      filtered = filtered.filter(i => matchesCompanyStatic(i, query, "startup_failures"));
    }
  } else {
    filtered = (typeof EMBEDDED_ITEMS !== 'undefined') ? EMBEDDED_ITEMS : [];
    if (sheetKey !== 'master') {
      filtered = filtered.filter(i => (i.ats || '').toLowerCase().includes(sheetKey.toLowerCase()));
    }
    if (query) {
      filtered = filtered.filter(i => matchesCompanyStatic(i, query, "standard"));
    }
    title = sheetKey.toUpperCase() + " Portals";
  }

  // Apply Role / Job Title Filter
  if (role && role.trim().toLowerCase() !== 'all' && role.trim().toLowerCase() !== 'all roles' && role.trim().toLowerCase() !== 'all job titles' && role.trim().toLowerCase() !== 'all disciplines') {
    const rLower = role.trim().toLowerCase();
    filtered = filtered.filter(i => {
      if (Array.isArray(i.roles)) {
        return i.roles.some(ro => {
          const t = (ro.title || '').toLowerCase();
          const d = (ro.department || '').toLowerCase();
          return t.includes(rLower) || d.includes(rLower) || rLower.includes(d) || rLower.split(' ').some(w => w.length > 3 && (t.includes(w) || d.includes(w)));
        });
      }
      if (typeof i.roles === 'string') {
        return i.roles.toLowerCase().includes(rLower);
      }
      return false;
    });
  }

  // Apply Work Mode Filter (Remote, Hybrid, Onsite)
  if (workMode && workMode.trim().toLowerCase() !== 'all' && workMode.trim().toLowerCase() !== 'all locations' && workMode.trim().toLowerCase() !== 'all modes') {
    const wLower = workMode.trim().toLowerCase();
    filtered = filtered.filter(i => {
      if (Array.isArray(i.roles)) {
        return i.roles.some(ro => (ro.location || '').toLowerCase().includes(wLower));
      }
      return false;
    });
  }

  // Apply Seniority Level Filter (Entry, Mid, Senior, Lead, Director)
  if (level && level.trim().toLowerCase() !== 'all' && level.trim().toLowerCase() !== 'all levels' && level.trim().toLowerCase() !== 'all seniorities') {
    const lLower = level.trim().toLowerCase();
    filtered = filtered.filter(i => {
      if (Array.isArray(i.roles)) {
        return i.roles.some(ro => (ro.level || '').toLowerCase().includes(lLower));
      }
      return false;
    });
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
      const companyPageUrl = item.website || item.board_url || item.google_jobs_url || `https://www.google.com/search?q=${encodeURIComponent(item.name)}+official+website`;
      const safeJsUrl = escapeHtml(companyPageUrl).replace(/'/g, "\\'");
      const safeItemData = encodeURIComponent(JSON.stringify(item));
      
      const roundBadge = item.round ? `<span class="badge-round">${escapeHtml(item.round)}</span>` : "";
      const amountBadge = item.amount ? `<span class="badge-amount">${escapeHtml(item.amount)}</span>` : "";
      const sectorBadge = item.sector ? `<span class="badge-sector">${escapeHtml(item.sector)}</span>` : "";
      const locationText = item.country ? `<span class="badge-country"><i class="fa-solid fa-location-dot" style="font-size: 0.68rem;"></i> ${escapeHtml(item.country)}</span>` : "";

      const companyPageBtn = `
        <a class="ext-link" href="${escapeHtml(companyPageUrl)}" target="_blank" rel="noopener noreferrer" style="margin-right: 4px;" title="Open ${safeComp} official company page / careers">
          <i class="fa fa-globe" style="font-size: 0.72rem;"></i> <span>Website</span> <i class="fa fa-arrow-up-right-from-square" style="font-size: 0.65rem;"></i>
        </a>
      `;

      return `
        <tr>
          <td style="color: var(--text-muted); font-size: 0.78rem; font-family: var(--font-mono);">${rowIndex}</td>
          <td>
            <div class="company-name-clickable" onclick="openCompanyModal('${safeItemData}')" title="Click to view full ${safeComp} company profile & dossier">
              <span>${safeComp}</span>
              <i class="fa fa-circle-info" style="font-size: 0.72rem; color: var(--accent-emerald);"></i>
            </div>
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
            ${sortAndRenderRolesHtml(item.roles, item, safeJsName, safeJsUrl, safeItemData)}
          </td>
          <td>
            <div style="font-weight: 600; font-size: 0.82rem; color: var(--text-primary);"><i class="fa fa-calendar-check" style="color: var(--accent-emerald); font-size: 0.75rem;"></i> ${escapeHtml(item.month || item.announced_date)}</div>
            ${item.lead_investors ? `<div style="font-size: 0.74rem; color: var(--text-secondary); margin-top: 2px;">Lead: <strong>${escapeHtml(item.lead_investors)}</strong></div>` : ''}
          </td>
          <td style="white-space: nowrap;">
            ${companyPageBtn}
            <a class="intel-link intel-levels" href="${escapeHtml(item.levels_url)}" target="_blank" rel="noopener noreferrer" title="View salaries on Levels.fyi">
              Salaries
            </a>
            <a class="intel-link intel-glassdoor" href="${escapeHtml(item.glassdoor_url)}" target="_blank" rel="noopener noreferrer" title="View reviews on Glassdoor">
              Reviews
            </a>
          </td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-sm btn-secondary" onclick="useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
              Tailor CV
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
      const safeItemData = encodeURIComponent(JSON.stringify(item));
      const sectorBadge = item.sector ? `<span class="badge-sector" style="background: transparent; color: var(--accent); border-color: transparent;">${escapeHtml(item.sector)}</span>` : "";
      const countryText = item.country ? `<span class="badge-country"><i class="fa-solid fa-location-dot" style="font-size: 0.68rem;"></i> ${escapeHtml(item.country)}</span>` : "";

      return `
        <tr>
          <td style="color: var(--text-muted); font-size: 0.78rem; font-family: var(--font-mono);">${rowIndex}</td>
          <td>
            <div class="company-name-clickable" onclick="openCompanyModal('${safeItemData}')" title="Click to view full ${safeComp} failure dossier & profile">
              <span style="color: var(--accent);"><i class="fa fa-skull-crossbones" style="font-size: 0.8rem; opacity: 0.7; margin-right: 4px;"></i>${safeComp}</span>
              <i class="fa fa-circle-info" style="font-size: 0.72rem; color: var(--accent);"></i>
            </div>
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
            <div style="font-size: 0.82rem; line-height: 1.4; color: var(--accent); background: transparent; padding: 6px 8px; border-radius: 6px; border: 0; border-left: 2px solid var(--accent); border-radius: 0; max-width: 280px;">
              ${escapeHtml(item.precise_reason)}
            </div>
          </td>
          <td>
            <div style="font-size: 0.8rem; line-height: 1.4; color: var(--ink); background: transparent; padding: 6px 8px; border-radius: 6px; border: 0; border-left: 2px solid var(--ink); border-radius: 0; max-width: 260px;">
              <i class="fa fa-lightbulb" style="color: var(--ink-subtle);"></i> ${escapeHtml(item.lesson)}
            </div>
          </td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-sm btn-secondary" onclick="useCompanyInStudio('${safeJsName}', '${escapeHtml(item.google_jobs_url).replace(/'/g, "\\\\'")}')">
              Tailor
            </button>
          </td>
        </tr>
      `;
    }).join("");
    return;
  }

  // Standard Sheet rendering (Master, Ashby, Greenhouse, Lever, Workday)
  tbody.innerHTML = data.items.map((item, idx) => {
    const rowIndex = data.start_index + idx;
    const safeComp = escapeHtml(item.name || "");
    const safeJsName = safeComp.replace(/'/g, "\\'");
    const safeJsUrl = escapeHtml(item.board_url || "").replace(/'/g, "\\'");
    const safeItemData = encodeURIComponent(JSON.stringify(item));

    const ats = (item.ats || "").toLowerCase();
    let badgeClass = "badge-other";
    if (ats.includes("ashby")) badgeClass = "badge-ashby";
    if (ats.includes("greenhouse")) badgeClass = "badge-greenhouse";
    if (ats.includes("lever")) badgeClass = "badge-lever";
    if (ats.includes("workday")) badgeClass = "badge-workday";
    if (ats.includes("funded")) badgeClass = "badge-greenhouse";

    const rolesHtml = sortAndRenderRolesHtml(item.roles, item, safeJsName, safeJsUrl, safeItemData);

    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.78rem; font-family: var(--font-mono);">${rowIndex}</td>
        <td>
          <div class="company-name-clickable" onclick="openCompanyModal('${safeItemData}')" title="Click to view full ${safeComp} company profile & details">
            <span>${safeComp}</span>
            <i class="fa fa-circle-info" style="font-size: 0.72rem; color: var(--accent-emerald);"></i>
          </div>
          <div style="font-size: 0.74rem; color: var(--text-muted); font-family: var(--font-mono);">slug: ${escapeHtml(item.slug || '')}</div>
        </td>
        <td>
          <span class="portal-badge ${badgeClass}"><i class="fa fa-tag"></i> ${escapeHtml((item.ats || 'ATS').toUpperCase())}</span>
        </td>
        <td>${rolesHtml}</td>
        <td>
          <a class="ext-link" href="${escapeHtml(item.board_url)}" target="_blank" rel="noopener noreferrer" title="Open ${safeComp} official company page & careers">
            <i class="fa fa-globe" style="font-size: 0.72rem;"></i> <span>Website</span> <i class="fa fa-arrow-up-right-from-square" style="font-size: 0.68rem;"></i>
          </a>
        </td>
        <td style="white-space: nowrap;">
          <a class="intel-link intel-levels" href="${escapeHtml(item.levels_url)}" target="_blank" rel="noopener noreferrer" title="View salaries on Levels.fyi">
            Salaries
          </a>
          <a class="intel-link intel-glassdoor" href="${escapeHtml(item.glassdoor_url)}" target="_blank" rel="noopener noreferrer" title="View reviews on Glassdoor">
            Reviews
          </a>
        </td>
        <td style="text-align: right; white-space: nowrap;">
          <button class="btn btn-sm btn-secondary" onclick="useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
            Tailor CV
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
  refreshDirectoryView();
}

function useCompanyInStudio(name, url, roleTitle = "") {
  switchView('tailor');
  document.getElementById("companyName").value = name;
  if (url) {
    document.getElementById("jobUrl").value = url;
  }
  if (roleTitle) {
    document.getElementById("jobTitle").value = roleTitle;
  }
  document.getElementById("jdText").focus();
  const roleMsg = roleTitle ? ` for ${roleTitle}` : "";
  showToast(`Pre-filled ${name}${roleMsg} in Studio! Paste the Job Description to tailor.`);
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
    generateOutreachTemplates(company, title, data.analysis?.top_priorities, data.analysis?.match_score);

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
  generateOutreachTemplates(company, title, simData.analysis.top_priorities, simData.analysis.match_score);
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
  if (!diffStr || !diffStr.trim()) return '<div style="color: var(--ink-subtle); padding: 4px;">No changes made to this section.</div>';
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

// -------------------------------------------------------------
// COMPANY PROFILE DOSSIER MODAL ("COMPANY PAGE")
// -------------------------------------------------------------
function openCompanyModal(encodedData) {
  let item = null;
  try {
    item = JSON.parse(decodeURIComponent(encodedData));
  } catch(e) {
    console.error("Could not parse company data", e);
    return;
  }
  const overlay = document.getElementById("companyModalOverlay");
  const body = document.getElementById("companyModalBody");
  if (!overlay || !body || !item) return;

  const safeComp = escapeHtml(item.name || "Company");
  const safeJsName = safeComp.replace(/'/g, "\\'");
  const companyUrl = item.website || item.board_url || item.google_jobs_url || `https://www.google.com/search?q=${encodeURIComponent(item.name)}+official+website`;
  const safeJsUrl = escapeHtml(companyUrl).replace(/'/g, "\\'");

  const rolesList = Array.isArray(item.roles) ? item.roles : (typeof item.roles === 'string' ? item.roles.split(';').map(t => ({ title: t.trim(), department: 'Role', level: 'Mid-Senior', location: 'Remote / Hybrid' })) : []);
  let rolesModalHtml = "";
  if (rolesList.length > 0) {
    rolesModalHtml = `
      <div style="margin-bottom: 22px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0;">
            <i class="fa fa-briefcase" style="color: var(--accent-emerald);"></i> Active Opened Roles (${rolesList.length} Verified Positions)
          </h4>
          <span style="font-size: 0.72rem; color: var(--text-muted);"><i class="fa fa-wand-magic-sparkles" style="color: var(--accent-emerald);"></i> 1-Click Tailor CV</span>
        </div>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${rolesList.map(r => {
            const titleStr = typeof r === 'string' ? r : (r.title || '');
            const safeTitle = escapeHtml(titleStr);
            const safeRoleJs = safeTitle.replace(/'/g, "\\'");
            const dept = escapeHtml(r.department || "Engineering & AI");
            const level = escapeHtml(r.level || "Mid-Senior");
            const loc = escapeHtml(r.location || "Remote / Hybrid");
            return `
              <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-raised); border: 1px solid var(--border-subtle); padding: 9px 12px; border-radius: 8px; gap: 10px; flex-wrap: wrap;">
                <div>
                  <div style="font-weight: 600; font-size: 0.86rem; color: var(--text-primary);">${safeTitle}</div>
                  <div style="font-size: 0.73rem; color: var(--text-secondary); margin-top: 2px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                    <span class="badge-sector" style="font-size: 0.68rem; padding: 1px 6px;">${dept}</span>
                    <span style="color: var(--text-muted);">&bull; ${level} &bull; ${loc}</span>
                  </div>
                </div>
                <div style="display: flex; gap: 6px; align-items: center;">
                  <button class="btn btn-sm btn-primary" onclick="closeCompanyModal(); useCompanyInStudio('${safeJsName}', '${safeJsUrl}', '${safeRoleJs}')" style="padding: 4px 10px; font-size: 0.76rem; white-space: nowrap;">
                    Tailor CV
                  </button>
                  <button class="btn btn-sm btn-secondary" onclick="quickBookmarkRole('${safeJsName}', '${safeRoleJs}', '${safeJsUrl}')" style="padding: 4px 8px; font-size: 0.76rem; white-space: nowrap;" title="Quick Bookmark this role in Applications Tracker">
                    <i class="fa fa-bookmark"></i>
                  </button>
                  <a class="btn btn-sm btn-secondary" href="https://www.google.com/search?q=${encodeURIComponent(item.name + ' ' + titleStr + ' job posting')}" target="_blank" rel="noopener noreferrer" style="padding: 4px 8px; font-size: 0.76rem; white-space: nowrap;" title="Search Job on Google">
                    <i class="fa fa-arrow-up-right-from-square"></i>
                  </a>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  let html = "";
  if (item.what_happened || item.funding_before_failure) {
    // Startup Failure Dossier
    html = `
      <div style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <h2 style="font-family: var(--font-display); font-size: 1.85rem; font-weight: 600; color: var(--accent); margin: 0;">
            <i class="fa fa-skull-crossbones" style="font-size: 1.2rem; opacity: 0.85; margin-right: 4px;"></i>${safeComp}
          </h2>
          <span class="badge-sector" style="background: transparent; color: var(--accent); border-color: transparent;">${escapeHtml(item.sector || 'Tech')}</span>
          <span class="badge-fail-funding">${escapeHtml(item.funding_before_failure || 'Disclosed Capital')}</span>
        </div>
        <div style="margin-top: 8px; font-size: 0.82rem; color: var(--text-secondary);">
          <i class="fa-solid fa-location-dot"></i> ${escapeHtml(item.country || 'Global')} &bull; <i class="fa fa-clock"></i> ${escapeHtml(item.when_date || '2026')}
        </div>
      </div>

      <div style="margin-bottom: 18px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 8px 0;">What Happened</h4>
        <div style="background: var(--bg-raised); border: 1px solid var(--border-subtle); padding: 14px 16px; border-radius: 8px; font-size: 0.92rem; line-height: 1.5; color: var(--text-primary);">
          ${escapeHtml(item.what_happened || 'Startup encountered severe market headwinds.')}
        </div>
      </div>

      <div style="margin-bottom: 18px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); margin: 0 0 8px 0;">Precise Distress Signal / Root Cause</h4>
        <div style="background: transparent; border: 0; border-left: 2px solid var(--accent); border-radius: 0; padding: 12px 14px; border-radius: 8px; font-size: 0.88rem; line-height: 1.5; color: var(--accent);">
          <strong>Risk Analysis:</strong> ${escapeHtml(item.precise_reason || 'Premature scaling or capital depletion.')}
        </div>
      </div>

      <div style="margin-bottom: 22px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink); margin: 0 0 8px 0;">Post-Mortem Engineering Lesson</h4>
        <div style="background: transparent; border: 0; border-left: 2px solid var(--ink); border-radius: 0; padding: 12px 14px; border-radius: 8px; font-size: 0.88rem; line-height: 1.5; color: var(--ink);">
          <i class="fa fa-lightbulb" style="color: var(--ink-subtle); margin-right: 4px;"></i><strong>Lesson:</strong> ${escapeHtml(item.lesson || 'Maintain strong capital discipline and genuine PMF.')}
        </div>
      </div>

      <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 22px;">
        <a class="btn btn-secondary btn-sm" href="${escapeHtml(companyUrl)}" target="_blank" rel="noopener noreferrer">
          <i class="fa fa-newspaper" style="color: var(--accent-emerald);"></i> <span>Company Page / News ↗</span>
        </a>
        <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.levels_url || '')}" target="_blank" rel="noopener noreferrer">
          <i class="fa fa-chart-line" style="color: var(--ink-subtle);"></i> <span>Levels.fyi ↗</span>
        </a>
        <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.glassdoor_url || '')}" target="_blank" rel="noopener noreferrer">
          <i class="fa fa-star" style="color: var(--ink);"></i> <span>Glassdoor ↗</span>
        </a>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid var(--border-subtle); padding-top: 16px;">
        <button class="btn btn-secondary" onclick="closeCompanyModal()">Close</button>
        <button class="btn btn-primary" onclick="closeCompanyModal(); useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
          <i class="fa fa-file-pen"></i> Track Application &rarr;
        </button>
      </div>
    `;
  } else if (item.round || item.kind === 'funded_startups') {
    // 2026 Funded Startup Dossier
    html = `
      <div style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <h2 style="font-family: var(--font-display); font-size: 1.85rem; font-weight: 600; color: var(--text-primary); margin: 0;">${safeComp}</h2>
          ${item.round ? `<span class="badge-round" style="font-size: 0.8rem; padding: 4px 10px;">${escapeHtml(item.round)}</span>` : ''}
          ${item.amount ? `<span class="badge-amount" style="font-size: 0.8rem; padding: 4px 10px;">${escapeHtml(item.amount)}</span>` : ''}
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px;">
          ${item.sector ? `<span class="badge-sector">${escapeHtml(item.sector)}</span>` : ''}
          ${item.country ? `<span class="badge-country"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(item.country)}</span>` : ''}
          <span style="font-size: 0.78rem; color: var(--text-secondary);"><i class="fa fa-calendar-check" style="color: var(--accent-emerald);"></i> ${escapeHtml(item.month || item.announced_date)}</span>
        </div>
      </div>

      <div style="margin-bottom: 20px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 8px 0;">What They Are Building</h4>
        <div style="font-size: 0.94rem; line-height: 1.55; color: var(--text-primary); background: var(--bg-raised); padding: 14px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          ${escapeHtml(item.what_they_build || 'High-growth technology startup.')}
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px;">
        <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Lead Investors</div>
          <div style="font-size: 0.88rem; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${escapeHtml(item.lead_investors || 'Not disclosed / Syndicate')}</div>
        </div>
        <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Valuation / Capital</div>
          <div style="font-size: 0.88rem; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${escapeHtml(item.valuation && item.valuation !== 'N/D' ? item.valuation : (item.amount || 'Undisclosed'))}</div>
        </div>
        <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Market Outlook</div>
          <div style="font-size: 0.88rem; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${escapeHtml(item.outlook || 'Active Growth')}</div>
        </div>
      </div>

      ${item.outlook_reasoning ? `
        <div style="margin-bottom: 20px; padding: 10px 14px; background: transparent; border: 1px solid var(--rule); border-radius: 8px; font-size: 0.82rem; color: var(--ink);">
          <strong>Intelligence Signal:</strong> ${escapeHtml(item.outlook_reasoning)}
        </div>
      ` : ''}

      ${rolesModalHtml}

      <div style="margin-bottom: 24px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 10px 0;">Official Company Pages &amp; Intelligence</h4>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(companyUrl)}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-globe" style="color: var(--accent-emerald);"></i> <span>Official Company Page ↗</span>
          </a>
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.levels_url || '')}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-chart-line" style="color: var(--ink-subtle);"></i> <span>Levels.fyi Salaries ↗</span>
          </a>
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.glassdoor_url || '')}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-star" style="color: var(--ink);"></i> <span>Glassdoor Reviews ↗</span>
          </a>
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.google_jobs_url || '')}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-magnifying-glass" style="color: var(--accent-amber);"></i> <span>Google Jobs Search ↗</span>
          </a>
        </div>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid var(--border-subtle); padding-top: 16px;">
        <button class="btn btn-secondary" onclick="closeCompanyModal()">Close</button>
        <button class="btn btn-primary" onclick="closeCompanyModal(); useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
          <i class="fa fa-wand-magic-sparkles"></i> Launch CV Studio for ${safeComp} &rarr;
        </button>
      </div>
    `;
  } else {
    // Standard Directory Sheet Profile
    html = `
      <div style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <h2 style="font-family: var(--font-display); font-size: 1.85rem; font-weight: 600; color: var(--text-primary); margin: 0;">${safeComp}</h2>
          <span class="portal-badge badge-greenhouse"><i class="fa fa-tag"></i> ${(item.ats || 'ATS').toUpperCase()}</span>
        </div>
        <div style="font-size: 0.78rem; color: var(--text-muted); font-family: var(--font-mono); margin-top: 6px;">slug: ${escapeHtml(item.slug || '')}</div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 22px;">
        <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">ATS Platform</div>
          <div style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${escapeHtml((item.ats || 'Direct Portal').toUpperCase())}</div>
        </div>
        <div style="background: var(--bg-raised); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 0.7rem; text-transform: uppercase; font-weight: 700; color: var(--text-secondary);">Open Roles Status</div>
          <div style="font-size: 0.9rem; font-weight: 600; color: var(--ink); margin-top: 4px;">${escapeHtml(item.open_jobs || 'Verified Career Board')}</div>
        </div>
      </div>

      ${rolesModalHtml}

      <div style="margin-bottom: 24px;">
        <h4 style="font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 10px 0;">Official Company Portals &amp; Intelligence</h4>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.board_url || companyUrl)}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-globe" style="color: var(--accent-emerald);"></i> <span>Official Company / Career Portal ↗</span>
          </a>
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.levels_url || '')}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-chart-line" style="color: var(--ink-subtle);"></i> <span>Levels.fyi Salaries ↗</span>
          </a>
          <a class="btn btn-secondary btn-sm" href="${escapeHtml(item.glassdoor_url || '')}" target="_blank" rel="noopener noreferrer">
            <i class="fa fa-star" style="color: var(--ink);"></i> <span>Glassdoor Reviews ↗</span>
          </a>
        </div>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid var(--border-subtle); padding-top: 16px;">
        <button class="btn btn-secondary" onclick="closeCompanyModal()">Close</button>
        <button class="btn btn-primary" onclick="closeCompanyModal(); useCompanyInStudio('${safeJsName}', '${safeJsUrl}')">
          <i class="fa fa-wand-magic-sparkles"></i> Launch CV Studio for ${safeComp} &rarr;
        </button>
      </div>
    `;
  }

  body.innerHTML = html;
  overlay.classList.add("active");
  document.body.style.overflow = "hidden";
}

function closeCompanyModal() {
  const overlay = document.getElementById("companyModalOverlay");
  if (overlay) overlay.classList.remove("active");
  document.body.style.overflow = "";
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeCompanyModal();
});
</script>
</body>
</html>
"""

_APP_CSS_PATH = Path(__file__).resolve().parent / "ui" / "app.css"
STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"
STATIC_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}
HTML_PAGE = HTML_PAGE.replace("/*__APP_CSS__*/", _APP_CSS_PATH.read_text(encoding="utf-8"))
HTML_PAGE = HTML_PAGE.replace("/*__SELECT_JS__*/", (Path(__file__).resolve().parent / "ui" / "select.js").read_text(encoding="utf-8"))


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

        elif path == "/favicon.ico" or path.startswith("/static/"):
            self.serve_static_asset("favicon.ico" if path == "/favicon.ico" else path[len("/static/"):])

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
            role = qs.get("role", [""])[0]
            work_mode = qs.get("work_mode", [""])[0]
            level = qs.get("level", [""])[0]

            data = get_sheet_page(sheet_key=sheet, page=page, limit=limit, query=q, month=month, role=role, work_mode=work_mode, level=level)
            self.send_json(200, data)

        elif path == "/api/roles":
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                page = int(qs.get("page", [1])[0])
            except (ValueError, TypeError):
                page = 1
            try:
                limit = int(qs.get("limit", [25])[0])
            except (ValueError, TypeError):
                limit = 25
            q = qs.get("q", [""])[0]
            discipline = qs.get("discipline", [""])[0]
            work_mode = qs.get("work_mode", [""])[0]
            level = qs.get("level", [""])[0]

            data = get_roles_page(page=page, limit=limit, query=q, discipline=discipline, work_mode=work_mode, level=level)
            self.send_json(200, data)

        elif path == "/api/system_status":
            status_file = Path("data/system_status.json")
            if status_file.is_file():
                self.send_json(200, json.loads(status_file.read_text(encoding="utf-8")))
            else:
                self.send_json(200, {
                    "status": "Healthy & Operational",
                    "schedule": "Every Sunday at 00:00 UTC",
                    "total_roles_indexed": 36288
                })

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

        elif path == "/api/bookmark":
            company = payload.get("company", "").strip()
            title = payload.get("job_title", "").strip()
            url = payload.get("job_url", "").strip()
            notes = payload.get("notes", "Quick bookmarked role").strip()
            if not company:
                self.send_json(400, {"error": "Company is required"})
                return

            try:
                record = record_application(
                    company=company,
                    job_title=title or "Open Role",
                    tailored_tex="% Bookmarked role",
                    metadata={"source": "quick_bookmark"},
                    job_url=url,
                    status="Bookmarked",
                    notes=notes
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

    def serve_static_asset(self, name: str):
        """Serve a file from ui/static (icons, manifest). Only plain filenames that
        exist in that folder are served — no subpaths, so no directory traversal."""
        asset = STATIC_DIR / name
        if "/" in name or "\\" in name or name.startswith(".") or not asset.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ctype = STATIC_TYPES.get(asset.suffix.lower()) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = asset.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

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
