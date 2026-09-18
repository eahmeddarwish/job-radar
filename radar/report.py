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
@media(max-width:520px){body{padding:20px 16px}h1{font-size:22px}}
"""


def _track_label(profile, track_id):
    t = profile.track(track_id)
    return t["label"] if t else track_id


def _cv(profile, track_id):
    t = profile.track(track_id)
    return t["cv"] if t else "—"


def build_html(matches, rejections, log, profile, scanned: int) -> str:
    today = date.today().isoformat()
    e = html.escape

    cards = []
    for j in matches:
        cards.append(f"""<div class="job">
<h3><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></h3>
<div class="meta">{e(j['company'])} · {e(j['location'] or 'not stated')} · via {e(j['source'])}</div>
<div class="row"><span class="score">{j['score']}</span>
<span class="cv">send: {e(_cv(profile, j['track']))}</span>
<span class="why">{e(_track_label(profile, j['track']))}</span></div>
<div class="why">{e(j['reasons'] or '')}</div>
<a class="apply" href="{e(j['url'])}" target="_blank" rel="noopener">Open and apply &rarr;</a>
</div>""")
    if not cards:
        cards.append('<div class="empty">No new matches today. The scan ran — nothing cleared the bar.</div>')

    rej_rows = "".join(
        f'<div class="rej"><b>{e(r["title"])}</b> — {e(r["company"])} · {e(r["reject_why"])}</div>'
        for r in rejections
    ) or '<div class="empty">Nothing was filtered out.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Radar — {today}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Job Radar</h1>
<div class="sub">Daily scan for Ahmed Darwish &middot; {today}</div>
<div class="stats">
<div class="stat"><b>{scanned}</b><span>scanned</span></div>
<div class="stat"><b>{len(matches)}</b><span>new matches</span></div>
<div class="stat"><b>{len(rejections)}</b><span>filtered out</span></div>
<div class="stat"><b>{profile.min_score}</b><span>score floor</span></div>
</div>
<h2>Worth your time</h2>
{''.join(cards)}
<h2>Filtered out, and why</h2>
{rej_rows}
<footer>Sources: {e(' · '.join(log))}<br>
This tool finds and ranks. It never applies for you — you open the link and send it yourself.</footer>
</div></body></html>"""


def build_markdown(matches, rejections, log, profile, scanned: int) -> str:
    today = date.today().isoformat()
    out = [f"## Job Radar — {today}", "",
           f"**{scanned}** scanned · **{len(matches)}** new matches · **{len(rejections)}** filtered out", ""]

    if matches:
        out.append("### Worth your time\n")
        for j in matches:
            out.append(f"**[{j['title']}]({j['url']})** — {j['company']}")
            out.append(f"`{j['score']}` · {j['location'] or 'location not stated'} · via {j['source']}")
            out.append(f"Send: **{_cv(profile, j['track'])}** ({_track_label(profile, j['track'])})")
            if j["reasons"]:
                out.append(f"_{j['reasons']}_")
            out.append("")
    else:
        out.append("_No new matches today._\n")

    if rejections:
        out.append("<details><summary>Filtered out, and why</summary>\n")
        for r in rejections:
            out.append(f"- **{r['title']}** — {r['company']} · {r['reject_why']}")
        out.append("\n</details>")

    out += ["", "---", f"Sources: {' · '.join(log)}", "",
            "_Finds and ranks only. It never applies for you._"]
    return "\n".join(out)
