#!/usr/bin/env python3
"""
gh_discover.py - build a master list of companies that use Greenhouse.

Pipeline:  discover candidate slugs  ->  validate against Greenhouse API  ->  export

Discovery sources (use any combination):
  seed    your own YAML/TXT files with slugs         (--seed companies.yaml)
  cc      Common Crawl index of greenhouse.io URLs   (--cc)        <- biggest source
  github  raw text/YAML/JSON URLs listing slugs      (--github URL [URL ...])
  names   company names -> guessed slugs             (--names names.txt)

Validation: GET https://boards-api.greenhouse.io/v1/boards/{slug}
  200 -> real public board (name returned), 404 -> not a board.

State lives in SQLite (gh_master.db), so the run is resumable and re-runnable.
Only public job boards are discoverable; companies with private boards are not.

Usage examples:
  pip install requests pyyaml
  python gh_discover.py --seed my_companies.yaml --cc --max-cc-pages 200
  python gh_discover.py --names names.txt --workers 8
  python gh_discover.py --export yaml csv          # export only
"""
import argparse, csv, json, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None

DB = "data/gh_master.db" if Path("data").is_dir() else "gh_master.db"
API = "https://boards-api.greenhouse.io/v1/boards/{slug}"
UA = {"User-Agent": "gh-discover/1.0 (research project)"}

# path segments on greenhouse.io that are not company slugs
RESERVED = {"embed", "static", "assets", "api", "v1", "jobs", "job_app", "favicon.ico",
            "robots.txt", "sitemap.xml", "boards", "job-boards", "greenhouse", ""}
SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

