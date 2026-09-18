"""Command line. `scan` is the daily job; `applied` / `skip` keep the log honest."""

import argparse
from datetime import date
from pathlib import Path

from radar import report as report_mod
from radar.config import load_profile
from radar.knockouts import check
from radar.score import evaluate
from radar.sources import scan_all
from radar.store import Store

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def cmd_scan(args) -> int:
    profile = load_profile(args.profile)
    jobs, log = scan_all(profile)

    added = 0
    with Store() as store:
        for job in jobs:
            if store.known(job["uid"]):
                continue
            rejected, why = check(job, profile)
            verdict = {"rejected": rejected, "reject_why": why} if rejected else evaluate(job, profile)
            verdict.setdefault("rejected", False)
            if store.add(job, verdict):
                added += 1

        matches = store.unreported_matches(profile.min_score, profile.max_report_items)
        rejections = store.unreported_rejections()

        html_doc = report_mod.build_html(matches, rejections, log, profile, len(jobs))
        md_doc = report_mod.build_markdown(matches, rejections, log, profile, len(jobs))

        REPORTS.mkdir(exist_ok=True)
        today = date.today().isoformat()
        (REPORTS / f"{today}.html").write_text(html_doc, encoding="utf-8")
        (REPORTS / f"{today}.md").write_text(md_doc, encoding="utf-8")
        (REPORTS / "latest.html").write_text(html_doc, encoding="utf-8")
        (REPORTS / "latest.md").write_text(md_doc, encoding="utf-8")

        if not args.dry_run:
            store.mark_reported([r["uid"] for r in matches] + [r["uid"] for r in rejections])

        print(f"scanned {len(jobs)} · new {added} · reported {len(matches)} · filtered {len(rejections)}")
        for line in log:
            print("  " + line)
        print(f"report: {REPORTS / f'{today}.html'}")
    return 0


def cmd_applied(args) -> int:
    with Store() as store:
        store.set_status(args.uid, "applied")
        print(f"marked applied: {args.uid}")
    return 0


def cmd_skip(args) -> int:
    with Store() as store:
        store.set_status(args.uid, "skipped")
        print(f"marked skipped: {args.uid}")
    return 0


def cmd_stats(args) -> int:
    with Store() as store:
        for k, v in sorted(store.counts().items()):
            print(f"{k:12} {v}")
        applied = store.applied_log()
        if applied:
            print("\napplied:")
            for r in applied:
                print(f"  {r['first_seen'][:10]}  {r['title']} — {r['company']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Find and rank jobs. Never applies for you.")
    p.add_argument("--profile", help="path to profile.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="run every source and write today's report")
    s.add_argument("--dry-run", action="store_true", help="build the report without marking anything reported")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("applied", help="record that you sent an application")
    a.add_argument("uid")
    a.set_defaults(func=cmd_applied)

    k = sub.add_parser("skip", help="record that you passed on one")
    k.add_argument("uid")
    k.set_defaults(func=cmd_skip)

    sub.add_parser("stats", help="pipeline counts and the applied log").set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    return args.func(args)
