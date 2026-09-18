# Job Radar

A daily scan that reads the job boards so Ahmed doesn't have to, ranks what it finds
against four CV tracks, and says which CV to send to which job.

```
scan sources ─► classify route ─► hard knockouts ─► score per CV track ─► dedup ─► daily report
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

## Three routes, not one list

A job is sorted into one of three routes **before** it is scored, and the report
follows that order:

1. **GCC employer — may sponsor residency.** The roles that fix the residency, not
   just the income.
2. **Universities, colleges and schools.** The academic and training route.
3. **Remote income — no residency.** Good money, foreign employer, solves half the
   problem.

This is a decision hierarchy, not a preference. A remote job scoring 95 never
appears above a sponsorship job scoring 85, because the two are not competing for
the same thing. Score ranks jobs *within* a route.

The distinction that took the most care: a Gulf city named in a posting is not the
same as a Gulf employer. A London company whose posting lists eighty permitted
countries, Kuwait among them, is remote income — `radar/tracks.py` treats a long
country list or an explicitly worldwide location as exactly that.

## Interview yield — the only number that matters

Not jobs scanned. Not jobs matched. What reached an interview.

```bash
python run.py applied <uid>              # you sent one
python run.py outcome <uid> interview    # ... and they replied
python run.py outcome <uid> rejected
python run.py yield                      # the funnel, per source
```

After a few weeks this answers the question no amount of scanning can: which
sources are worth the hours. Expand what produces interviews; drop what doesn't.

## Watching institutions

Universities, colleges and international schools rarely reach the aggregators.
`radar/institutions.py` watches ten Kuwaiti ones daily, in order of preference:

1. **schema.org JobPosting** embedded as JSON-LD — a real, structured vacancy.
2. **Content-hash change detection** — when there is no structured data, the page
   is hashed, and a changed hash emits one item saying "this page changed, go and
   look". Crude, but honest about what it knows, and it never invents a vacancy.

Add more in `config/profile.json` under `institutions`.

## Source health

A source returning nothing is recorded as *healthy and quiet* or as *failed* —
never silently as zero, because a dead parser and an empty week look identical
until you make them look different.

```bash
python run.py health
```

Failures appear in the daily report with the reason, so a broken URL is fixed in
days rather than discovered in a month.

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
python run.py yield           # the funnel per source
python run.py health          # which sources are alive
python run.py stats           # pipeline counts
python run.py applied <uid>   # log that you sent one
python run.py outcome <uid> interview|offer|rejected|no_reply
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
config/profile.json   the four CV tracks, the knockouts, the sources, the institutions
radar/tracks.py       the three routes — decided before scoring
radar/institutions.py university, college and school watchers
radar/sources.py      the scanners — one function per board
radar/knockouts.py    hard rejects, applied before scoring
radar/score.py        per-track scoring, with the reasons kept
radar/store.py        SQLite; its job is to never show you a job twice
radar/report.py       the daily report, HTML and Markdown
radar/cli.py          scan / applied / skip / stats
tests/                stdlib unittest, no pytest needed
```
