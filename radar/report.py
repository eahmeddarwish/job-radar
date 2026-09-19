"""The daily report: a ranked shortlist, the reasoning behind each rank, and what
was thrown out and why.

Two formats from the same data — HTML to read, Markdown to paste into a GitHub
issue so the report arrives by email without any mail server.
"""

import html
from datetime import date

CSS = """
:root{--bg:#ffffff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--navy:#12395E;
--copper:#A4531F;--chip:#f4f4f5;--good:#116b3a}
:root:not([data-theme="light"]){@media (prefers-color-scheme:dark){
:root{--bg:#141414;--fg:#ededed;--muted:#a1a1a1;--line:#2c2c2c;--navy:#7fb0e0;
--copper:#e08a4d;--chip:#242424;--good:#5fd18e}}}
:root[data-theme="dark"]{--bg:#141414;--fg:#ededed;--muted:#a1a1a1;--line:#2c2c2c;
--navy:#7fb0e0;--copper:#e08a4d;--chip:#242424;--good:#5fd18e}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;padding:32px 16px;
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px;color:var(--navy)}
.sub{color:var(--muted);font-size:14px;margin-bottom:28px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:28px}
.stat{background:var(--chip);border-radius:10px;padding:10px 14px;min-width:96px}
.stat b{display:block;font-size:20px;color:var(--navy)}
.stat span{font-size:12px;color:var(--muted)}
.job{border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.job h3{margin:0 0 2px;font-size:17px}
.job h3 a{color:var(--fg);text-decoration:none}
.job h3 a:hover{color:var(--navy);text-decoration:underline}
.meta{color:var(--muted);font-size:13px;margin-bottom:10px}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.score{background:var(--navy);color:#fff;border-radius:999px;padding:2px 11px;
font-size:13px;font-weight:600}
.cv{background:var(--chip);border-radius:999px;padding:2px 11px;font-size:12px;
color:var(--copper);font-weight:600}
.why{font-size:13px;color:var(--muted)}
.apply{display:inline-block;margin-top:8px;font-size:13px;font-weight:600;
color:var(--navy);text-decoration:none}
.apply:hover{text-decoration:underline}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
margin:34px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.rej{font-size:13px;color:var(--muted);padding:6px 0;border-bottom:1px solid var(--line)}
.rej b{color:var(--fg);font-weight:600}
.empty{color:var(--muted);font-style:italic;padding:20px 0}
footer{margin-top:36px;padding-top:14px;border-top:1px solid var(--line);
font-size:12px;color:var(--muted)}
.track{margin-top:30px}
.track h2{margin-bottom:2px;color:var(--navy);text-transform:none;font-size:17px;
letter-spacing:0;border:0;padding:0}
.track .note{font-size:13px;color:var(--muted);margin-bottom:12px}
.rank{display:inline-block;background:var(--copper);color:#fff;border-radius:6px;
padding:1px 8px;font-size:11px;font-weight:700;letter-spacing:.04em;margin-bottom:6px}
.health{font-size:13px;padding:5px 0;border-bottom:1px solid var(--line);
display:flex;gap:8px;align-items:baseline}
.health .s{flex:1}
.bad{color:var(--copper);font-weight:600}
table.yield{width:100%;border-collapse:collapse;font-size:13px}
table.yield th{text-align:left;color:var(--muted);font-weight:600;padding:5px 8px 5px 0;
border-bottom:1px solid var(--line)}
table.yield td{padding:5px 8px 5px 0;border-bottom:1px solid var(--line)}
@media(max-width:520px){body{padding:20px 16px}h1{font-size:22px}}
"""


def _track_label(profile, track_id):
    t = profile.track(track_id)
    return t["label"] if t else track_id


def _cv(profile, track_id):
    t = profile.track(track_id)
    return t["cv"] if t else "—"


