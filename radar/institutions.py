"""Watch university, college and school careers pages.

These are where the academic and training roles actually appear — they rarely
reach the aggregators. There is no API, so two techniques in order of preference:

1. schema.org JobPosting embedded as JSON-LD. Many career systems emit it for
   Google Jobs, and when present it gives a real, structured vacancy.
2. Content-hash change detection. When there is no structured data, the page is
   hashed; if today's hash differs from yesterday's, one item is emitted saying
   "this page changed, go and look". Crude, but it is honest about what it knows,
   and it never invents a job that isn't there.

The important discipline is that a source returning nothing is recorded as
either "healthy, nothing new" or "failed" — never silently as zero.
"""

import hashlib
import json
import re
import urllib.error
import urllib.request

UA = "job-radar/1.1 (personal job search; contact via github.com/eahmeddarwish)"
TIMEOUT = 30

_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_MARKUP = re.compile(r"<[^>]+>")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _walk(node):
    """JSON-LD nests: a graph, a list, a single object. Yield every dict."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _job_postings(html: str) -> list[dict]:
    out = []
    for block in _JSONLD.findall(html):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for node in _walk(data):
            types = node.get("@type")
            types = [types] if isinstance(types, str) else (types or [])
            if any(str(t).lower() == "jobposting" for t in types):
                out.append(node)
    return out


def _text_of(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for key in ("name", "title", "value", "description"):
            if key in node:
                return _text_of(node[key])
    if isinstance(node, list) and node:
        return _text_of(node[0])
    return ""


def _location_of(node) -> str:
    loc = node.get("jobLocation")
    parts = []
    for n in _walk(loc) if loc is not None else []:
        addr = n.get("address") if isinstance(n, dict) else None
        if isinstance(addr, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry"):
                v = _text_of(addr.get(key, ""))
                if v and v not in parts:
                    parts.append(v)
    if not parts and node.get("jobLocationType"):
        return "Remote"
    return ", ".join(parts)


def _readable(html: str) -> str:
    stripped = _MARKUP.sub(" ", _TAGS.sub(" ", html))
    return re.sub(r"\s+", " ", stripped).strip()


def scan_institution(inst: dict, store) -> tuple[list[dict], str]:
    """Returns (jobs, status_note). Never raises — one dead page is not an outage."""
    slug = inst["id"]
    source = f"institution/{slug}"
    url = inst["careers_url"]

    try:
        html = _fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        store.record_source(source, None, f"unreachable: {type(exc).__name__}: {exc}")
        return [], "failed"

    postings = _job_postings(html)
    if postings:
        jobs = []
        for node in postings:
            title = _text_of(node.get("title") or node.get("name"))
            if not title:
                continue
            apply_url = _text_of(node.get("url")) or url
            jobs.append({
                "uid": f"{source}:" + hashlib.sha1(
                    f"{slug}|{title}|{apply_url}".encode("utf-8")).hexdigest()[:16],
                "source": source,
                "title": title,
                "company": inst["name"],
                "location": _location_of(node) or inst.get("country", ""),
                "url": apply_url,
                "description": _readable(_text_of(node.get("description")))[:8000],
                "posted_at": _text_of(node.get("datePosted")),
            })
        store.record_source(source, len(jobs), "structured data (JSON-LD)")
        return jobs, "structured"

    # No structured data — fall back to noticing that the page changed at all.
    body = _readable(html)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    store.record_source(source, 0, "no JSON-LD; watching for page changes")
    previous = store.page_hash(source)
    store.set_page_hash(source, digest)

    if previous is None:
        return [], "baselined"
    if previous == digest:
        return [], "unchanged"

    return [{
        "uid": f"{source}:changed:{digest[:16]}",
        "source": source,
        "title": f"{inst['name']} — careers page changed, check it",
        "company": inst["name"],
        "location": inst.get("country", ""),
        "url": url,
        "description": ("The careers page for this institution changed since the last scan and it "
                        "publishes no structured job data, so the change could not be read "
                        "automatically. Open it and look. " + body[:1500]),
        "posted_at": "",
    }], "changed"


def scan_all(profile, store) -> tuple[list[dict], list[str]]:
    jobs, log = [], []
    for inst in profile.data.get("institutions", []):
        found, status = scan_institution(inst, store)
        jobs += found
        log.append(f"institution/{inst['id']}: {status}" +
                   (f" ({len(found)})" if found else ""))
    return jobs, log
