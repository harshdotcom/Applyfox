#!/usr/bin/env python3
"""
web_app.py - Zero-dependency, modern local web application & API server for CV tailoring
and job application tracking. Built using Python's standard library http.server.
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

# Cache company names for quick autocomplete
CACHED_COMPANIES: List[str] = []


def get_cached_companies() -> List[str]:
    """Load unique company names from master dataset for UI autocomplete."""
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
<title>🦊 Applyfox | CV Tailor & Job Application Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
  :root {
    --primary: #f97316;
    --primary-dark: #ea580c;
    --primary-light: #ffedd5;
    --airforceblue: #5c8aab;
    --bg: #0f172a;
    --panel-bg: #1e293b;
    --panel-border: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --success: #10b981;
    --info: #38bdf8;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    min-height: 100vh;
  }
  /* Top Navigation */
  header {
    background: rgba(30, 41, 59, 0.95);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--panel-border);
    padding: 14px 28px;
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
    font-size: 1.25rem;
    font-weight: 700;
  }
  .brand-badge {
    background: var(--primary);
    color: #fff;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .nav-tabs {
    display: flex;
    gap: 8px;
  }
  .tab-btn {
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-secondary);
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  .tab-btn:hover {
    color: var(--text-primary);
    background: rgba(255,255,255,0.05);
  }
  .tab-btn.active {
    background: var(--primary);
    color: #fff;
    font-weight: 600;
  }
  /* Main Container */
  main {
    max-width: 1500px;
    margin: 0 auto;
    padding: 24px;
  }
  /* Tailor Grid Layout */
  .tailor-layout {
    display: grid;
    grid-template-columns: 480px 1fr;
    gap: 24px;
    align-items: start;
  }
  @media (max-width: 1100px) {
    .tailor-layout { grid-template-columns: 1fr; }
  }
  /* Card panels */
  .card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--panel-border);
  }
  .card-title {
    font-size: 1.1rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  /* Forms */
  .form-group {
    margin-bottom: 14px;
  }
  label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }
  input[type="text"], input[type="url"], textarea, select {
    width: 100%;
    padding: 10px 12px;
    background: #0f172a;
    border: 1px solid var(--panel-border);
    border-radius: 8px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.9rem;
    transition: border-color 0.2s;
  }
  input[type="text"]:focus, input[type="url"]:focus, textarea:focus, select:focus {
    outline: none;
    border-color: var(--primary);
  }
  textarea {
    resize: vertical;
    min-height: 140px;
    font-family: 'Inter', sans-serif;
  }
  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .referral-box {
    background: rgba(249, 115, 22, 0.08);
    border: 1px dashed rgba(249, 115, 22, 0.3);
    border-radius: 8px;
    padding: 12px;
    margin-top: 10px;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--text-primary);
    user-select: none;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 18px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
    font-size: 0.9rem;
  }
  .btn-primary {
    background: var(--primary);
    color: #fff;
  }
  .btn-primary:hover {
    background: var(--primary-dark);
  }
  .btn-secondary {
    background: #334155;
    color: #fff;
  }
  .btn-secondary:hover {
    background: #475569;
  }
  .btn-success {
    background: var(--success);
    color: #fff;
  }
  .btn-block { width: 100%; }
  /* Action Banner */
  .banner-actions {
    display: flex;
    gap: 10px;
    margin-top: 16px;
  }
  /* Results Preview Tabs */
  .results-tabs {
    display: flex;
    gap: 8px;
    border-bottom: 1px solid var(--panel-border);
    margin-bottom: 16px;
    padding-bottom: 8px;
  }
  .subtab-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 0.88rem;
    font-weight: 500;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
  }
  .subtab-btn.active {
    background: #334155;
    color: var(--text-primary);
    font-weight: 600;
  }
  .preview-frame-container {
    background: #334155;
    border-radius: 8px;
    overflow: hidden;
    height: 750px;
  }
  iframe.preview-frame {
    width: 100%;
    height: 100%;
    border: none;
    background: #fff;
  }
  /* Diff box */
  .diff-box {
    background: #0f172a;
    border-radius: 8px;
    padding: 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    overflow-x: auto;
    max-height: 650px;
  }
  .diff-line { padding: 2px 4px; white-space: pre-wrap; }
  .diff-added { background: rgba(16, 185, 129, 0.2); color: #34d399; }
  .diff-removed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
  .diff-header { color: #94a3b8; font-weight: bold; }
  .diff-chunk { color: #38bdf8; }
  .diff-context { color: #cbd5e1; }
  /* Metadata badges */
  .meta-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }
  .chip {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .chip-score { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
  .chip-archetype { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); }
  .chip-skill { background: #334155; color: #f1f5f9; }
  /* Tracker Table */
  .tracker-table-container {
    overflow-x: auto;
  }
  table.tracker-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    text-align: left;
  }
  table.tracker-table th {
    background: #0f172a;
    padding: 12px;
    color: var(--text-secondary);
    font-weight: 600;
    border-bottom: 1px solid var(--panel-border);
  }
  table.tracker-table td {
    padding: 12px;
    border-bottom: 1px solid var(--panel-border);
    vertical-align: middle;
  }
  table.tracker-table tr:hover td {
    background: rgba(255,255,255,0.02);
  }
  .status-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .status-applied { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
  .status-interviewing { background: rgba(249, 115, 22, 0.2); color: #fb923c; }
  .status-offer { background: rgba(16, 185, 129, 0.2); color: #34d399; }
  .status-rejected { background: rgba(239, 68, 68, 0.2); color: #f87171; }
  .referral-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--primary);
    font-weight: 500;
  }
  /* Notification Toast */
  #toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--panel-bg);
    border: 1px solid var(--success);
    color: #fff;
    padding: 14px 20px;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    display: none;
    z-index: 1000;
  }
  /* Code Editor preview */
  textarea.tex-code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 500px;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <span>🦊 Applyfox</span>
    <span class="brand-badge">CV Studio & Tracker</span>
  </div>
  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchView('tailor')"><i class="fa fa-wand-magic-sparkles"></i> Tailor & Apply</button>
    <button class="tab-btn" onclick="switchView('tracker')"><i class="fa fa-table-list"></i> Application Sheet (<span id="appCount">0</span>)</button>
    <button class="tab-btn" onclick="switchView('base-cv')"><i class="fa fa-file-code"></i> Base main.tex</button>
  </div>
</header>

<main>
  <!-- TAB 1: TAILOR & APPLY -->
  <div id="view-tailor">
    <div class="tailor-layout">
      <!-- Left Column: Input Form -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><i class="fa fa-pen-to-square"></i> Job Application Details</div>
          <span style="font-size: 0.8rem; color: var(--text-secondary);">Candidate: <strong>Harsh Jha</strong></span>
        </div>

        <form id="tailorForm" onsubmit="event.preventDefault(); handleTailor();">
          <div class="form-group">
            <label for="companyName">Target Company Name *</label>
            <input type="text" id="companyName" placeholder="e.g. Stripe, OpenAI, Databricks..." list="companyList" required>
            <datalist id="companyList"></datalist>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="jobTitle">Job Title / Role</label>
              <input type="text" id="jobTitle" placeholder="e.g. Senior Backend Engineer">
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
              <span><i class="fa fa-user-tag" style="color: var(--primary);"></i> I have an Employee Referral for this job</span>
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
            <button type="button" id="btnTailor" class="btn btn-primary" style="flex: 1;" onclick="handleTailor()"><i class="fa fa-wand-magic-sparkles"></i> 1. Tailor CV</button>
            <button type="button" id="btnSaveApp" class="btn btn-success" style="flex: 1;" onclick="handleSaveApplication()"><i class="fa fa-floppy-disk"></i> 2. Save & Track Job</button>
          </div>
        </form>
      </div>

      <!-- Right Column: Tailored Output & Preview -->
      <div class="card" id="resultsCard" style="min-height: 600px;">
        <div class="card-header">
          <div class="card-title"><i class="fa fa-eye"></i> Tailored CV Studio Preview</div>
          <div id="actionDownloadButtons" style="display: none; gap: 8px; flex-wrap: wrap;">
            <button id="btnDownloadPdf" class="btn btn-primary" onclick="downloadPdf()"><i class="fa fa-file-pdf"></i> Download PDF</button>
            <button class="btn btn-secondary" onclick="recompilePdf()"><i class="fa fa-arrows-rotate"></i> Recompile TeX</button>
            <button class="btn btn-secondary" onclick="downloadTex()"><i class="fa fa-download"></i> Download .tex</button>
            <button class="btn btn-secondary" onclick="copyTex()"><i class="fa fa-copy"></i> Copy TeX</button>
          </div>
        </div>

        <div id="emptyState" style="text-align: center; padding: 120px 20px; color: var(--text-secondary);">
          <i class="fa fa-file-invoice" style="font-size: 3rem; margin-bottom: 14px; opacity: 0.4;"></i>
          <h3 style="margin: 0 0 6px 0; color: var(--text-primary);">No CV tailored yet</h3>
          <p style="margin: 0; font-size: 0.9rem;">Fill in the job description on the left and click <strong>Tailor CV</strong> to preview the customized LaTeX CV and match analytics.</p>
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
          <div id="subtab-pdf" style="display: none; height: 800px; background: #525659; border-radius: 6px; overflow: hidden;">
            <iframe id="pdfPreviewFrame" style="width: 100%; height: 100%; border: none;"></iframe>
          </div>

          <!-- Subtab 3: Diffs -->
          <div id="subtab-diff" style="display: none;">
            <div id="diffViewContainer"></div>
          </div>

          <!-- Subtab 4: TeX Code -->
          <div id="subtab-tex" style="display: none;">
            <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.85rem; color: var(--text-secondary);"><i class="fa fa-pencil"></i> You can edit this LaTeX source directly and click <strong>Recompile TeX</strong> to regenerate both previews and the PDF.</span>
              <button class="btn btn-primary" style="padding: 4px 12px; font-size: 0.82rem;" onclick="recompilePdf()"><i class="fa fa-arrows-rotate"></i> Recompile TeX</button>
            </div>
            <textarea id="tailoredTexArea" class="tex-code" style="height: 650px;"></textarea>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 2: APPLICATION TRACKER SHEET -->
  <div id="view-tracker" style="display: none;">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><i class="fa fa-table"></i> Master Job Applications Tracker ("The Sheet")</div>
        <div style="display: flex; gap: 8px;">
          <input type="text" id="trackerSearch" placeholder="Search company or title..." oninput="filterTrackerTable()" style="width: 250px; padding: 6px 10px;">
          <a href="/api/export_csv" class="btn btn-secondary" style="text-decoration: none;"><i class="fa fa-file-csv"></i> Export CSV</a>
        </div>
      </div>

      <div class="tracker-table-container">
        <table class="tracker-table" id="trackerTable">
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

  <!-- TAB 3: BASE CV INSPECTOR -->
  <div id="view-base-cv" style="display: none;">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><i class="fa fa-file-code"></i> Canonical Master CV Template (<code>data/main.tex</code>)</div>
      </div>
      <textarea id="baseTexContent" class="tex-code" style="min-height: 700px;" readonly></textarea>
    </div>
  </div>
</main>

<div id="toast"></div>

<script>
let CURRENT_TAILORED_RESULT = null;
let TRACKED_APPLICATIONS = [];

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadCompaniesAutocomplete();
  loadTrackerData();
  loadBaseTex();
});

function switchView(viewName) {
  document.getElementById("view-tailor").style.display = (viewName === 'tailor') ? 'block' : 'none';
  document.getElementById("view-tracker").style.display = (viewName === 'tracker') ? 'block' : 'none';
  document.getElementById("view-base-cv").style.display = (viewName === 'base-cv') ? 'block' : 'none';

  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  if (viewName === 'tailor') document.querySelectorAll(".tab-btn")[0].classList.add("active");
  if (viewName === 'tracker') {
    document.querySelectorAll(".tab-btn")[1].classList.add("active");
    loadTrackerData();
  }
  if (viewName === 'base-cv') document.querySelectorAll(".tab-btn")[2].classList.add("active");
}

let CURRENT_PDF_PREVIEW_URL = "";

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
      showToast("✓ LaTeX PDF preview loaded");
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

    showToast("✓ LaTeX successfully recompiled!");
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
    datalist.innerHTML = data.map(c => `<option value="${c}"></option>`).join("");
  } catch (e) {
    console.error("Failed to load companies", e);
  }
}

async function loadBaseTex() {
  try {
    const res = await fetch("/api/base_tex");
    const text = await res.text();
    document.getElementById("baseTexContent").value = text;
  } catch(e) {}
}

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
      return;
    }

    CURRENT_TAILORED_RESULT = data;

    // Display Output
    document.getElementById("emptyState").style.display = "none";
    document.getElementById("outputContent").style.display = "block";
    document.getElementById("actionDownloadButtons").style.display = "flex";
    document.getElementById("btnSaveApp").disabled = false;

    // Set Metadata
    document.getElementById("scoreBadge").textContent = `Match: ${data.analysis.match_score}%`;
    document.getElementById("archetypeBadge").textContent = `Archetype: ${data.analysis.archetype.replace('_', ' ')}`;

    const chips = data.analysis.top_priorities.map(s => `<span class="chip chip-skill">${s}</span>`).join("");
    document.getElementById("prioritySkillsChips").innerHTML = chips;

    // Render Preview Iframe
    const frame = document.getElementById("cvPreviewFrame");
    frame.srcdoc = data.preview_html;

    // Set Diff HTML
    document.getElementById("diffViewContainer").innerHTML = `
      <div style="margin-bottom: 16px;">
        <h4 style="color: var(--primary); margin: 0 0 6px 0;">PROFILE Changes</h4>
        <div class="diff-box">${renderDiffLines(data.profile_diff)}</div>
      </div>
      <div style="margin-bottom: 16px;">
        <h4 style="color: var(--primary); margin: 0 0 6px 0;">TECHNICAL SKILLS Changes</h4>
        <div class="diff-box">${renderDiffLines(data.skills_diff)}</div>
      </div>
      <div>
        <h4 style="color: var(--primary); margin: 0 0 6px 0;">PROJECTS Changes</h4>
        <div class="diff-box">${renderDiffLines(data.projects_diff)}</div>
      </div>
    `;

    // Set TeX Source
    document.getElementById("tailoredTexArea").value = data.tailored_tex;
    document.getElementById("pdfPreviewFrame").src = "about:blank";

    showToast(`✓ Successfully tailored CV for ${company}! Click 'Save & Track Job' to record it.`);
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
  return text.replace(/[&<>"']/g, m => map[m]);
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
      showToast(`✓ Recorded application ${data.application_id} in sheet!`);
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
      ? `<span class="referral-tag"><i class="fa fa-user-check"></i> ${a.referral_name || "Referred"}</span>`
      : `<span style="color: #64748b;">None</span>`;

    const skillsHtml = (a.key_skills_matched || []).slice(0, 4).map(s => `<span class="chip chip-skill" style="font-size:0.7rem; padding: 2px 6px;">${s}</span>`).join(" ");

    return `
      <tr>
        <td style="white-space: nowrap; font-size: 0.8rem; color: #94a3b8;">${a.applied_date || "-"}</td>
        <td><strong>${a.company || "-"}</strong></td>
        <td>${a.job_title || "-"}</td>
        <td>
          <select onchange="updateStatus('${a.application_id}', this.value)" style="padding: 4px 8px; font-size: 0.8rem; width: auto; background: #1e293b; border-color: #475569;">
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
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.78rem;" onclick="viewArchivedCV('${a.application_id}')"><i class="fa fa-eye"></i> View CV</button>
          <a class="btn btn-primary" style="padding: 4px 8px; font-size: 0.78rem; text-decoration: none;" href="/api/application/${a.application_id}/download_pdf" download><i class="fa fa-file-pdf"></i> PDF</a>
          <a class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.78rem; text-decoration: none;" href="/api/application/${a.application_id}/download_tex"><i class="fa fa-download"></i> .tex</a>
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
    document.getElementById("btnSaveApp").disabled = true;

    document.getElementById("scoreBadge").textContent = `Match: ${data.match_score}%`;
    document.getElementById("archetypeBadge").textContent = `Archetype: ${(data.metadata?.archetype || 'SDE').replace('_', ' ')}`;
    document.getElementById("prioritySkillsChips").innerHTML = (data.key_skills_matched || []).map(s => `<span class="chip chip-skill">${s}</span>`).join("");

    const frame = document.getElementById("cvPreviewFrame");
    frame.srcdoc = data.preview_html || "Preview not available";
    document.getElementById("tailoredTexArea").value = data.tailored_tex || "";

    // Set PDF preview frame to direct compiled PDF
    document.getElementById("pdfPreviewFrame").src = `/api/application/${appId}/preview_pdf`;

    showToast(`Loaded archived CV for ${data.company} (${appId})`);
  } catch (e) {
    showToast("Error loading archived CV: " + e.message);
  }
}

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
    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Compiling PDF...';
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
    showToast("✓ Genuine Overleaf-grade PDF downloaded successfully!");
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
            self.send_json(404, {"error": "Not Found"})

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

                # Render HTML preview of tailored CV
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
                    self.send_json(500, {"error": f"LaTeX Compilation Failed:\n{msg}"})
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
                    self.send_json(500, {"error": f"LaTeX Preview Compilation Failed:\n{msg}"})
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
    print(f" 🦊 Applyfox CV Studio & Job Application Tracker Online")
    print(f" Access URL: http://127.0.0.1:{port}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()

