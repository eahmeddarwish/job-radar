"""Which of the three routes does this job belong to?

This is the decision that outranks scoring. A remote job scoring 95 must never
appear above a sponsorship job scoring 85, because the two are not competing for
the same thing: one pays, the other fixes the residency. Score ranks jobs WITHIN
a track; the track itself is chosen first and never traded away.
"""

import re

GCC_SPONSORED = "GCC_SPONSORED"
INSTITUTIONAL = "INSTITUTIONAL"
REMOTE_FOREIGN = "REMOTE_FOREIGN"

# Report order. This list is the hierarchy — not a preference, an ordering.
TRACK_ORDER = [GCC_SPONSORED, INSTITUTIONAL, REMOTE_FOREIGN]

TRACK_LABELS = {
    GCC_SPONSORED: "GCC employer — may sponsor residency",
    INSTITUTIONAL: "Universities, colleges and schools",
    REMOTE_FOREIGN: "Remote income — no residency",
}

TRACK_NOTE = {
    GCC_SPONSORED: "Highest priority: these are the roles that can fix the residency, not just the income.",
    INSTITUTIONAL: "Academic and training routes. Most are in the Gulf and sponsor; check each one.",
    REMOTE_FOREIGN: "Good money, foreign employer. Does not provide Kuwaiti residency on its own.",
}

_GCC = ("kuwait", "saudi", "riyadh", "jeddah", "dammam", "khobar", "uae",
        "dubai", "abu dhabi", "sharjah", "qatar", "doha", "bahrain", "manama",
        "oman", "muscat", "gcc", "gulf")

_INSTITUTION_WORDS = ("university", "universities", "college", "institute", "school",
                      "academy", "faculty", "polytechnic", "جامعة", "كلية", "معهد", "مدرسة")

_GLOBAL_REMOTE = ("worldwide", "anywhere", "global", "remote - emea", "work from anywhere")


def _is_really_in_the_gulf(location: str) -> bool:
    """A Gulf word in the location field is not the same as a Gulf employer.

    The Flex is the case that taught this: a London company whose Ashby posting
    lists eighty countries, Kuwait among them. That is a remote job Ahmed may
    take from Kuwait — it is not an employer who will sponsor him. A long list of
    places, or an explicitly worldwide one, means the company is naming where it
    will accept residents from, not where it is.
    """
    if any(g in location for g in _GLOBAL_REMOTE):
        return False
    # Four or more places listed is a permitted-countries list, not an address.
    if len(re.split(r"[;,/|]", location)) >= 4:
        return False
    return any(g in location for g in _GCC)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower())


def classify(job: dict) -> str:
    source = _norm(job.get("source", ""))
    company = _norm(job.get("company", ""))
    location = _norm(job.get("location", ""))
    title = _norm(job.get("title", ""))

    # Anything the institution watchers found is institutional by construction.
    if source.startswith("institution/"):
        return INSTITUTIONAL

    if any(w in company for w in _INSTITUTION_WORDS):
        return INSTITUTIONAL

    # An academic title plus a Gulf location is an institution under another name.
    if any(w in title for w in ("lecturer", "faculty", "professor", "instructor")) and \
       _is_really_in_the_gulf(location):
        return INSTITUTIONAL

    if _is_really_in_the_gulf(location):
        return GCC_SPONSORED

    return REMOTE_FOREIGN
