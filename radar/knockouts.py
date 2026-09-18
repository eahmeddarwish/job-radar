"""Hard filters — the part that matters most for someone applying from Kuwait.

A job that will never hire him is worse than no job at all: it costs an hour and
returns a silence he cannot read. These rules throw those out before scoring.
"""

import re


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def check(job: dict, profile) -> tuple[bool, str]:
    """Return (rejected, reason)."""
    blob = _norm(f"{job.get('title','')} {job.get('description','')}")
    loc = _norm(job.get("location", ""))

    for category, phrases in profile.knockouts.items():
        for phrase in phrases:
            if phrase.lower() in blob:
                return True, f"{category}: matched \"{phrase}\""

    # Location gate: accept only if the location names somewhere he can actually work
    # from. An empty location is allowed through — plenty of remote posts leave it
    # blank, and scoring will judge them on content instead.
    if loc and not any(allowed in loc for allowed in profile.location_allow):
        return True, f"location: \"{job.get('location')}\" is outside his work radius"

    return False, ""
