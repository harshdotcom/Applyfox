#!/usr/bin/env python3
"""
html_preview.py - Converts LaTeX CV to faithful HTML/CSS paper-accurate resume preview
and generates interactive side-by-side visual diffs and client-side PDF export.
"""

import html
import re
from typing import Any, Dict, List, Optional, Tuple


def extract_braced_content(text: str, start_index: int) -> Tuple[str, int]:
    """Given text and the index of an opening brace '{', find the matching closing brace '}'."""
    depth = 0
    content_start = start_index + 1
    for i in range(start_index, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[content_start:i], i + 1
    return text[content_start:], len(text)


def extract_n_braced_args(text: str, start_index: int, n: int) -> Tuple[List[str], int]:
    """Extract N consecutive braced arguments starting from start_index."""
    args = []
    idx = start_index
    for _ in range(n):
        brace_pos = text.find('{', idx)
        if brace_pos == -1:
            break
        arg, idx = extract_braced_content(text, brace_pos)
        args.append(arg.strip())
    return args, idx


def extract_resume_items(text: str) -> List[str]:
    """Accurately extract all \\resumeItem{...} contents handling arbitrary nested braces."""
    items = []
    marker = r"\resumeItem"
    idx = 0
    while True:
        pos = text.find(marker, idx)
        if pos == -1:
            break
        brace_pos = text.find('{', pos + len(marker))
        if brace_pos == -1:
            break
        content, end_pos = extract_braced_content(text, brace_pos)
        cleaned = content.strip()
        if cleaned:
            items.append(cleaned)
        idx = end_pos
    return items


def clean_latex_inline(text: str) -> str:
    """Accurately convert inline LaTeX formatting to HTML without breaking on nested commands."""
    def replace_command(s: str, cmd: str, open_tag: str, close_tag: str) -> str:
        idx = 0
        while True:
            pos = s.find(cmd, idx)
            if pos == -1:
                break
            b_start = s.find('{', pos + len(cmd))
            if b_start == -1:
                break
            depth = 0
            b_end = -1
            for i in range(b_start, len(s)):
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        b_end = i
                        break
            if b_end != -1:
                inner = s[b_start + 1 : b_end]
                inner_cleaned = clean_latex_inline(inner)
                s = s[:pos] + open_tag + inner_cleaned + close_tag + s[b_end + 1:]
                idx = pos + len(open_tag) + len(inner_cleaned) + len(close_tag)
            else:
                idx = pos + len(cmd)
        return s

    def replace_href(s: str) -> str:
        idx = 0
        while True:
            pos = s.find(r'\href', idx)
            if pos == -1:
                break
            b1_start = s.find('{', pos + 5)
            if b1_start == -1:
                break
            depth = 0
            b1_end = -1
            for i in range(b1_start, len(s)):
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        b1_end = i
                        break
            if b1_end == -1:
                break
            url = s[b1_start + 1 : b1_end]

            b2_start = s.find('{', b1_end + 1)
            if b2_start == -1:
                break
            depth = 0
            b2_end = -1
            for i in range(b2_start, len(s)):
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        b2_end = i
                        break
            if b2_end == -1:
                break
            text_inner = s[b2_start + 1 : b2_end]
            text_cleaned = clean_latex_inline(text_inner)
            replacement = f'<a href="{url}" target="_blank" class="cv-link">{text_cleaned}</a>'
            s = s[:pos] + replacement + s[b2_end + 1:]
            idx = pos + len(replacement)
        return s

    s = replace_href(text)
    s = replace_command(s, r'\textbf', '<strong>', '</strong>')
    s = replace_command(s, r'\textit', '<em>', '</em>')
    s = replace_command(s, r'\small', '', '')
    s = s.replace(r'\&', '&').replace(r'\%', '%').replace(r'\_', '_').replace(r'\#', '#')
    s = s.replace(r'\$', '$').replace('~', ' ').replace('---', '—').replace('--', '–')
    s = re.sub(r'\\vspace\{[^}]*\}', '', s)
    s = re.sub(r'\\color\{[^}]*\}', '', s)
    s = re.sub(r'\\item\[[^\]]*\]', '', s)
    s = re.sub(r'\\item\b', '', s)
    s = s.replace(r'\textbullet', '')
    return s.strip()


def parse_latex_to_resume_structure(tex_content: str) -> Dict[str, Any]:
    """Parse sections from LaTeX into a structured dictionary with 100% brace safety."""
    # 1. Header Contact
    phone = "+91 7060286069"
    email = "harshj92002@gmail.com"
    linkedin = "https://www.linkedin.com/in/harshjha-iiti/"
    github = "https://github.com/jhaharsh03"
    leetcode = "https://leetcode.com/u/harshdotcom/"

    # Extract sections by \section
    sections = {}
    section_regex = re.compile(r'\\section\{\\color\{[^}]+\}([^}]+)\}(.*?)(?=\\section|\\end\{document\})', re.DOTALL)
    for match in section_regex.finditer(tex_content):
        sec_name = match.group(1).strip()
        sec_body = match.group(2).strip()
        sections[sec_name] = sec_body

    # 1. Profile Items
    profile_raw = extract_resume_items(sections.get("PROFILE", ""))
    profile_items = [clean_latex_inline(it) for it in profile_raw if it.strip()]

    # 2. Technical Skills
    skills_raw = extract_resume_items(sections.get("TECHNICAL SKILLS", ""))
    skills_items = []
    for s in skills_raw:
        pos = s.find(r"\textbf{")
        if pos != -1:
            cat_inner, end_pos = extract_braced_content(s, pos + 7)
            cat_name = clean_latex_inline(cat_inner).rstrip(":")
            rest = clean_latex_inline(s[end_pos:])
            skills_items.append({"category": cat_name, "skills": rest})
        else:
            skills_items.append({"category": "Skills", "skills": clean_latex_inline(s)})

    # 3. Education
    edu_sec = sections.get("EDUCATION", "")
    education_subheadings = []
    sub_marker = r"\resumeSubheading"
    idx = 0
    while True:
        pos = edu_sec.find(sub_marker, idx)
        if pos == -1:
            break
        args, end_idx = extract_n_braced_args(edu_sec, pos + len(sub_marker), 4)
        if len(args) == 4:
            education_subheadings.append({
                "institution": clean_latex_inline(args[0]),
                "location": clean_latex_inline(args[1]),
                "degree": clean_latex_inline(args[2]),
                "dates": clean_latex_inline(args[3]),
            })
        idx = end_idx if end_idx > pos else pos + len(sub_marker)

    # 4. Work Experience
    work_sec = sections.get("WORK EXPERIENCE", "")
    work_subheadings = []
    idx = 0
    while True:
        pos = work_sec.find(sub_marker, idx)
        if pos == -1:
            break
        args, end_idx = extract_n_braced_args(work_sec, pos + len(sub_marker), 4)
        next_sub = work_sec.find(sub_marker, end_idx)
        next_end = work_sec.find(r"\resumeSubHeadingListEnd", end_idx)
        limit = len(work_sec)
        if next_sub != -1 and next_end != -1:
            limit = min(next_sub, next_end)
        elif next_sub != -1:
            limit = next_sub
        elif next_end != -1:
            limit = next_end

        bullets = [clean_latex_inline(b) for b in extract_resume_items(work_sec[end_idx:limit])]
        if len(args) == 4:
            work_subheadings.append({
                "title": clean_latex_inline(args[0]),
                "dates": clean_latex_inline(args[1]),
                "company": clean_latex_inline(args[2]),
                "location": clean_latex_inline(args[3]),
                "bullets": bullets
            })
        idx = limit

    # 5. Projects
    proj_sec = sections.get("PROJECTS", "")
    projects = []
    proj_marker = r"\resumeProjectHeading"
    idx = 0
    while True:
        pos = proj_sec.find(proj_marker, idx)
        if pos == -1:
            break
        args, end_idx = extract_n_braced_args(proj_sec, pos + len(proj_marker), 2)
        next_proj = proj_sec.find(proj_marker, end_idx)
        next_end = proj_sec.find(r"\resumeSubHeadingListEnd", end_idx)
        limit = len(proj_sec)
        if next_proj != -1 and next_end != -1:
            limit = min(next_proj, next_end)
        elif next_proj != -1:
            limit = next_proj
        elif next_end != -1:
            limit = next_end

        bullets = [clean_latex_inline(b) for b in extract_resume_items(proj_sec[end_idx:limit])]
        raw_heading = args[0] if len(args) > 0 else ""
        link_html = clean_latex_inline(args[1]) if len(args) > 1 else ""

        title = raw_heading
        tech_stack = ""
        if "$|$" in raw_heading:
            parts = raw_heading.split("$|$")
            title = clean_latex_inline(parts[0])
            tech_stack = clean_latex_inline(parts[1])
        else:
            title = clean_latex_inline(raw_heading)

        projects.append({
            "title": title,
            "tech_stack": tech_stack,
            "link_html": link_html,
            "bullets": bullets
        })
        idx = limit

    # 6. Certifications
    cert_raw = extract_resume_items(sections.get("CERTIFICATIONS", ""))
    certifications = [clean_latex_inline(it) for it in cert_raw if it.strip()]

    # 7. Achievements
    achieve_raw = extract_resume_items(sections.get("ACHIEVEMENTS", ""))
    achievements = [clean_latex_inline(it) for it in achieve_raw if it.strip()]

    return {
        "name": "Harsh Jha",
        "phone": phone,
        "email": email,
        "linkedin": linkedin,
        "github": github,
        "leetcode": leetcode,
        "profile": profile_items,
        "education": education_subheadings,
        "skills": skills_items,
        "work": work_subheadings,
        "projects": projects,
        "certifications": certifications,
        "achievements": achievements,
    }


def render_resume_to_html(tex_content: str, title_badge: str = "Preview") -> str:
    """Generate a clean, paper-accurate HTML/CSS view of the LaTeX CV with PDF print support."""
    data = parse_latex_to_resume_structure(tex_content)

    profile_html = "\n".join([f'<li>{item}</li>' for item in data["profile"]])

    skills_html = "\n".join([
        f'<li><strong>{s["category"]}:</strong> {s["skills"]}</li>'
        for s in data["skills"]
    ])

    edu_html = ""
    for edu in data["education"]:
        edu_html += f"""
        <div class="subheading-row">
            <div class="row-left"><strong>{edu["institution"]}</strong></div>
            <div class="row-right"><strong>{edu["location"]}</strong></div>
        </div>
        <div class="subheading-row sub-row">
            <div class="row-left"><em>{edu["degree"]}</em></div>
            <div class="row-right"><em>{edu["dates"]}</em></div>
        </div>
        """

    work_html = ""
    for w in data["work"]:
        bullets = "\n".join([f'<li>{b}</li>' for b in w["bullets"]])
        work_html += f"""
        <div class="entry-block">
            <div class="subheading-row">
                <div class="row-left"><strong>{w["title"]}</strong></div>
                <div class="row-right"><strong>{w["dates"]}</strong></div>
            </div>
            <div class="subheading-row sub-row">
                <div class="row-left"><em>{w["company"]}</em></div>
                <div class="row-right"><em>{w["location"]}</em></div>
            </div>
            <ul class="resume-list">
                {bullets}
            </ul>
        </div>
        """

    proj_html = ""
    for p in data["projects"]:
        bullets = "\n".join([f'<li>{b}</li>' for b in p["bullets"]])
        proj_html += f"""
        <div class="entry-block">
            <div class="project-header-row">
                <div class="proj-left"><strong>{p["title"]}</strong> <span class="pipe-sep">|</span> <span class="tech-tag">{p["tech_stack"]}</span></div>
                <div class="proj-right">{p["link_html"]}</div>
            </div>
            <ul class="resume-list">
                {bullets}
            </ul>
        </div>
        """

    certs_html = "\n".join([f'<li>{c}</li>' for c in data["certifications"]])
    achieve_html = "\n".join([f'<li>{a}</li>' for a in data["achievements"]])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harsh Jha - CV ({title_badge})</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
  :root {{
    --airforceblue: #5c8aab;
    --text-color: #000000;
    --paper-bg: #ffffff;
    --link-color: #000000;
    --line-color: #000000;
  }}
  @page {{
    size: letter portrait;
    margin: 0.35in 0.45in;
  }}
  * {{
    box-sizing: border-box;
  }}
  body {{
    background: #e5e7eb;
    margin: 0;
    padding: 16px 8px;
    font-family: 'Times New Roman', Times, Cambria, Georgia, serif;
    color: var(--text-color);
    line-height: 1.25;
    font-size: 10pt;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  .paper-page {{
    background: var(--paper-bg);
    max-width: 8.5in;
    min-height: 11in;
    margin: 0 auto;
    padding: 0.4in 0.5in;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    box-sizing: border-box;
  }}
  .header-block {{
    text-align: center;
    margin-bottom: 6px;
  }}
  .header-name {{
    font-size: 20pt;
    font-weight: bold;
    letter-spacing: 0.5px;
    margin: 0 0 4px 0;
  }}
  .header-contacts {{
    font-size: 9.5pt;
    color: #111;
  }}
  .header-contacts a, .cv-link {{
    color: var(--text-color);
    text-decoration: none;
  }}
  .header-contacts a:hover, .cv-link:hover {{
    text-decoration: underline;
  }}
  .contact-sep {{
    margin: 0 4px;
    color: #666;
  }}
  .section-title {{
    color: var(--airforceblue);
    font-size: 11pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 10px 0 2px 0;
    border-bottom: 1px solid #111;
    padding-bottom: 2px;
  }}
  ul.resume-list {{
    margin: 2px 0 5px 0;
    padding-left: 18px;
  }}
  ul.resume-list li {{
    margin-bottom: 2.5px;
    font-size: 9.8pt;
    line-height: 1.28;
  }}
  .subheading-row, .project-header-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 9.8pt;
    margin-top: 3px;
  }}
  .sub-row {{
    margin-top: 1px;
    margin-bottom: 2px;
  }}
  .row-left {{
    text-align: left;
  }}
  .row-right {{
    text-align: right;
    white-space: nowrap;
  }}
  .pipe-sep {{
    color: #333;
    margin: 0 3px;
  }}
  .tech-tag {{
    font-style: italic;
    color: #111;
  }}
  .entry-block {{
    margin-bottom: 5px;
  }}
  @media print {{
    body {{
      background: none !important;
      padding: 0 !important;
      margin: 0 !important;
    }}
    .paper-page {{
      box-shadow: none !important;
      padding: 0.25in 0.35in !important;
      max-width: 100% !important;
      min-height: auto !important;
      margin: 0 !important;
    }}
  }}
</style>
</head>
<body>

<div class="paper-page" id="cvPaperDocument">
  <!-- HEADER -->
  <div class="header-block">
    <div class="header-name">{data["name"]}</div>
    <div class="header-contacts">
      <i class="fa fa-phone"></i> {data["phone"]}
      <span class="contact-sep">~</span>
      <i class="fa fa-envelope"></i> <a href="mailto:{data["email"]}">{data["email"]}</a>
      <span class="contact-sep">~</span>
      <i class="fab fa-linkedin"></i> <a href="{data["linkedin"]}" target="_blank">LinkedIn</a>
      <span class="contact-sep">~</span>
      <i class="fab fa-github"></i> <a href="{data["github"]}" target="_blank">GitHub</a>
      <span class="contact-sep">~</span>
      <i class="fa fa-code"></i> <a href="{data["leetcode"]}" target="_blank">LeetCode</a>
    </div>
  </div>

  <!-- PROFILE -->
  <div class="section-title">PROFILE</div>
  <ul class="resume-list">
    {profile_html}
  </ul>

  <!-- EDUCATION -->
  <div class="section-title">EDUCATION</div>
  {edu_html}

  <!-- TECHNICAL SKILLS -->
  <div class="section-title">TECHNICAL SKILLS</div>
  <ul class="resume-list">
    {skills_html}
  </ul>

  <!-- WORK EXPERIENCE -->
  <div class="section-title">WORK EXPERIENCE</div>
  {work_html}

  <!-- PROJECTS -->
  <div class="section-title">PROJECTS</div>
  {proj_html}

  <!-- CERTIFICATIONS -->
  <div class="section-title">CERTIFICATIONS</div>
  <ul class="resume-list">
    {certs_html}
  </ul>

  <!-- ACHIEVEMENTS -->
  <div class="section-title">ACHIEVEMENTS</div>
  <ul class="resume-list">
    {achieve_html}
  </ul>
</div>

<script>
window.generateAndDownloadPdf = function(filename) {{
  const elem = document.getElementById("cvPaperDocument");
  const opt = {{
    margin: [0.3, 0.3, 0.3, 0.3],
    filename: filename || "Harsh_Jha_CV.pdf",
    image: {{ type: "jpeg", quality: 0.99 }},
    html2canvas: {{ scale: 2.5, useCORS: true, letterRendering: true }},
    jsPDF: {{ unit: "in", format: "letter", orientation: "portrait" }}
  }};
  if (typeof html2pdf !== "undefined") {{
    return html2pdf().set(opt).from(elem).save();
  }} else {{
    window.print();
  }}
}};
</script>

</body>
</html>
"""


def render_diff_html(diff_text: str, title: str = "CV Modifications Diff") -> str:
    """Format unified diff into a beautiful colored HTML diff view."""
    lines = diff_text.splitlines()
    html_lines = []

    for line in lines:
        escaped = html.escape(line)
        if line.startswith("+++") or line.startswith("---"):
            html_lines.append(f'<div class="diff-line diff-header">{escaped}</div>')
        elif line.startswith("@@"):
            html_lines.append(f'<div class="diff-line diff-chunk">{escaped}</div>')
        elif line.startswith("+"):
            html_lines.append(f'<div class="diff-line diff-added">{escaped}</div>')
        elif line.startswith("-"):
            html_lines.append(f'<div class="diff-line diff-removed">{escaped}</div>')
        else:
            html_lines.append(f'<div class="diff-line diff-context">{escaped}</div>')

    content = "\n".join(html_lines)
    return f"""
    <div class="diff-container">
        <h4 style="margin: 0 0 10px 0; color: #1e293b;">{title}</h4>
        <div class="diff-box">
            {content}
        </div>
    </div>
    """
