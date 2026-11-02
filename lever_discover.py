#!/usr/bin/env python3
"""
lever_discover.py - build a master list of companies that use Lever ATS.

Pipeline:  discover candidate slugs  ->  validate against Lever API / Boards  ->  export

Discovery sources (use any combination):
  directory   built-in or downloaded directory.json      (--directory [path])
  seed        your own YAML/JSON/TXT files with slugs    (--seed companies.yaml)
  cc          Common Crawl index of jobs.lever.co URLs   (--cc)
  github      raw text/YAML/JSON URLs listing slugs      (--github URL [URL ...])
  names       company names -> guessed slugs             (--names names.txt)

Validation:
  Primary US: https://api.lever.co/v0/postings/{slug}?mode=json
  Fallback EU: https://api.eu.lever.co/v0/postings/{slug}?mode=json
  200 -> real public Lever board (and returns job postings count)
  404 -> not a board.

State lives in SQLite (lever_master.db), so runs are resumable and re-runnable.
Outputs: lever_master.csv, lever_master.yaml, lever_master.json
"""
import argparse, csv, json, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None

DB = "data/lever_master.db" if Path("data").is_dir() else "lever_master.db"
API_US = "https://api.lever.co/v0/postings/{slug}?mode=json"
API_EU = "https://api.eu.lever.co/v0/postings/{slug}?mode=json"
BOARD_US = "https://jobs.lever.co/{slug}"
BOARD_EU = "https://jobs.eu.lever.co/{slug}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

RESERVED = {
    "v0", "postings", "embed", "static", "assets", "api", "v1", "jobs", "job",
    "favicon.ico", "robots.txt", "sitemap.xml", "apply", "confirmation", ""
}
SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

LEVER_URL = re.compile(
    r"(?:jobs|api)(?:\.eu)?\.lever\.co/(?:v0/postings/)?([A-Za-z0-9_\-]+)",
    re.I
)


