"""Fetch full job-description text from ATS public APIs (see ARCHITECTURE.md 8).

The GitHub lists give us the direct apply URL but no description. These public JSON endpoints
(meant for consumption — no scraping, no auth bypass) return the JD text we need so the
sponsorship assessor and matcher have real signal instead of a bare title.

Supported: Greenhouse, Lever, Ashby. Others return None (skipped, not scraped).
"""
from __future__ import annotations

import html
import re

import httpx

from job_agent.observability import get_logger

log = get_logger(__name__)

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")
MAX_LEN = 12000  # keep stored descriptions reasonable


def html_to_text(fragment: str) -> str:
    text = html.unescape(fragment or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6])>", "\n", text)
    text = _TAGS.sub("", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()[:MAX_LEN]


def parse_greenhouse(url: str) -> tuple[str, str] | None:
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([^/?#]+)", url)
    board = m.group(1) if m else None
    jid = None
    mj = re.search(r"/jobs?/(\d+)", url) or re.search(r"[?&]gh_jid=(\d+)", url)
    if mj:
        jid = mj.group(1)
    if board and jid:
        return board, jid
    return None


def parse_lever(url: str) -> tuple[str, str] | None:
    m = re.search(r"lever\.co/([^/?#]+)/([0-9a-f-]{16,})", url)
    return (m.group(1), m.group(2)) if m else None


def parse_ashby(url: str) -> tuple[str, str] | None:
    m = re.search(r"ashbyhq\.com/([^/?#]+)/([0-9a-f-]{16,})", url)
    return (m.group(1), m.group(2)) if m else None


def _greenhouse(url: str, client: httpx.Client) -> str | None:
    parsed = parse_greenhouse(url)
    if not parsed:
        return None
    board, jid = parsed
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}")
    if r.status_code != 200:
        return None
    return html_to_text(r.json().get("content", ""))


def _lever(url: str, client: httpx.Client) -> str | None:
    parsed = parse_lever(url)
    if not parsed:
        return None
    company, jid = parsed
    r = client.get(f"https://api.lever.co/v0/postings/{company}/{jid}?mode=json")
    if r.status_code != 200:
        return None
    d = r.json()
    return html_to_text(d.get("descriptionPlain") or d.get("description") or d.get("text") or "")


def _ashby(url: str, client: httpx.Client) -> str | None:
    parsed = parse_ashby(url)
    if not parsed:
        return None
    org, jid = parsed
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=false")
    if r.status_code != 200:
        return None
    for job in r.json().get("jobs", []):
        if job.get("id") == jid:
            return html_to_text(job.get("descriptionPlain") or job.get("descriptionHtml") or "")
    return None


_FETCHERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}
SUPPORTED = set(_FETCHERS)


def fetch_description(apply_url: str, ats: str | None, client: httpx.Client | None = None) -> str | None:
    """Return JD plain text for a supported ATS, else None. Never raises."""
    if not apply_url or ats not in _FETCHERS:
        return None
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True,
                                    headers={"User-Agent": "job-agent/0.1 (personal job search)"})
    try:
        return _FETCHERS[ats](apply_url, client) or None
    except Exception as exc:  # network/JSON issues never abort the batch
        log.warning("ats_fetch_failed", ats=ats, url=apply_url[:80], error=str(exc))
        return None
    finally:
        if own:
            client.close()
