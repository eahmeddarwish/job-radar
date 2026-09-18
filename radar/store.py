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
    status       TEXT NOT NULL DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_jobs_reported ON jobs(reported_on);
CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
"""

VALID_STATUS = {"new", "shortlisted", "applied", "skipped"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
                                 posted_at, first_seen, score, track, reasons, rejected, reject_why)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["uid"], job["source"], job["title"], job["company"], job.get("location", ""),
                job["url"], job.get("description", "")[:20000], job.get("posted_at", ""), _now(),
                verdict.get("score", 0), verdict.get("track", ""),
                " · ".join(verdict.get("reasons", [])),
                1 if verdict.get("rejected") else 0, verdict.get("reject_why", ""),
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

    def counts(self) -> dict:
        rows = self.conn.execute("SELECT status, COUNT(*) c FROM jobs WHERE rejected = 0 GROUP BY status")
        out = {r["status"]: r["c"] for r in rows}
        out["rejected"] = self.conn.execute("SELECT COUNT(*) c FROM jobs WHERE rejected = 1").fetchone()["c"]
        return out

    def applied_log(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'applied' ORDER BY first_seen DESC"
        ).fetchall()