# ----------------------------------------------------------------- storage
def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS slugs(
        slug TEXT PRIMARY KEY,
        source TEXT,
        status TEXT DEFAULT 'pending',
        name TEXT,
        job_count INTEGER,
        region TEXT DEFAULT 'us',
        checked_at REAL
    )""")
    return con


def add_slugs(con, slugs, source):
    """Add slugs to database. Accepts a set, list, or dict mapping slug -> name."""
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
        cur = con.execute("INSERT OR IGNORE INTO slugs(slug, source, name) VALUES(?,?,?)", (s, source, name))
        if cur.rowcount == 0 and name:
            con.execute("UPDATE slugs SET name=? WHERE slug=? AND (name IS NULL OR name=slug)", (name, s))
        n += cur.rowcount
    con.commit()
    return n


# --------------------------------------------------------------- discovery
def extract_slugs(text):
    return {m.group(1).lower() for m in LEVER_URL.finditer(text) if m.group(1).lower() not in RESERVED}


def from_seed(path):
    """Accepts YAML, JSON directory (or list), or TXT with one slug/URL per line."""
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
            if isinstance(c, dict) and c.get("ats", "lever") == "lever" and c.get("slug"):
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

    # TXT or URL list fallback
    for l in raw.splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        m = LEVER_URL.search(l)
        if m:
            s = m.group(1).lower()
            if s not in RESERVED:
                slugs[s] = None
        elif SLUG_OK.match(l.lower()) and l.lower() not in RESERVED:
            slugs[l.lower()] = None
    return slugs


def from_github(url):
    """Fetch raw URL and extract Lever slugs."""
    text = requests.get(url, headers=UA, timeout=30).text
    found = extract_slugs(text)
    found |= set(re.findall(r"slug\W+([a-z0-9_\-]+)", text, re.I))
    return {s for s in found if s not in RESERVED}


def from_names(path):
    """Guess slugs from company names."""
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
    """Stream lever.co URLs from Common Crawl index."""
    try:
        cols = requests.get("https://index.commoncrawl.org/collinfo.json", headers=UA, timeout=30).json()
    except requests.RequestException as e:
        print(f"Failed to fetch Common Crawl indexes: {e}", file=sys.stderr)
        return 0

    total = 0
    for col in cols[:3]:
        api = col["cdx-api"]
        for host in ("jobs.lever.co/*", "jobs.eu.lever.co/*"):
            try:
                r = requests.get(api, params={"url": host, "output": "json", "showNumPages": "true"},
                                 headers=UA, timeout=20)
                pages = r.json().get("pages", 0)
            except (requests.RequestException, ValueError):
                continue
            for p in range(min(pages, max_pages)):
                try:
                    resp = requests.get(api, params={"url": host, "output": "json", "fl": "url",
                                                     "page": p, "collapse": "urlkey"},
                                        headers=UA, timeout=45)
                    if resp.status_code != 200:
                        continue
                    found = extract_slugs(resp.text)
                    total += add_slugs(con, found, "commoncrawl")
                    print(f"  [cc] {col['id']} {host} page {p+1}/{pages}  new total={total}", flush=True)
                except requests.RequestException as e:
                    print(f"  [cc] {col['id']} {host} page {p+1}/{pages} skipped ({e})", flush=True)
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


def fetch_title(slug, region):
    board_url = BOARD_EU.format(slug=slug) if region == "eu" else BOARD_US.format(slug=slug)
    try:
        r = requests.get(board_url, headers=UA, timeout=8)
        if r.status_code == 200:
            m = re.search(r"<title>(.*?)</title>", r.text, re.I)
            if m:
                t = m.group(1).strip()
                t = re.sub(r"\s*-\s*Jobs.*$", "", t, flags=re.I)
                t = re.sub(r"\s+jobs$", "", t, flags=re.I).strip()
                if t:
                    return t
    except requests.RequestException:
        pass
    return slug.replace("-", " ").replace("_", " ").title()


def check(slug, known_name, limiter, with_jobs):
    limiter.wait()
    for attempt in range(3):
        try:
            # 1. Try US API endpoint
            r = requests.get(API_US.format(slug=slug), headers=UA, timeout=12)
            if r.status_code == 200:
                data = r.json()
                jobs = len(data) if (with_jobs and isinstance(data, list)) else None
                name = known_name or fetch_title(slug, "us")
                return slug, "valid", name, jobs, "us"

            if r.status_code == 404:
                # 2. Check EU API endpoint
                limiter.wait()
                r_eu = requests.get(API_EU.format(slug=slug), headers=UA, timeout=12)
                if r_eu.status_code == 200:
                    data = r_eu.json()
                    jobs = len(data) if (with_jobs and isinstance(data, list)) else None
                    name = known_name or fetch_title(slug, "eu")
                    return slug, "valid", name, jobs, "eu"
                if r_eu.status_code == 404:
                    return slug, "invalid", None, None, "us"

            time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(2 ** attempt)

    return slug, "error", None, None, "us"


def validate(con, workers, rate, with_jobs, recheck_days):
    cutoff = time.time() - recheck_days * 86400
    todo = con.execute(
        "SELECT slug, name FROM slugs WHERE status IN ('pending','error') "
        "OR (status='valid' AND (checked_at IS NULL OR checked_at < ?))", (cutoff,)
    ).fetchall()

    print(f"Validating {len(todo)} Lever slugs ({workers} workers, {rate}/s)...")
    limiter, done, ok = RateLimiter(rate), 0, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(check, s, name, limiter, with_jobs) for s, name in todo]
        for f in as_completed(futs):
            slug, status, name, jobs, region = f.result()
            con.execute(
                "UPDATE slugs SET status=?, name=?, job_count=?, region=?, checked_at=? WHERE slug=?",
                (status, name, jobs, region, time.time(), slug)
            )
            done += 1
            ok += (status == "valid")
            if done % 50 == 0 or done == len(todo):
                con.commit()
                print(f"  {done}/{len(todo)} checked, {ok} valid", flush=True)
    con.commit()


# ------------------------------------------------------------------ export
def export(con, formats):
    rows = con.execute(
        "SELECT name, slug, job_count, region FROM slugs WHERE status='valid' "
        "ORDER BY lower(coalesce(name, slug))"
    ).fetchall()

    out_dir = Path("data") if Path("data").is_dir() else Path(".")

    if "yaml" in formats:
        lines = ["companies:"] + [
            f"  - {{ name: {json.dumps(n or s)}, ats: lever, slug: {s}, region: {r} }}" for n, s, _, r in rows
        ]
        (out_dir / "lever_master.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if "csv" in formats:
        with open(out_dir / "lever_master.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "slug", "open_jobs", "region", "board_url"])
            for n, s, j, r in rows:
                base = "https://jobs.eu.lever.co" if r == "eu" else "https://jobs.lever.co"
                w.writerow([n or s, s, j if j is not None else "", r, f"{base}/{s}"])

    if "json" in formats:
        data = [
            {
                "name": n or s,
                "slug": s,
                "open_jobs": j,
                "region": r,
                "board_url": f"https://jobs.eu.lever.co/{s}" if r == "eu" else f"https://jobs.lever.co/{s}"
            }
            for n, s, j, r in rows
        ]
        (out_dir / "lever_master.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    stats = dict(con.execute("SELECT status, COUNT(*) FROM slugs GROUP BY status").fetchall())
    print(f"Exported {len(rows)} valid Lever companies to {out_dir}/. DB status counts: {stats}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--directory", nargs="?", const="lever_directory.json", default=None,
                    help="load curated directory JSON (default: lever_directory.json)")
    ap.add_argument("--seed", nargs="*", default=[], help="YAML/JSON/TXT files of slugs")
    ap.add_argument("--github", nargs="*", default=[], help="raw URLs to scan for slugs")
    ap.add_argument("--names", help="text file, one company name per line")
    ap.add_argument("--cc", action="store_true", help="discover via Common Crawl")
    ap.add_argument("--max-cc-pages", type=int, default=50, help="pages per host per crawl")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--jobs", action="store_true", help="fetch live open-job counts")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=6.0, help="max requests/sec")
    ap.add_argument("--recheck-days", type=int, default=30)
    ap.add_argument("--export", nargs="*", default=["yaml", "csv", "json"], choices=["yaml", "csv", "json"])
    a = ap.parse_args()

    con = db()

    # Built-in or specified directory
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

