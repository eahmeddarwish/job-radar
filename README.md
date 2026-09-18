# Job Radar

A daily scan that reads the job boards so Ahmed doesn't have to, ranks what it finds
against four CV tracks, and says which CV to send to which job.

```
scan sources ─► hard knockouts ─► score per CV track ─► dedup ─► daily report
```

**It does not apply for you.** That is a design decision, not a missing feature —
see below.

No dependencies. Stdlib Python 3.10+, nothing to `pip install`, nothing to break.

---

## Why it stops at the shortlist

Auto-apply tools exist and they are cheap. They are also the reason a single remote
posting now draws over a thousand applications, and the reason employers have started
putting knockout questions, work samples and "we will detect AI" warnings in front of
the résumé instead of behind it. A tool that fires 200 applications a month in your
name walks into every one of those filters without you watching.

So this one automates the expensive part — finding, filtering and ranking — and hands
you a short list with the reasoning attached. You open the link and send it yourself.
Ten minutes a day, against roles that can actually hire you.

## The filters that matter most

Scoring is the obvious half. The half that saves real hours is `radar/knockouts.py`,
which throws a job out before it is ever scored when:

- it requires work authorisation he does not have (`"must be authorized to work in the US"`,
  `"we are unable to sponsor"`, security clearance)
- it requires relocation outside the Gulf
- it is an internship or graduate scheme
- its stated location is outside his working radius (remote-anywhere, MENA, GCC)

A job that will never hire him is worse than no job at all: it costs an hour and
returns a silence he cannot read.

## Run it

```bash
python run.py scan            # scan, write today's report
python run.py scan --dry-run  # build the report without consuming the queue
python run.py stats           # pipeline counts and what you've applied to
python run.py applied <uid>   # log that you sent one
python run.py skip <uid>      # log that you passed
python -m unittest discover -s tests
```

Reports land in `reports/` as both HTML (to read) and Markdown (to paste).
`reports/latest.html` is always the newest.

## Run it without your PC on

`.github/workflows/daily.yml` runs the scan on GitHub Actions every morning at
08:00 Kuwait time and opens the report as an issue — so it arrives in your email
whether or not your machine is awake. There is also a manual **Run workflow**
button for when you want it now.

The seen-jobs database is cached between runs, so a job is only ever reported once.

## Tuning it

Everything lives in `config/profile.json`.

**The four tracks.** Each has `title_hits` (a match here is worth 25 points),
`strong` skills (6 each) and `weak` ones (2 each), plus the CV file to send. Change
the keywords, change what surfaces.

**`min_score`** is the floor for the report — 30 by default. Too much noise, raise it;
too quiet, lower it.

**Watching specific companies** is the highest-value setting in the file. Add a
company to `greenhouse_boards` or `ashby_boards` and the radar reads its careers page
directly, before the role reaches the aggregators:

```json
"greenhouse_boards": ["stripe", "figma"],
"ashby_boards": ["The-Flex", "linear"]
```

The slug is the last part of the company's job-board URL.

## Sources

Public JSON endpoints only — no scraping, no logins, nothing that violates a site's
terms or risks an account: Remotive, RemoteOK, Arbeitnow, plus any Greenhouse or
Ashby board you name. A source that goes down is logged and skipped; the run
continues on the rest.

## Layout

```
config/profile.json   the four CV tracks, the knockouts, the sources
radar/sources.py      the scanners — one function per board
radar/knockouts.py    hard rejects, applied before scoring
radar/score.py        per-track scoring, with the reasons kept
radar/store.py        SQLite; its job is to never show you a job twice
radar/report.py       the daily report, HTML and Markdown
radar/cli.py          scan / applied / skip / stats
tests/                stdlib unittest, no pytest needed
```
