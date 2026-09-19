"""Command line. `scan` is the daily job; the rest keep the yield log honest."""

import argparse
import os
from datetime import date
from pathlib import Path

from radar import institutions
from radar import report as report_mod
from radar import tracks
from radar.config import load_profile
from radar.knockouts import check
from radar.score import evaluate
from radar.sources import scan_all
from radar.store import Store

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def cmd_scan(args) -> int:
    profile = load_profile(args.profile)

    with Store() as store:
        jobs, log = scan_all(profile)
        for line in log:
            name, _, rest = line.partition(": ")
            store.record_source(name, None if "FAILED" in rest else _count(rest), rest)

        inst_jobs, inst_log = institutions.scan_all(profile, store)
        jobs += inst_jobs
        log += inst_log

        added = 0
        for job in jobs:
            if store.known(job["uid"]):
                continue
            job["employment_track"] = tracks.classify(job)
            rejected, why = check(job, profile)
            verdict = {"rejected": rejected, "reject_why": why} if rejected else evaluate(job, profile)
            verdict.setdefault("rejected", False)
            if store.add(job, verdict):
                added += 1

        by_track = store.unreported_matches_by_track(profile.min_score, profile.max_report_items)
        rejections = store.unreported_rejections()
        health = store.source_health()
        yields = store.yield_by_source()

        html_doc = report_mod.build_html(by_track, rejections, log, profile, len(jobs), health, yields)
        md_doc = report_mod.build_markdown(by_track, rejections, log, profile, len(jobs), health, yields)
        # The dashboard browses the last 30 days, not only what is new today.
        json_doc = report_mod.build_json(store.all_matches(profile.min_score, 30),
                                         rejections, log, profile, len(jobs), health, yields)

        REPORTS.mkdir(exist_ok=True)
        today = date.today().isoformat()
        for name, doc in ((f"{today}.html", html_doc), (f"{today}.md", md_doc),
                          ("latest.html", html_doc), ("latest.md", md_doc),
                          ("latest.json", json_doc)):
            (REPORTS / name).write_text(doc, encoding="utf-8")

        reported = [r["uid"] for rows in by_track.values() for r in rows]
        if not args.dry_run:
            store.mark_reported(reported + [r["uid"] for r in rejections])

        # The workflow runs hourly but should only raise an issue when something
        # new actually turned up — otherwise it is 24 notifications a day of nothing.
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as fh:
                fh.write(f"new_matches={len(reported)}\n")
                fh.write(f"scanned={len(jobs)}\n")

        print(f"scanned {len(jobs)} · new {added} · reported {len(reported)} · filtered {len(rejections)}")
        for track, rows in by_track.items():
            print(f"  {track:<15} {len(rows)}")
        for line in log:
            print("  " + line)
        broken = [h["source"] for h in health if (h["consecutive_fails"] or 0) > 0]
        if broken:
            print("  ⚠ sources failing: " + ", ".join(broken))
        print(f"report: {REPORTS / f'{today}.html'}")
    return 0


def _count(text: str):
    for token in text.split():
        if token.isdigit():
            return int(token)
    return 0


def cmd_applied(args) -> int:
    with Store() as store:
        store.mark_applied(args.uid)
        print(f"applied: {args.uid}")
    return 0


def cmd_outcome(args) -> int:
    with Store() as store:
        store.mark_outcome(args.uid, args.outcome)
        print(f"{args.uid} -> {args.outcome}")
    return 0


def cmd_skip(args) -> int:
    with Store() as store:
        store.set_status(args.uid, "skipped")
        print(f"skipped: {args.uid}")
    return 0


def cmd_yield(args) -> int:
    with Store() as store:
        rows = store.yield_by_source()
        print(f"{'source':<28}{'surfaced':>9}{'applied':>9}{'interviews':>12}{'offers':>8}{'rate':>8}")
        for y in rows:
            rate = "—" if y["rate"] is None else format(y["rate"], ".0%")
            print(f"{y['source']:<28}{y['surfaced']:>9}{y['applied']:>9}"
                  f"{y['interviews']:>12}{y['offers']:>8}{rate:>8}")
        if not any(y["applied"] for y in rows):
            print("\nNothing applied to yet — the only number that matters is still empty.")
    return 0


def cmd_health(args) -> int:
    with Store() as store:
        for h in store.source_health():
            flag = "FAIL" if (h["consecutive_fails"] or 0) else "ok"
            count = "—" if h["last_count"] is None else h["last_count"]
            print(f"{flag:<5} {h['source']:<34} {str(count):>5}  {h['note'] or ''}")
    return 0


def cmd_stats(args) -> int:
    with Store() as store:
        for k, v in sorted(store.counts().items()):
            print(f"{k:12} {v}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Find and rank jobs. Never applies for you.")
    p.add_argument("--profile", help="path to profile.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="run every source and write today's report")
    s.add_argument("--dry-run", action="store_true", help="build the report without consuming the queue")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("applied", help="record that you sent an application")
    a.add_argument("uid"); a.set_defaults(func=cmd_applied)

    o = sub.add_parser("outcome", help="record what came back")
    o.add_argument("uid"); o.add_argument("outcome", choices=["interview", "offer", "rejected", "no_reply"])
    o.set_defaults(func=cmd_outcome)

    k = sub.add_parser("skip", help="record that you passed on one")
    k.add_argument("uid"); k.set_defaults(func=cmd_skip)

    sub.add_parser("yield", help="the funnel per source — the only number that matters").set_defaults(func=cmd_yield)
    sub.add_parser("health", help="which sources are alive").set_defaults(func=cmd_health)
    sub.add_parser("stats", help="pipeline counts").set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    return args.func(args)