GH_URL = re.compile(
    r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?(?:[^\"'\s]*&)?for=)?([A-Za-z0-9_\-]+)",
    re.I)


# ----------------------------------------------------------------- storage
def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS slugs(
        slug TEXT PRIMARY KEY, source TEXT, status TEXT DEFAULT 'pending',
        name TEXT, job_count INTEGER, checked_at REAL)""")
    return con


def add_slugs(con, slugs, source):
    n = 0
    for s in slugs:
        s = s.strip().lower()
        if s in RESERVED or not SLUG_OK.match(s):
            continue
        cur = con.execute("INSERT OR IGNORE INTO slugs(slug, source) VALUES(?,?)", (s, source))
        n += cur.rowcount
    con.commit()
    return n


# --------------------------------------------------------------- discovery
def extract_slugs(text):
    return {m.group(1).lower() for m in GH_URL.finditer(text)}


def from_seed(path):
    """Accepts the YAML format from your file, a plain list of slugs, or JSON."""
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Seed file not found: {path}", file=sys.stderr)
        return set()
    raw = p.read_text(encoding="utf-8", errors="ignore")
    slugs = set()
    if path.endswith((".yaml", ".yml")) and yaml:
        for c in (yaml.safe_load(raw) or {}).get("companies", []):
            if c.get("ats", "greenhouse") == "greenhouse" and c.get("slug"):
                slugs.add(c["slug"])
        return slugs
    if path.endswith(".json"):
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("companies", [])
        return {i if isinstance(i, str) else i.get("slug", "") for i in items}
    return {l.strip() for l in raw.splitlines() if l.strip() and not l.startswith("#")}


def from_github(url):
    """Fetch any raw URL and pull out greenhouse slugs (URLs or `slug: x` entries)."""
    text = requests.get(url, headers=UA, timeout=30).text
    found = extract_slugs(text)
    found |= set(re.findall(r"slug\W+([a-z0-9_\-]+)", text, re.I))
    return found


def from_names(path):
    """Guess slugs from company names: 'Warby Parker' -> warbyparker, warby-parker, warbyparkerinc."""
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Names file not found: {path}", file=sys.stderr)
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        name = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        if not name:
            continue
        words = name.split()
        out |= {"".join(words), "-".join(words), "".join(words) + "inc",
                "".join(words) + "hq", "".join(words) + "jobs", words[0]}
    return out


def from_common_crawl(con, max_pages):
    """Stream greenhouse.io URLs from the newest Common Crawl indexes."""
    cols = requests.get("https://index.commoncrawl.org/collinfo.json", headers=UA, timeout=30).json()
    total = 0
    for col in cols[:3]:  # newest three crawls
        api = col["cdx-api"]
        for host in ("boards.greenhouse.io/*", "job-boards.greenhouse.io/*",
                     "boards.eu.greenhouse.io/*"):
            try:
                r = requests.get(api, params={"url": host, "output": "json", "showNumPages": "true"},
                                 headers=UA, timeout=30)
                pages = r.json().get("pages", 0)
            except (requests.RequestException, ValueError):
                continue
            for p in range(min(pages, max_pages)):
                try:
                    resp = requests.get(api, params={"url": host, "output": "json", "fl": "url",
                                                     "page": p, "collapse": "urlkey"},
                                        headers=UA, timeout=60)
                    if resp.status_code != 200:
                        time.sleep(2)
                        continue
                    total += add_slugs(con, extract_slugs(resp.text), "commoncrawl")
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


def check(slug, limiter, with_jobs):
    limiter.wait()
    for attempt in range(3):
        try:
            r = requests.get(API.format(slug=slug), headers=UA, timeout=15)
            if r.status_code == 200:
                name = r.json().get("name") or slug
                jobs = None
                if with_jobs:
                    limiter.wait()
                    jr = requests.get(API.format(slug=slug) + "/jobs", headers=UA, timeout=20)
                    if jr.ok:
                        jobs = len(jr.json().get("jobs", []))
                return slug, "valid", name, jobs
            if r.status_code == 404:
                return slug, "invalid", None, None
            time.sleep(2 ** attempt)  # 429 / 5xx -> back off
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return slug, "error", None, None


def validate(con, workers, rate, with_jobs, recheck_days):
    cutoff = time.time() - recheck_days * 86400
    todo = [r[0] for r in con.execute(
        "SELECT slug FROM slugs WHERE status IN ('pending','error') "
        "OR (status='valid' AND (checked_at IS NULL OR checked_at < ?))", (cutoff,))]
    print(f"Validating {len(todo)} slugs ({workers} workers, {rate}/s)...")
    limiter, done, ok = RateLimiter(rate), 0, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(check, s, limiter, with_jobs) for s in todo]
        for f in as_completed(futs):
            slug, status, name, jobs = f.result()
            con.execute("UPDATE slugs SET status=?, name=?, job_count=?, checked_at=? WHERE slug=?",
                        (status, name, jobs, time.time(), slug))
            done += 1
            ok += status == "valid"
            if done % 50 == 0:
                con.commit()
                print(f"  {done}/{len(todo)} checked, {ok} valid", flush=True)
    con.commit()


# ------------------------------------------------------------------ export
def export(con, formats):
    rows = con.execute("SELECT name, slug, job_count FROM slugs WHERE status='valid' "
                       "ORDER BY lower(name)").fetchall()
    out_dir = Path("data") if Path("data").is_dir() else Path(".")
    if "yaml" in formats:
        lines = ["companies:"] + [
            f"  - {{ name: {json.dumps(n)}, ats: greenhouse, slug: {s} }}" for n, s, _ in rows]
        (out_dir / "greenhouse_master.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if "csv" in formats:
        with open(out_dir / "greenhouse_master.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "slug", "open_jobs", "board_url"])
            for n, s, j in rows:
                w.writerow([n, s, j if j is not None else "", f"https://boards.greenhouse.io/{s}"])
    if "json" in formats:
        (out_dir / "greenhouse_master.json").write_text(json.dumps(
            [{"name": n, "slug": s, "open_jobs": j} for n, s, j in rows], indent=2), encoding="utf-8")
    stats = dict(con.execute("SELECT status, COUNT(*) FROM slugs GROUP BY status").fetchall())
    print(f"Exported {len(rows)} valid companies to {out_dir}/. DB status counts: {stats}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", nargs="*", default=[], help="YAML/JSON/TXT files of slugs")
    ap.add_argument("--github", nargs="*", default=[], help="raw URLs to scan for slugs")
    ap.add_argument("--names", help="text file, one company name per line")
    ap.add_argument("--cc", action="store_true", help="discover via Common Crawl")
    ap.add_argument("--max-cc-pages", type=int, default=50, help="pages per host per crawl")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--jobs", action="store_true", help="also fetch open-job counts (2x requests)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rate", type=float, default=5.0, help="max requests/sec")
    ap.add_argument("--recheck-days", type=int, default=30)
    ap.add_argument("--export", nargs="*", default=["yaml", "csv", "json"], choices=["yaml", "csv", "json"])
    a = ap.parse_args()

    con = db()
    for p in a.seed:
        print(f"seed {p}: +{add_slugs(con, from_seed(p), 'seed')}")
    for u in a.github:
        try:
            print(f"github {u}: +{add_slugs(con, from_github(u), 'github')}")
        except requests.RequestException as e:
            print(f"github {u}: failed ({e})", file=sys.stderr)
    if a.names:
        print(f"names: +{add_slugs(con, from_names(a.names), 'names')}")
    if a.cc:
        try:
            print(f"commoncrawl: +{from_common_crawl(con, a.max_cc_pages)}")
        except requests.RequestException as e:
            print(f"commoncrawl failed ({e})", file=sys.stderr)
    if not a.no_validate:
        validate(con, a.workers, a.rate, a.jobs, a.recheck_days)
    export(con, a.export)


if __name__ == "__main__":
    main()