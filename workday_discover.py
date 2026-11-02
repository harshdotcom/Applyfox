#!/usr/bin/env python3
"""
workday_discover.py - build a master list of companies that use Workday ATS.

Pipeline:  discover candidate career sites  ->  validate against Workday CXS API  ->  export

Workday Architecture:
  Each career site is defined by:
    tenant      company identifier (e.g. adobe, salesforce, nvidia)
    wd          datacenter instance (e.g. wd1, wd5, wd12, wd3)
    site        career site name (e.g. external_experienced, External, Careers)

  Validation Endpoint (CXS REST API):
    POST https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    Payload: {"limit": 20, "offset": 0, "searchText": "", "appliedFacets": {}}
    200 OK -> Valid active board + returns total open job count!
    400 / 404 / 422 -> Inactive or invalid board.

State lives in SQLite (workday_master.db), so runs are resumable and re-runnable.
Outputs: workday_master.csv, workday_master.yaml, workday_master.json
"""
import argparse, csv, json, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None

DB = "data/workday_master.db" if Path("data").is_dir() else "workday_master.db"
API_TEMPLATE = "https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
BOARD_URL_TEMPLATE = "https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

RESERVED_SITES = {"wday", "job", "login", "apply", "en-us", "assets", "static", "favicon.ico"}
SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
WD_URL_REGEX = re.compile(
    r"https?://([a-zA-Z0-9_\-]+)\.((?:wd\d+|[a-zA-Z0-9_\-]+)\.)?myworkdayjobs\.com(?:/[a-z]{2}(?:[-_][a-zA-Z]{2,4})?)?/([^/?#\s\"\)\'>]+)",
    re.I
)

COMMON_WD_INSTANCES = ["wd5", "wd1", "wd12", "wd3", "wd2", "wd102"]
COMMON_SITE_NAMES = ["Careers", "External", "external_careers", "careers"]