def _card(j, profile) -> str:
    e = html.escape
    return f"""<div class="job">
<h3><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></h3>
<div class="meta">{e(j['company'])} · {e(j['location'] or 'not stated')} · via {e(j['source'])}</div>
<div class="row"><span class="score">{j['score']}</span>
<span class="cv">send: {e(_cv(profile, j['track']))}</span>
<span class="why">{e(_track_label(profile, j['track']))}</span></div>
<div class="why">{e(j['reasons'] or '')}</div>
<a class="apply" href="{e(j['url'])}" target="_blank" rel="noopener">Open and apply &rarr;</a>
</div>"""


def build_html(by_track, rejections, log, profile, scanned, health=(), yields=()) -> str:
    from radar.tracks import TRACK_ORDER, TRACK_LABELS, TRACK_NOTE
    today = date.today().isoformat()
    e = html.escape
    total = sum(len(v) for v in by_track.values())

    sections = []
    for rank, track in enumerate(TRACK_ORDER, start=1):
        rows = by_track.get(track) or []
        if not rows:
            continue
        cards = "".join(_card(j, profile) for j in rows)
        sections.append(f"""<div class="track">
<span class="rank">PRIORITY {rank}</span>
<h2>{e(TRACK_LABELS[track])}</h2>
<div class="note">{e(TRACK_NOTE[track])}</div>
{cards}</div>""")
    if not sections:
        sections.append('<div class="empty">No new matches today. The scan ran — nothing cleared the bar.</div>')

    rej_rows = "".join(
        f'<div class="rej"><b>{e(r["title"])}</b> — {e(r["company"])} · {e(r["reject_why"])}</div>'
        for r in rejections) or '<div class="empty">Nothing was filtered out.</div>'

    health_rows = ""
    for h in health:
        broke = (h["consecutive_fails"] or 0) > 0
        count = "failed" if h["last_count"] is None else f"{h['last_count']} jobs"
        cls = ' class="bad"' if broke else ""
        health_rows += (f'<div class="health"><span class="s">{e(h["source"])}</span>'
                        f'<span{cls}>{e(count)}</span>'
                        f'<span class="why">{e(h["note"] or "")}</span></div>')
    health_block = health_rows or '<div class="empty">No source history yet.</div>'

    yield_rows = "".join(
        f"<tr><td>{e(y['source'])}</td><td>{y['surfaced']}</td><td>{y['applied']}</td>"
        f"<td>{y['interviews']}</td><td>{y['offers']}</td>"
        f"<td>{'—' if y['rate'] is None else format(y['rate'], '.0%')}</td></tr>"
        for y in yields if y["applied"])
    yield_block = (f"""<table class="yield"><tr><th>source</th><th>surfaced</th><th>applied</th>
<th>interviews</th><th>offers</th><th>rate</th></tr>{yield_rows}</table>"""
        if yield_rows else
        '<div class="empty">Nothing applied to yet. Run <code>python run.py applied &lt;uid&gt;</code> when you send one.</div>')

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Radar — {today}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Job Radar</h1>
<div class="sub">Daily scan for Ahmed Darwish &middot; {today}</div>
<div class="stats">
<div class="stat"><b>{scanned}</b><span>scanned</span></div>
<div class="stat"><b>{total}</b><span>new matches</span></div>
<div class="stat"><b>{len(rejections)}</b><span>filtered out</span></div>
<div class="stat"><b>{profile.min_score}</b><span>score floor</span></div>
</div>
{''.join(sections)}
<h2>Interview yield</h2>
{yield_block}
<h2>Source health</h2>
{health_block}
<h2>Filtered out, and why</h2>
{rej_rows}
<footer>Sources: {e(' · '.join(log))}<br>
This tool finds and ranks. It never applies for you — you open the link and send it yourself.</footer>
</div></body></html>"""


def build_markdown(by_track, rejections, log, profile, scanned, health=(), yields=()) -> str:
    from radar.tracks import TRACK_ORDER, TRACK_LABELS, TRACK_NOTE
    today = date.today().isoformat()
    total = sum(len(v) for v in by_track.values())
    out = [f"## Job Radar — {today}", "",
           f"**{scanned}** scanned · **{total}** new matches · **{len(rejections)}** filtered out", ""]

    if total:
        for rank, track in enumerate(TRACK_ORDER, start=1):
            rows = by_track.get(track) or []
            if not rows:
                continue
            out.append(f"### {rank}. {TRACK_LABELS[track]}")
            out.append(f"_{TRACK_NOTE[track]}_\n")
            for j in rows:
                out.append(f"**[{j['title']}]({j['url']})** — {j['company']}")
                out.append(f"`{j['score']}` · {j['location'] or 'location not stated'} · via {j['source']}")
                out.append(f"Send: **{_cv(profile, j['track'])}** ({_track_label(profile, j['track'])})")
                if j["reasons"]:
                    out.append(f"_{j['reasons']}_")
                out.append("")
    else:
        out.append("_No new matches today._\n")

    applied_rows = [y for y in yields if y["applied"]]
    if applied_rows:
        out += ["### Interview yield", "",
                "| source | surfaced | applied | interviews | offers | rate |",
                "|---|---|---|---|---|---|"]
        for y in applied_rows:
            rate = "—" if y["rate"] is None else format(y["rate"], ".0%")
            out.append(f"| {y['source']} | {y['surfaced']} | {y['applied']} | "
                       f"{y['interviews']} | {y['offers']} | {rate} |")
        out.append("")

    broken = [h for h in health if (h["consecutive_fails"] or 0) > 0]
    if broken:
        out.append("### ⚠️ Sources needing attention\n")
        for h in broken:
            out.append(f"- **{h['source']}** — {h['note']} "
                       f"({h['consecutive_fails']} run(s) in a row)")
        out.append("")

    if rejections:
        out.append("<details><summary>Filtered out, and why</summary>\n")
        for r in rejections:
            out.append(f"- **{r['title']}** — {r['company']} · {r['reject_why']}")
        out.append("\n</details>")

    out += ["", "---", f"Sources: {' · '.join(log)}", "",
            "_Finds and ranks only. It never applies for you._"]
    return "\n".join(out)


def build_json(matches, rejections, log, profile, scanned, health=(), yields=()) -> str:
    """The dashboard's data feed.

    Written as a separate artefact rather than scraped back out of the HTML,
    because a report meant for a human and a feed meant for a program should not
    be the same document.
    """
    import json
    from datetime import datetime, timezone
    from radar.tracks import TRACK_ORDER, TRACK_LABELS, TRACK_NOTE

    def job_row(r):
        return {
            "uid": r["uid"],
            "title": r["title"],
            "company": r["company"],
            "location": r["location"] or "",
            "url": r["url"],
            "source": r["source"],
            "score": r["score"],
            "cv_track": r["track"] or "",
            "cv_file": _cv(profile, r["track"]),
            "cv_label": _track_label(profile, r["track"]),
            "reasons": r["reasons"] or "",
            "posted_at": r["posted_at"] or "",
            "first_seen": r["first_seen"],
            "status": r["status"],
            "employment_track": r["employment_track"] or "",
            "applied_at": r["applied_at"] or "",
            "outcome": r["outcome"] or "",
            "excerpt": (r["description"] or "")[:1200],
        }

    by_track = {}
    for r in matches:
        by_track.setdefault(r["employment_track"] or "REMOTE_FOREIGN", []).append(job_row(r))

    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": date.today().isoformat(),
        "scanned": scanned,
        "min_score": profile.min_score,
        "candidate": profile.candidate,
        "tracks": [
            {"id": t, "label": TRACK_LABELS[t], "note": TRACK_NOTE[t], "jobs": by_track.get(t, [])}
            for t in TRACK_ORDER
        ],
        "cv_tracks": [
            {"id": t["id"], "label": t["label"], "cv": t["cv"]} for t in profile.tracks
        ],
        "rejected": [
            {"title": r["title"], "company": r["company"], "why": r["reject_why"]}
            for r in rejections
        ],
        "sources": [
            {"source": h["source"], "last_count": h["last_count"], "note": h["note"] or "",
             "fails": h["consecutive_fails"] or 0, "last_success": h["last_success"] or ""}
            for h in health
        ],
        "yield": list(yields),
        "log": list(log),
    }, ensure_ascii=False, indent=2)
