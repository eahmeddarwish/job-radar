#!/usr/bin/env python3
"""Push the latest scan into the Career Radar API.

Runs after every scan. The API keeps the person's decisions in a separate table,
so re-syncing the same job every hour never erases a delete or an application.

Needs two environment variables, both set as GitHub Actions secrets:
  CAREER_API_URL    e.g. https://career.engdarwish.com
  CAREER_SYNC_SECRET
Absent either, this exits quietly — the scan itself must never fail because the
dashboard is not wired up yet.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

FEED = Path(__file__).resolve().parent / "reports" / "latest.json"


def main() -> int:
    base = (os.environ.get("CAREER_API_URL") or "").rstrip("/")
    secret = os.environ.get("CAREER_SYNC_SECRET") or ""
    if not base or not secret:
        print("sync: CAREER_API_URL / CAREER_SYNC_SECRET not set — skipping")
        return 0
    if not FEED.exists():
        print("sync: no reports/latest.json — skipping")
        return 0

    feed = json.loads(FEED.read_text(encoding="utf-8"))
    jobs = [j for t in feed.get("tracks", []) for j in t.get("jobs", [])]
    if not jobs:
        print("sync: nothing to push")
        return 0

    payload = json.dumps({
        "jobs": jobs,
        "meta": {"date": feed.get("date"), "scanned": feed.get("scanned"),
                 "min_score": feed.get("min_score")},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/api/sync", data=payload, method="POST",
        headers={"content-type": "application/json", "x-sync-secret": secret,
                 "user-agent": "job-radar-sync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            print("sync:", resp.read().decode("utf-8", "replace")[:300])
    except urllib.error.HTTPError as exc:
        print(f"sync: HTTP {exc.code} — {exc.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        return 0        # a dashboard outage must not fail the scan
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"sync: unreachable — {exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
