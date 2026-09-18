"""Profile loading. Stdlib only, so this runs on any Python 3.9+ with nothing installed."""

import json
from pathlib import Path

DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / "config" / "profile.json"


class Profile:
    def __init__(self, data: dict):
        self.data = data
        self.candidate = data["candidate"]
        self.tracks = data["tracks"]
        self.knockouts = data["knockouts"]
        self.location_allow = [s.lower() for s in data["location_allow"]]
        self.sources = data["sources"]
        self.min_score = int(data.get("min_score", 30))
        self.max_report_items = int(data.get("max_report_items", 25))

    def track(self, track_id: str) -> dict | None:
        return next((t for t in self.tracks if t["id"] == track_id), None)


def load_profile(path: str | Path | None = None) -> Profile:
    p = Path(path) if path else DEFAULT_PROFILE
    with open(p, encoding="utf-8") as fh:
        return Profile(json.load(fh))
