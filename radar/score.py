"""Score a job against each CV track and pick the track that fits best.

The output is not just a number — it carries the reasons, because a shortlist you
cannot interrogate is a shortlist you stop trusting after a week.
"""

import re

TITLE_POINTS = 25
STRONG_POINTS = 6
WEAK_POINTS = 2
MAX_SCORE = 100

# A generic title with almost no skill overlap is a posting that happens to share a
# word with his CV, not a job that wants him. The first live run surfaced "Software
# Engineer GO" on the strength of the word "api" alone; this is the rule that stops it.
MIN_STRONG_FOR_MATCH = 2
THIN_MATCH_PENALTY = 0.4


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _contains(haystack: str, needle: str) -> bool:
    # Word-boundary match so "ai" does not fire inside "maintenance".
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def score_track(job: dict, track: dict) -> tuple[int, list[str]]:
    title = _norm(job.get("title", ""))
    blob = _norm(f"{job.get('title','')} {job.get('description','')}")

    # Anti-patterns disqualify the track outright: "AI Trainer Image QA Evaluator"
    # is a labelling gig, not technical training, however well the keywords line up.
    hit_anti = [a for a in track.get("anti", []) if a in title]
    if hit_anti:
        return 0, [f"not this track: title says {hit_anti[0]!r}"]

    points = 0
    reasons: list[str] = []

    matched_titles = [t for t in track["title_hits"] if t in title]
    if matched_titles:
        points += TITLE_POINTS
        reasons.append(f"title matches {matched_titles[0]!r}")

    strong = [k for k in track["strong"] if _contains(blob, k)]
    if strong:
        points += min(len(strong), 6) * STRONG_POINTS
        reasons.append("core skills: " + ", ".join(strong[:6]))

    weak = [k for k in track["weak"] if _contains(blob, k)]
    if weak:
        points += min(len(weak), 4) * WEAK_POINTS
        reasons.append("also mentions: " + ", ".join(weak[:4]))

    if matched_titles and len(strong) < MIN_STRONG_FOR_MATCH:
        points = int(points * THIN_MATCH_PENALTY)
        reasons.append("thin overlap — generic title, little else")

    return min(points, MAX_SCORE), reasons


def evaluate(job: dict, profile) -> dict:
    """Score against every track; the best one decides which CV to send."""
    best_id, best_score, best_reasons = "", 0, []
    for track in profile.tracks:
        s, reasons = score_track(job, track)
        if s > best_score:
            best_id, best_score, best_reasons = track["id"], s, reasons
    return {"score": best_score, "track": best_id, "reasons": best_reasons}
