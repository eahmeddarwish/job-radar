"""Job scanners. Public JSON endpoints only — no scraping, no logins, no ToS trouble.

Every fetcher returns the same dict shape so the rest of the pipeline never has to
care where a job came from. Add a company to greenhouse_boards / ashby_boards in
profile.json to watch its careers page directly, which is where the good roles are
before they reach the aggregators.
"""

import hashlib
import json
import urllib.error
import urllib.request

UA = "job-radar/1.0 (personal job search tool)"
TIMEOUT = 30


def _uid(source: str, url: str) -> str:
    return f"{source}:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _safe(fetcher, label: str, log: list) -> list[dict]:
    """One dead endpoint must never take the whole daily run down with it."""
    try:
        jobs = fetcher()
        log.append(f"{label}: {len(jobs)} jobs")
        return jobs
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
        log.append(f"{label}: FAILED ({type(exc).__name__}: {exc})")
        return []


def remotive() -> list[dict]:
    data = _get_json("https://remotive.com/api/remote-jobs")
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "")
        out.append({
            "uid": _uid("remotive", url), "source": "remotive",
            "title": j.get("title", ""), "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location", ""), "url": url,
            "description": j.get("description", ""), "posted_at": j.get("publication_date", ""),
        })
    return out


def remoteok() -> list[dict]:
    data = _get_json("https://remoteok.com/api")
    out = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is a legal notice, not a job
        url = j.get("url", "")
        out.append({
            "uid": _uid("remoteok", url), "source": "remoteok",
            "title": j.get("position", ""), "company": j.get("company", ""),
            "location": j.get("location", "") or "Remote", "url": url,
            "description": j.get("description", ""), "posted_at": j.get("date", ""),
        })
    return out


def arbeitnow() -> list[dict]:
    data = _get_json("https://www.arbeitnow.com/api/job-board-api")
    out = []
    for j in data.get("data", []):
        url = j.get("url", "")
        loc = j.get("location", "")
        if j.get("remote"):
            loc = f"{loc} (remote)" if loc else "Remote"
        out.append({
            "uid": _uid("arbeitnow", url), "source": "arbeitnow",
            "title": j.get("title", ""), "company": j.get("company_name", ""),
            "location": loc, "url": url,
            "description": j.get("description", ""), "posted_at": str(j.get("created_at", "")),
        })
    return out


def greenhouse(board: str) -> list[dict]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        url = j.get("absolute_url", "")
        out.append({
            "uid": _uid("greenhouse", url), "source": f"greenhouse/{board}",
            "title": j.get("title", ""), "company": board,
            "location": (j.get("location") or {}).get("name", ""), "url": url,
            "description": j.get("content", ""), "posted_at": j.get("updated_at", ""),
        })
    return out


def ashby(board: str) -> list[dict]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    out = []
    for j in data.get("jobs", []):
        url = j.get("jobUrl", "")
        out.append({
            "uid": _uid("ashby", url), "source": f"ashby/{board}",
            "title": j.get("title", ""), "company": board.replace("-", " "),
            "location": j.get("location", ""), "url": url,
            "description": j.get("descriptionPlain", "") or j.get("descriptionHtml", ""),
            "posted_at": j.get("publishedAt", ""),
        })
    return out


def scan_all(profile) -> tuple[list[dict], list[str]]:
    """Run every enabled source. Returns (jobs, per-source log)."""
    cfg = profile.sources
    log: list[str] = []
    jobs: list[dict] = []

    if cfg.get("remotive"):
        jobs += _safe(remotive, "remotive", log)
    if cfg.get("remoteok"):
        jobs += _safe(remoteok, "remoteok", log)
    if cfg.get("arbeitnow"):
        jobs += _safe(arbeitnow, "arbeitnow", log)
    for board in cfg.get("greenhouse_boards", []):
        jobs += _safe(lambda b=board: greenhouse(b), f"greenhouse/{board}", log)
    for board in cfg.get("ashby_boards", []):
        jobs += _safe(lambda b=board: ashby(b), f"ashby/{board}", log)

    seen, deduped = set(), []
    for j in jobs:
        if j["uid"] not in seen and j.get("url"):
            seen.add(j["uid"])
            deduped.append(j)
    return deduped, log
