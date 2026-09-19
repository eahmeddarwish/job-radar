"""SQLite store. Its whole job is: never show Ahmed the same job twice."""

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "radar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid          TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    location     TEXT,
    url          TEXT NOT NULL,
    description  TEXT,
    posted_at    TEXT,
    first_seen   TEXT NOT NULL,
    score        INTEGER,
    track        TEXT,
    reasons      TEXT,
    rejected     INTEGER NOT NULL DEFAULT 0,
    reject_why   TEXT,
    reported_on  TEXT,
    status       TEXT NOT NULL DEFAULT 'new',
    employment_track TEXT,
    applied_at   TEXT,
    interview_at TEXT,
    outcome      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_reported ON jobs(reported_on);
CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);

CREATE TABLE IF NOT EXISTS source_health (
    source            TEXT PRIMARY KEY,
    last_run          TEXT,
    last_success      TEXT,
    last_count        INTEGER,
    previous_count    INTEGER,
    consecutive_fails INTEGER NOT NULL DEFAULT 0,
    note              TEXT,
    content_hash      TEXT
);
"""

# Columns added after v1 shipped. A database from the first week must keep working.
_MIGRATIONS = [
    ("jobs", "employment_track", "TEXT"),
    ("jobs", "applied_at", "TEXT"),
    ("jobs", "interview_at", "TEXT"),
    ("jobs", "outcome", "TEXT"),
    ("source_health", "content_hash", "TEXT"),
]

# Indexes over migrated columns, created only once those columns exist.
_POST_MIGRATION = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_track ON jobs(employment_track)",
]

VALID_STATUS = {"new", "shortlisted", "applied", "skipped"}
VALID_OUTCOME = {"interview", "offer", "rejected", "no_reply"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        for table, column, coltype in _MIGRATIONS:
            existing = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        for statement in _POST_MIGRATION:
            self.conn.execute(statement)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def known(self, uid: str) -> bool:
        return self.conn.execute("SELECT 1 FROM jobs WHERE uid = ?", (uid,)).fetchone() is not None

    def add(self, job: dict, verdict: dict) -> bool:
        """Insert one scanned job. Returns False if it was already known."""
        if self.known(job["uid"]):
            return False
        self.conn.execute(
            """INSERT INTO jobs (uid, source, title, company, location, url, description,
                                 posted_at, first_seen, score, track, reasons, rejected, reject_why,
                                 employment_track)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["uid"], job["source"], job["title"], job["company"], job.get("location", ""),
                job["url"], job.get("description", "")[:20000], job.get("posted_at", ""), _now(),
                verdict.get("score", 0), verdict.get("track", ""),
                " · ".join(verdict.get("reasons", [])),
                1 if verdict.get("rejected") else 0, verdict.get("reject_why", ""),
                job.get("employment_track", ""),
            ),
        )
        self.conn.commit()
        return True

    def unreported_matches(self, min_score: int, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT * FROM jobs
               WHERE rejected = 0 AND reported_on IS NULL AND score >= ?
               ORDER BY score DESC, first_seen DESC LIMIT ?""",
            (min_score, limit),
        ).fetchall()

    def all_matches(self, min_score: int, days: int = 30) -> list:
        """Everything still worth showing — the dashboard browses history, not just today."""
        return self.conn.execute(
            """SELECT * FROM jobs
               WHERE rejected = 0 AND score >= ?
                 AND first_seen >= date('now', ?)
               ORDER BY score DESC, first_seen DESC""",
            (min_score, f"-{int(days)} days"),
        ).fetchall()

    def unreported_rejections(self, limit: int = 40) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT * FROM jobs WHERE rejected = 1 AND reported_on IS NULL
               ORDER BY first_seen DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def mark_reported(self, uids: list[str], on: str | None = None) -> None:
        stamp = on or date.today().isoformat()
        self.conn.executemany(
            "UPDATE jobs SET reported_on = ?, status = CASE WHEN rejected = 0 THEN 'shortlisted' ELSE status END "
            "WHERE uid = ?",
            [(stamp, u) for u in uids],
        )
        self.conn.commit()

    def set_status(self, uid: str, status: str) -> None:
        if status not in VALID_STATUS:
            raise ValueError(f"unknown status {status!r}; expected one of {sorted(VALID_STATUS)}")
        self.conn.execute("UPDATE jobs SET status = ? WHERE uid = ?", (status, uid))
        self.conn.commit()

    def unreported_matches_by_track(self, min_score: int, limit_per_track: int) -> dict:
        """The report's spine: jobs grouped by route, ranked only within a route."""
        from radar.tracks import TRACK_ORDER
        out = {}
        for track in TRACK_ORDER:
            rows = self.conn.execute(
                """SELECT * FROM jobs
                   WHERE rejected = 0 AND reported_on IS NULL AND score >= ?
                     AND employment_track = ?
                   ORDER BY score DESC, first_seen DESC LIMIT ?""",
                (min_score, track, limit_per_track),
            ).fetchall()
            if rows:
                out[track] = rows
        return out

    # ---- interview yield -------------------------------------------------
    # The only number that says whether any of this is working.

    def mark_applied(self, uid: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET status = 'applied', applied_at = ? WHERE uid = ?", (_now(), uid))
        self.conn.commit()

    def mark_outcome(self, uid: str, outcome: str) -> None:
        if outcome not in VALID_OUTCOME:
            raise ValueError(f"unknown outcome {outcome!r}; expected one of {sorted(VALID_OUTCOME)}")
        interview_at = _now() if outcome in ("interview", "offer") else None
        self.conn.execute(
            "UPDATE jobs SET outcome = ?, interview_at = COALESCE(interview_at, ?) WHERE uid = ?",
            (outcome, interview_at, uid))
        self.conn.commit()

    def yield_by_source(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT source,
                      COUNT(*)                                             AS surfaced,
                      SUM(CASE WHEN applied_at IS NOT NULL THEN 1 ELSE 0 END)   AS applied,
                      SUM(CASE WHEN interview_at IS NOT NULL THEN 1 ELSE 0 END) AS interviews,
                      SUM(CASE WHEN outcome = 'offer' THEN 1 ELSE 0 END)        AS offers
               FROM jobs WHERE rejected = 0 GROUP BY source ORDER BY interviews DESC, applied DESC"""
        ).fetchall()
        out = []
        for r in rows:
            applied = r["applied"] or 0
            interviews = r["interviews"] or 0
            out.append({
                "source": r["source"], "surfaced": r["surfaced"], "applied": applied,
                "interviews": interviews, "offers": r["offers"] or 0,
                "rate": (interviews / applied) if applied else None,
            })
        return out

    # ---- source health ---------------------------------------------------
    # Zero jobs from a source must never quietly mean zero jobs exist.

    def record_source(self, source: str, count: int | None, note: str = "") -> None:
        row = self.conn.execute(
            "SELECT last_count, consecutive_fails FROM source_health WHERE source = ?", (source,)
        ).fetchone()
        previous = row["last_count"] if row else None
        failed = count is None
        fails = ((row["consecutive_fails"] if row else 0) + 1) if failed else 0
        self.conn.execute(
            """INSERT INTO source_health (source, last_run, last_success, last_count,
                                          previous_count, consecutive_fails, note)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(source) DO UPDATE SET
                 last_run = excluded.last_run,
                 last_success = COALESCE(excluded.last_success, source_health.last_success),
                 last_count = excluded.last_count,
                 previous_count = excluded.previous_count,
                 consecutive_fails = excluded.consecutive_fails,
                 note = excluded.note""",
            (source, _now(), None if failed else _now(), count, previous, fails, note),
        )
        self.conn.commit()

    def page_hash(self, source: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM source_health WHERE source = ?", (source,)).fetchone()
        return row["content_hash"] if row else None

    def set_page_hash(self, source: str, digest: str) -> None:
        self.conn.execute("UPDATE source_health SET content_hash = ? WHERE source = ?",
                          (digest, source))
        self.conn.commit()

    def source_health(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM source_health ORDER BY consecutive_fails DESC, source"
        ).fetchall()

    def counts(self) -> dict:
        rows = self.conn.execute("SELECT status, COUNT(*) c FROM jobs WHERE rejected = 0 GROUP BY status")
        out = {r["status"]: r["c"] for r in rows}
        out["rejected"] = self.conn.execute("SELECT COUNT(*) c FROM jobs WHERE rejected = 1").fetchone()["c"]
        return out

    def applied_log(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'applied' ORDER BY first_seen DESC"
        ).fetchall()
