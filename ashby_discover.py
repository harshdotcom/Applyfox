#!/usr/bin/env python3
"""
ashby_discover.py - build a master list of companies that use Ashby ATS.

Pipeline:  discover candidate slugs  ->  validate against Ashby Posting API  ->  export

Ashby Architecture:
  Public Job Board: https://jobs.ashbyhq.com/{slug}
  Public Posting REST API: https://api.ashbyhq.com/posting-api/job-board/{slug}
    200 OK -> Valid active board + returns full job postings array
    404 Not Found -> Inactive or invalid board

State lives in SQLite (ashby_master.db), so runs are resumable and re-runnable.
Outputs: ashby_master.csv, ashby_master.yaml, ashby_master.json
"""
import argparse, csv, json, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None

DB = "data/ashby_master.db" if Path("data").is_dir() else "ashby_master.db"
API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
BOARD_URL = "https://jobs.ashbyhq.com/{slug}"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

RESERVED = {
    "api", "static", "assets", "favicon.ico", "robots.txt", "sitemap.xml",
    "application", "apply", "job", "jobs", "v1", ""
}
SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
ASHBY_URL = re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_\-]+)", re.I)


# ----------------------------------------------------------------- storage
def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS slugs(
        slug TEXT PRIMARY KEY,
        source TEXT,
        status TEXT DEFAULT 'pending',
        name TEXT,
        job_count INTEGER,
        checked_at REAL
    )""")
    return con


def add_slugs(con, slugs, source):
    """slugs can be a set, list, or dict mapping slug -> name."""
    n = 0
    if isinstance(slugs, (set, list)):
        slugs_dict = {s: None for s in slugs}
    elif isinstance(slugs, dict):
        slugs_dict = slugs
    else:
        return 0

    for s, name in slugs_dict.items():
        if not s:
            continue
        s = s.strip().lower()
        if s in RESERVED or not SLUG_OK.match(s):
            continue
        clean_name = name.strip() if name else None
        cur = con.execute("INSERT OR IGNORE INTO slugs(slug, source, name) VALUES(?,?,?)", (s, source, clean_name))
        if cur.rowcount == 0 and clean_name:
            con.execute("UPDATE slugs SET name=? WHERE slug=? AND (name IS NULL OR name=slug)", (clean_name, s))
        n += cur.rowcount
    con.commit()
    return n


# --------------------------------------------------------------- discovery
def extract_slugs(text):
    return {m.group(1).lower() for m in ASHBY_URL.finditer(text) if m.group(1).lower() not in RESERVED}


def from_seed(path):
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Seed file not found: {path}", file=sys.stderr)
        return {}
    raw = p.read_text(encoding="utf-8", errors="ignore")
    slugs = {}

    if path.endswith((".yaml", ".yml")) and yaml:
        for c in (yaml.safe_load(raw) or {}).get("companies", []):
            if isinstance(c, dict) and c.get("ats", "ashby") == "ashby" and c.get("slug"):
                slugs[c["slug"].strip().lower()] = c.get("name")
        return slugs

    if path.endswith(".json"):
        try:
            data = json.loads(raw)
            items = data.get("companies", []) if isinstance(data, dict) else data
            for i in items:
                if isinstance(i, str):
                    slugs[i.strip().lower()] = None
                elif isinstance(i, dict) and i.get("slug"):
                    slugs[i["slug"].strip().lower()] = i.get("name")
            return slugs
        except json.JSONDecodeError:
            pass

    for l in raw.splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        m = ASHBY_URL.search(l)
        if m:
            s = m.group(1).lower()
            if s not in RESERVED:
                slugs[s] = None
        elif SLUG_OK.match(l.lower()) and l.lower() not in RESERVED:
            slugs[l.lower()] = None
    return slugs


def from_github(url):
    text = requests.get(url, headers=UA, timeout=30).text
    found = extract_slugs(text)
    found |= set(re.findall(r"slug\W+([a-z0-9_\-]+)", text, re.I))
    return {s for s in found if s not in RESERVED and SLUG_OK.match(s)}


def from_names(path):
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Names file not found: {path}", file=sys.stderr)
        return {}
    out = set()
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        name = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        if not name:
            continue
        words = name.split()
        out |= {"".join(words), "-".join(words), "".join(words) + "inc",
                "".join(words) + "hq", "".join(words) + "jobs", words[0]}
    return {s for s in out if s not in RESERVED and SLUG_OK.match(s)}


def from_common_crawl(con, max_pages):
    try:
        cols = requests.get("https://index.commoncrawl.org/collinfo.json", headers=UA, timeout=30).json()
    except requests.RequestException as e:
        print(f"Failed to fetch Common Crawl indexes: {e}", file=sys.stderr)
        return 0

    total = 0
    # Search latest crawls + known responsive crawl
    candidate_crawls = [c["id"] for c in cols[:3]] + ["CC-MAIN-2024-38", "CC-MAIN-2026-30"]
    seen = set()
    for cid in candidate_crawls:
        if cid in seen:
            continue
        seen.add(cid)
        api = f"https://index.commoncrawl.org/{cid}-index"
        for p in range(max_pages):
            try:
                resp = requests.get(api, params={"url": "jobs.ashbyhq.com/*", "output": "json",
                                                 "fl": "url", "limit": 1500, "page": p, "collapse": "urlkey"},
                                    headers=UA, timeout=25)
                if resp.status_code != 200:
                    break
                found = extract_slugs(resp.text)
                if not found:
                    break
                total += add_slugs(con, found, "commoncrawl")
                print(f"  [cc] {cid} page {p+1} new total={total}", flush=True)
            except requests.RequestException:
                break
            time.sleep(1)
    return total


# -------------------------------------------------------------- validation
class RateLimiter:
    def __init__(self, per_sec):
        self.gap, self.lock, self.next = 1.0 / per_sec, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            self.next = max(self.next, now) + self.gap
            delay = self.next - self.gap - now
        if delay > 0:
            time.sleep(delay)


def fetch_title(slug):
    try:
        r = requests.get(BOARD_URL.format(slug=slug), headers=UA, timeout=8)
        if r.status_code == 200:
            # 1. Check title tag
            m = re.search(r"<title>(.*?)</title>", r.text, re.I)
            if m:
                t = m.group(1).strip()
                t = re.sub(r"\s*-\s*Jobs.*$", "", t, flags=re.I)
                t = re.sub(r"\s+Jobs\s*$", "", t, flags=re.I).strip()
                if t and t.lower() not in ("jobs", "ashby"):
                    return t
            # 2. Check window.__appData organization name
            m_org = re.search(r'"organization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', r.text)
            if m_org:
                return m_org.group(1).strip()
    except requests.RequestException:
        pass
    return slug.replace("-", " ").replace("_", " ").title()


def check(slug, known_name, limiter, with_jobs):
    limiter.wait()
    url = API.format(slug=slug)

    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=12)
            if r.status_code == 200:
                data = r.json()
                jobs = len([j for j in data.get("jobs", []) if j.get("isListed") is not False]) if with_jobs else None
                name = known_name or fetch_title(slug)
                return slug, "valid", name, jobs
            if r.status_code == 404:
                return slug, "invalid", None, None
            time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(2 ** attempt)

    return slug, "error", None, None


def validate(con, workers, rate, with_jobs, recheck_days):
    cutoff = time.time() - recheck_days * 86400
    todo = con.execute(
        "SELECT slug, name FROM slugs WHERE status IN ('pending','error') "
        "OR (status='valid' AND (checked_at IS NULL OR checked_at < ?))", (cutoff,)
    ).fetchall()

    print(f"Validating {len(todo)} Ashby slugs ({workers} workers, {rate}/s)...")
    limiter, done, ok = RateLimiter(rate), 0, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(check, s, name, limiter, with_jobs) for s, name in todo]
        for f in as_completed(futs):
            slug, status, name, jobs = f.result()
            con.execute(
                "UPDATE slugs SET status=?, name=?, job_count=?, checked_at=? WHERE slug=?",
                (status, name, jobs, time.time(), slug)
            )
            done += 1
            ok += (status == "valid")
            if done % 25 == 0 or done == len(todo):
                con.commit()
                print(f"  {done}/{len(todo)} checked, {ok} valid", flush=True)
    con.commit()


# ------------------------------------------------------------------ export
def export(con, formats):
    rows = con.execute(
        "SELECT name, slug, job_count FROM slugs WHERE status='valid' "
        "ORDER BY lower(coalesce(name, slug))"
    ).fetchall()

    out_dir = Path("data") if Path("data").is_dir() else Path(".")

    if "yaml" in formats:
        lines = ["companies:"] + [
            f"  - {{ name: {json.dumps(n or s)}, ats: ashby, slug: {s} }}" for n, s, _ in rows
        ]
        (out_dir / "ashby_master.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if "csv" in formats:
        with open(out_dir / "ashby_master.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "slug", "open_jobs", "board_url"])
            for n, s, j in rows:
                w.writerow([n or s, s, j if j is not None else "", f"https://jobs.ashbyhq.com/{s}"])

    if "json" in formats:
        data = [
            {
                "name": n or s,
                "slug": s,
                "open_jobs": j,
                "board_url": f"https://jobs.ashbyhq.com/{s}"
            }
            for n, s, j in rows
        ]
        (out_dir / "ashby_master.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    stats = dict(con.execute("SELECT status, COUNT(*) FROM slugs GROUP BY status").fetchall())
    print(f"Exported {len(rows)} valid Ashby companies to {out_dir}/. DB status counts: {stats}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--directory", nargs="?", const="ashby_directory.json", default=None,
                    help="load curated Ashby directory JSON (default: ashby_directory.json)")
    ap.add_argument("--seed", nargs="*", default=[], help="YAML/JSON/TXT files of slugs")
    ap.add_argument("--github", nargs="*", default=[], help="raw URLs to scan for slugs")
    ap.add_argument("--names", help="text file, one company name per line")
    ap.add_argument("--cc", action="store_true", help="discover via Common Crawl")
    ap.add_argument("--max-cc-pages", type=int, default=5, help="pages per crawl")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--jobs", action="store_true", help="fetch live open-job counts")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=8.0, help="max requests/sec")
    ap.add_argument("--recheck-days", type=int, default=30)
    ap.add_argument("--export", nargs="*", default=["yaml", "csv", "json"], choices=["yaml", "csv", "json"])
    a = ap.parse_args()

    con = db()

    # Directory
    if a.directory:
        print(f"directory {a.directory}: +{add_slugs(con, from_seed(a.directory), 'directory')}")

    # Seed files
    for p in a.seed:
        print(f"seed {p}: +{add_slugs(con, from_seed(p), 'seed')}")

    # GitHub URLs
    for u in a.github:
        try:
            print(f"github {u}: +{add_slugs(con, from_github(u), 'github')}")
        except requests.RequestException as e:
            print(f"github {u}: failed ({e})", file=sys.stderr)

    # Names heuristic
    if a.names:
        print(f"names: +{add_slugs(con, from_names(a.names), 'names')}")

    # Common Crawl
    if a.cc:
        try:
            print(f"commoncrawl: +{from_common_crawl(con, a.max_cc_pages)}")
        except requests.RequestException as e:
            print(f"commoncrawl failed ({e})", file=sys.stderr)

    # Validation
    if not a.no_validate:
        validate(con, a.workers, a.rate, a.jobs, a.recheck_days)

    # Export
    export(con, a.export)


if __name__ == "__main__":
    main()