# ----------------------------------------------------------------- storage
def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS boards(
        key TEXT PRIMARY KEY,
        tenant TEXT NOT NULL,
        wd TEXT NOT NULL,
        site TEXT NOT NULL,
        name TEXT,
        board_url TEXT NOT NULL,
        source TEXT,
        status TEXT DEFAULT 'pending',
        job_count INTEGER,
        checked_at REAL
    )""")
    return con


def add_board(con, tenant, wd, site, name, source):
    tenant = tenant.strip().lower()
    wd = wd.strip().lower() if wd else "wd1"
    site = site.strip()
    if not tenant or not site or site.lower() in RESERVED_SITES:
        return 0
    if not SLUG_OK.match(tenant):
        return 0

    key = f"{tenant}:{wd}:{site}"
    board_url = BOARD_URL_TEMPLATE.format(tenant=tenant, wd=wd, site=site)
    clean_name = name.strip() if name else tenant.replace("-", " ").replace("_", " ").title()

    cur = con.execute(
        "INSERT OR IGNORE INTO boards(key, tenant, wd, site, name, board_url, source) VALUES(?,?,?,?,?,?,?)",
        (key, tenant, wd, site, clean_name, board_url, source)
    )
    if cur.rowcount == 0 and name:
        con.execute(
            "UPDATE boards SET name=? WHERE key=? AND (name IS NULL OR name=tenant)",
            (clean_name, key)
        )
    con.commit()
    return cur.rowcount


# --------------------------------------------------------------- discovery
def extract_boards_from_text(text, source_name="text"):
    found = []
    lines = text.splitlines()
    for line in lines:
        for m in WD_URL_REGEX.finditer(line):
            tenant = m.group(1).lower()
            wd = m.group(2).rstrip(".").lower() if m.group(2) else "wd1"
            site = m.group(3)
            if site.lower() in RESERVED_SITES:
                continue

            comp_name = None
            m_comp = re.search(r"\|\s*\*\*\[([^\]]+)\]", line)
            if not m_comp:
                m_comp = re.search(r"\|\s*\[([^\]]+)\]", line)
            if not m_comp:
                m_comp = re.search(r"\|\s*\*\*([^\*\|]+)\*\*", line)
            if m_comp:
                comp_name = m_comp.group(1).strip()

            found.append((tenant, wd, site, comp_name))
    return found


def from_seed(path):
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Seed file not found: {path}", file=sys.stderr)
        return []
    raw = p.read_text(encoding="utf-8", errors="ignore")
    boards = []

    # YAML seed
    if path.endswith((".yaml", ".yml")) and yaml:
        data = yaml.safe_load(raw) or {}
        for c in data.get("companies", []):
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            if c.get("tenant") and c.get("site"):
                tenant = c["tenant"]
                wd = c.get("wd", "wd1")
                site = c["site"]
                boards.append((tenant, wd, site, name))
            elif c.get("url"):
                m = WD_URL_REGEX.search(c["url"])
                if m:
                    tenant = m.group(1).lower()
                    wd = m.group(2).rstrip(".").lower() if m.group(2) else "wd1"
                    site = m.group(3)
                    boards.append((tenant, wd, site, name))
        return boards

    # JSON directory or list
    if path.endswith(".json"):
        try:
            data = json.loads(raw)
            items = data.get("boards", []) if isinstance(data, dict) else data
            for b in items:
                if isinstance(b, dict) and b.get("tenant") and b.get("site"):
                    boards.append((b["tenant"], b.get("wd", "wd1"), b["site"], b.get("name")))
                elif isinstance(b, dict) and b.get("board_url"):
                    m = WD_URL_REGEX.search(b["board_url"])
                    if m:
                        tenant = m.group(1).lower()
                        wd = m.group(2).rstrip(".").lower() if m.group(2) else "wd1"
                        site = m.group(3)
                        boards.append((tenant, wd, site, b.get("name")))
            return boards
        except json.JSONDecodeError:
            pass

    # TXT / URL list fallback
    return extract_boards_from_text(raw)


def from_github(url):
    text = requests.get(url, headers=UA, timeout=30).text
    return extract_boards_from_text(text)


def from_names(path):
    p = Path(path)
    if not p.is_file() and (Path("seeds") / path).is_file():
        p = Path("seeds") / path
    if not p.is_file():
        print(f"Warning: Names file not found: {path}", file=sys.stderr)
        return []

    candidates = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        name = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        if not name:
            continue
        words = name.split()
        slugs = {"".join(words), "-".join(words), words[0]}
        for s in slugs:
            if not SLUG_OK.match(s):
                continue
            for wd in ("wd5", "wd1", "wd12"):
                for site in ("Careers", "External", s):
                    candidates.append((s, wd, site, line.strip()))
    return candidates


def from_common_crawl(con, max_pages):
    try:
        cols = requests.get("https://index.commoncrawl.org/collinfo.json", headers=UA, timeout=30).json()
    except requests.RequestException as e:
        print(f"Failed to fetch Common Crawl indexes: {e}", file=sys.stderr)
        return 0

    total = 0
    for col in cols[:2]:
        api = col["cdx-api"]
        for pattern in ("*.wd1.myworkdayjobs.com/*", "*.wd5.myworkdayjobs.com/*"):
            try:
                r = requests.get(api, params={"url": pattern, "output": "json", "showNumPages": "true"},
                                 headers=UA, timeout=20)
                pages = r.json().get("pages", 0)
            except (requests.RequestException, ValueError):
                continue

            for p in range(min(pages, max_pages)):
                try:
                    resp = requests.get(api, params={"url": pattern, "output": "json", "fl": "url",
                                                     "page": p, "collapse": "urlkey"},
                                        headers=UA, timeout=30)
                    if resp.status_code != 200:
                        continue
                    found = extract_boards_from_text(resp.text)
                    for tenant, wd, site, name in found:
                        total += add_board(con, tenant, wd, site, name, "commoncrawl")
                    print(f"  [cc] {col['id']} {pattern} page {p+1}/{pages} new total={total}", flush=True)
                except requests.RequestException:
                    pass
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


def check(key, tenant, wd, site, name, limiter, with_jobs):
    limiter.wait()
    url = API_TEMPLATE.format(tenant=tenant, wd=wd, site=site)
    payload = {"limit": 20, "offset": 0, "searchText": "", "appliedFacets": {}}

    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, headers=UA, timeout=12)
            if r.status_code == 200:
                data = r.json()
                jobs = data.get("total", len(data.get("jobPostings", []))) if with_jobs else None
                return key, "valid", name, jobs
            if r.status_code in (400, 403, 404, 422):
                return key, "invalid", None, None
            time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(2 ** attempt)

    return key, "error", None, None


def validate(con, workers, rate, with_jobs, recheck_days):
    cutoff = time.time() - recheck_days * 86400
    todo = con.execute(
        "SELECT key, tenant, wd, site, name FROM boards WHERE status IN ('pending','error') "
        "OR (status='valid' AND (checked_at IS NULL OR checked_at < ?))", (cutoff,)
    ).fetchall()

    print(f"Validating {len(todo)} Workday boards ({workers} workers, {rate}/s)...")
    limiter, done, ok = RateLimiter(rate), 0, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(check, k, t, w, s, name, limiter, with_jobs) for k, t, w, s, name in todo]
        for f in as_completed(futs):
            key, status, name, jobs = f.result()
            con.execute(
                "UPDATE boards SET status=?, job_count=?, checked_at=? WHERE key=?",
                (status, jobs, time.time(), key)
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
        "SELECT name, tenant, wd, site, job_count, board_url FROM boards WHERE status='valid' "
        "ORDER BY lower(coalesce(name, tenant))"
    ).fetchall()

    out_dir = Path("data") if Path("data").is_dir() else Path(".")

    if "yaml" in formats:
        lines = ["companies:"] + [
            f"  - {{ name: {json.dumps(n or t)}, ats: workday, tenant: {t}, wd: {w}, site: {s}, url: {u} }}"
            for n, t, w, s, _, u in rows
        ]
        (out_dir / "workday_master.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if "csv" in formats:
        with open(out_dir / "workday_master.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "tenant", "wd_instance", "site", "open_jobs", "board_url"])
            for n, t, wd, s, j, u in rows:
                w.writerow([n or t, t, wd, s, j if j is not None else "", u])

    if "json" in formats:
        data = [
            {
                "name": n or t,
                "tenant": t,
                "wd_instance": wd,
                "site": s,
                "open_jobs": j,
                "board_url": u
            }
            for n, t, wd, s, j, u in rows
        ]
        (out_dir / "workday_master.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    stats = dict(con.execute("SELECT status, COUNT(*) FROM boards GROUP BY status").fetchall())
    print(f"Exported {len(rows)} valid Workday career boards to {out_dir}/. DB status counts: {stats}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--directory", nargs="?", const="workday_directory.json", default=None,
                    help="load curated Workday directory JSON (default: workday_directory.json)")
    ap.add_argument("--seed", nargs="*", default=[], help="YAML/JSON/TXT files of boards or URLs")
    ap.add_argument("--github", nargs="*", default=[], help="raw URLs to scan for Workday boards")
    ap.add_argument("--names", help="text file, one company name per line")
    ap.add_argument("--cc", action="store_true", help="discover via Common Crawl")
    ap.add_argument("--max-cc-pages", type=int, default=50, help="pages per pattern per crawl")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--jobs", action="store_true", help="fetch live open-job counts")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=6.0, help="max requests/sec")
    ap.add_argument("--recheck-days", type=int, default=30)
    ap.add_argument("--export", nargs="*", default=["yaml", "csv", "json"], choices=["yaml", "csv", "json"])
    a = ap.parse_args()

    con = db()

    # Directory
    if a.directory:
        boards = from_seed(a.directory)
        added = sum(add_board(con, t, w, s, n, "directory") for t, w, s, n in boards)
        print(f"directory {a.directory}: +{added}")

    # Seed files
    for p in a.seed:
        boards = from_seed(p)
        added = sum(add_board(con, t, w, s, n, "seed") for t, w, s, n in boards)
        print(f"seed {p}: +{added}")

    # GitHub URLs
    for u in a.github:
        try:
            boards = from_github(u)
            added = sum(add_board(con, t, w, s, n, "github") for t, w, s, n in boards)
            print(f"github {u}: +{added}")
        except requests.RequestException as e:
            print(f"github {u}: failed ({e})", file=sys.stderr)

    # Names heuristic
    if a.names:
        boards = from_names(a.names)
        added = sum(add_board(con, t, w, s, n, "names") for t, w, s, n in boards)
        print(f"names: +{added}")

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

