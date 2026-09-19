#!/usr/bin/env python3
"""Watch the mailbox for replies to applications.

Runs twice a day. Reads the list of roles already applied to from the API, then
looks through recent mail for anything that plausibly answers one of them, and
posts what it finds back.

It is deliberately read-only against the mailbox: it never marks mail as read,
never moves anything, never deletes and never replies. Gmail's own unread state
stays exactly as the person left it.

Environment (all GitHub Actions secrets):
  CAREER_API_URL       https://career.engdarwish.com
  CAREER_SYNC_SECRET   same shared secret as the scan
  MAIL_HOST            imap.gmail.com
  MAIL_USER            the mailbox address
  MAIL_PASSWORD        a Google App Password, never the account password
Absent any of them, it exits quietly.
"""

import email
import email.utils
import imaplib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header

LOOKBACK_DAYS = 21
MAX_MESSAGES = 300

# Phrases that place a reply on one side or the other. Deliberately conservative:
# anything unclear stays "unknown" rather than being guessed into a false verdict.
INTERVIEW = ("interview", "schedule a call", "book a time", "meet the team",
             "next steps", "assessment", "technical screen", "availability",
             "مقابلة", "موعد")
REJECTED = ("unfortunately", "not moving forward", "not proceeding", "other candidates",
            "regret to inform", "unsuccessful", "not selected", "نأسف", "نعتذر")

NOISE_SENDERS = ("noreply@linkedin", "jobs-noreply@linkedin", "no-reply@indeed",
                 "notifications@", "newsletter@", "digest@")


def http_json(url, secret, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={"content-type": "application/json", "x-sync-secret": secret,
                 "user-agent": "job-radar-mailwatch/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def decoded(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def body_text(msg) -> str:
    parts = []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "text/plain":
            try:
                parts.append(part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", "replace"))
            except Exception:
                continue
    text = " ".join(parts) or ""
    return re.sub(r"\s+", " ", text).strip()


def classify(subject: str, body: str) -> str:
    blob = f"{subject} {body}".lower()
    if any(p in blob for p in REJECTED):
        return "rejected"
    if any(p in blob for p in INTERVIEW):
        return "interview"
    return "unknown"


def company_tokens(name: str) -> list[str]:
    """Distinctive words in a company name, so 'Gulf University for Science and
    Technology' can match on 'gust'-like words rather than on 'for' or 'group'."""
    stop = {"the", "for", "and", "of", "group", "company", "co", "ltd", "llc",
            "inc", "university", "college", "school", "international", "technologies",
            "technology", "solutions", "services", "industries"}
    words = re.findall(r"[a-z]{3,}", (name or "").lower())
    return [w for w in words if w not in stop] or words


def main() -> int:
    base = (os.environ.get("CAREER_API_URL") or "").rstrip("/")
    secret = os.environ.get("CAREER_SYNC_SECRET") or ""
    host = os.environ.get("MAIL_HOST") or "imap.gmail.com"
    user = os.environ.get("MAIL_USER") or ""
    password = os.environ.get("MAIL_PASSWORD") or ""

    if not all([base, secret, user, password]):
        print("mailwatch: credentials not configured — skipping")
        return 0

    try:
        applied = http_json(f"{base}/api/applied", secret).get("applied", [])
    except Exception as exc:
        print(f"mailwatch: could not read applied list — {exc}", file=sys.stderr)
        return 0
    if not applied:
        print("mailwatch: nothing applied to yet — nothing to watch for")
        return 0

    index = [(a["uid"], a.get("company", ""), company_tokens(a.get("company", ""))) for a in applied]
    print(f"mailwatch: watching for replies from {len(index)} employer(s)")

    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    found = []
    try:
        box = imaplib.IMAP4_SSL(host)
        box.login(user, password)
        box.select("INBOX", readonly=True)          # readonly: never touches unread state
        typ, data = box.search(None, f'(SINCE {since})')
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-MAX_MESSAGES:]
        print(f"mailwatch: {len(ids)} message(s) since {since}")

        for mid in ids:
            typ, raw = box.fetch(mid, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            frm = decoded(msg.get("From", ""))
            addr = email.utils.parseaddr(frm)[1].lower()
            if any(n in addr for n in NOISE_SENDERS):
                continue
            subject = decoded(msg.get("Subject", ""))
            body = body_text(msg)[:4000]
            hay = f"{subject} {body} {addr}".lower()
            domain = addr.split("@")[-1] if "@" in addr else ""

            for uid, company, tokens in index:
                if not tokens:
                    continue
                if any(t in hay for t in tokens) or (domain and tokens[0] in domain):
                    found.append({
                        "uid": uid, "from_addr": addr, "from_domain": domain,
                        "subject": subject,
                        "received_at": (email.utils.parsedate_to_datetime(msg.get("Date"))
                                        .isoformat() if msg.get("Date") else ""),
                        "snippet": body[:400],
                        "kind": classify(subject, body),
                    })
                    break
        box.logout()
    except (imaplib.IMAP4.error, OSError) as exc:
        print(f"mailwatch: mailbox error — {exc}", file=sys.stderr)
        return 0

    if not found:
        print("mailwatch: no replies matched")
        # still record that the check happened, so the dashboard can say when
        try: http_json(f"{base}/api/replies", secret, {"replies": []})
        except Exception: pass
        return 0

    try:
        res = http_json(f"{base}/api/replies", secret, {"replies": found})
        print(f"mailwatch: posted {len(found)} reply candidate(s) — {res}")
    except Exception as exc:
        print(f"mailwatch: could not post — {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
