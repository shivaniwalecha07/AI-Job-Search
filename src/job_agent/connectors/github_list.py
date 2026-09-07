"""GitHub job-list connector (Phase 1 primary source).

Targets the public README-based trackers. These come in TWO layouts, both handled here:
  * HTML <table> (e.g. SimplifyJobs/Summer2027-Internships) with an "Age" column ("0d")
  * Markdown pipe-table (e.g. vanshb03/Summer2027-Internships) with a "Date Posted"
    column ("Aug 21")
Columns in both:  Company | Role | Location | Application | Age/Date
Rows whose company cell is the continuation arrow "↳" inherit the previous company.
Closed roles carry a 🔒 marker.

Parsing is stdlib only (re + html). Cells may contain HTML anchors and/or markdown links;
company cells may be plain text, **bold**, an HTML <a>, or a markdown [link](url).
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import httpx

from job_agent.connectors.base import BaseConnector, register
from job_agent.observability import get_logger
from job_agent.schemas.core import RawJobRecord, SourceHealth

log = get_logger(__name__)

RAW_URL = "https://raw.githubusercontent.com/{repo}/{branch}/README.md"

_TR = re.compile(r"<tr>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
_A_HREF = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)")
_TAGS = re.compile(r"<[^>]+>")
_AGE = re.compile(r"^\s*(\d+)\s*d\s*$", re.IGNORECASE)
_SEP_CELL = re.compile(r"^:?-{2,}:?$")
_CONTINUATION = {"↳", "&#8627;", "&darr;", "⤷", "↳"}
_MARKERS = ("🔥", "🎓", "🔒", "🛂", "🇺🇸", "⭐", "✨", "🌍", "🔐")

_ATS_HOSTS = {
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
    "workable.com": "workable",
    "icims.com": "icims",
    "eightfold.ai": "eightfold",
    "oraclecloud.com": "oracle",
    "smartrecruiters.com": "smartrecruiters",
    "myworkdayjobs.com": "workday",
    "successfactors": "successfactors",
    "taleo.net": "taleo",
    "jobvite.com": "jobvite",
}
_ID_PATTERNS = [
    re.compile(r"/jobs?/(\d{4,})"),
    re.compile(r"[?&]gh_jid=(\d+)"),
    re.compile(r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
    re.compile(r"/(\d{6,})"),
]
_MONTH_FMTS = ("%b %d", "%B %d", "%b %d, %Y", "%B %d, %Y")


def _strip_tags(fragment: str) -> str:
    return html.unescape(_TAGS.sub("", fragment)).strip()


def _clean_text(fragment: str) -> str:
    text = _strip_tags(fragment)
    for marker in _MARKERS:
        text = text.replace(marker, "")
    return re.sub(r"\s+", " ", text).strip()


def _all_hrefs(cell: str) -> list[str]:
    """Every link in a cell, from HTML anchors and markdown links, in order."""
    hrefs = [html.unescape(h) for h, _ in _A_HREF.findall(cell)]
    hrefs += [m.group(2) for m in _MD_LINK.finditer(cell)]
    return hrefs


def _first_apply_url(cell: str) -> str | None:
    for href in _all_hrefs(cell):
        if "simplify.jobs" not in href and not href.endswith((".png", ".jpg", ".svg")):
            return href
    return None


def _detect_ats(url: str | None) -> str | None:
    if not url:
        return None
    for host, name in _ATS_HOSTS.items():
        if host in url:
            return name
    return None


def _extract_job_id(url: str | None) -> str | None:
    if not url:
        return None
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def _parse_date_cell(text: str) -> datetime | None:
    """Handle both '0d'/'12d' age strings and 'Aug 21'/'August 21' date strings."""
    t = _clean_text(text)
    if not t:
        return None
    now = datetime.now(timezone.utc)
    m = _AGE.match(t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    for fmt in _MONTH_FMTS:
        try:
            d = datetime.strptime(t, fmt)
        except ValueError:
            continue
        if d.year == 1900:
            d = d.replace(year=now.year)
        d = d.replace(tzinfo=timezone.utc)
        if d > now:  # e.g. "Dec 20" seen in January -> last year
            d = d.replace(year=d.year - 1)
        return d
    return None


def _company_from_cell(cell: str) -> tuple[str | None, str | None]:
    """Return (company_name, company_url) or (None, None) for a continuation row."""
    plain = _clean_text(cell)
    if not plain or plain in _CONTINUATION:
        return None, None
    m = _A_HREF.search(cell)
    if m:
        return (_clean_text(m.group(2)) or None), html.unescape(m.group(1))
    md = _MD_LINK.search(cell)
    if md:
        return (_clean_text(md.group(1)) or None), md.group(2)
    name = plain.strip("*").strip()
    return (name or None), None


def _split_locations(cell: str) -> list[str]:
    parts = re.split(r"<br\s*/?>", cell, flags=re.IGNORECASE)
    return [loc for loc in (_clean_text(p) for p in parts) if loc]


def _extract_html_rows(markdown: str) -> list[list[str]]:
    rows = []
    for tr in _TR.findall(markdown):
        cells = _TD.findall(tr)
        if len(cells) >= 5:
            rows.append(cells[:5])
    return rows


def _extract_markdown_rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if all(_SEP_CELL.match(c or "") for c in cells):  # |---|---| separator
            continue
        if cells[0].lower() == "company" and cells[1].lower() == "role":  # header
            continue
        rows.append(cells[:5])
    return rows


def _rows_to_records(
    rows: list[list[str]], source_id: str, raw_url: str
) -> list[RawJobRecord]:
    records: list[RawJobRecord] = []
    last_company: str | None = None
    last_company_url: str | None = None

    for company_cell, role_cell, loc_cell, app_cell, date_cell in rows:
        company, company_url = _company_from_cell(company_cell)
        if company is None:
            company, company_url = last_company, last_company_url
        else:
            last_company, last_company_url = company, company_url
        if not company:
            continue

        role = _clean_text(role_cell)
        if not role:
            continue

        is_closed = "🔒" in role_cell or "🔒" in app_cell
        locations = _split_locations(loc_cell)
        location = " | ".join(locations) if locations else None
        apply_url = _first_apply_url(app_cell)
        posting_date = _parse_date_cell(date_cell)

        records.append(
            RawJobRecord(
                source_id=source_id,
                source_type="github_list",
                raw_url=raw_url,
                payload={
                    "company": company,
                    "company_url": company_url,
                    "role": role,
                    "location": location,
                    "locations": locations,
                    "apply_url": apply_url,
                    "ats": _detect_ats(apply_url),
                    "ats_job_id": _extract_job_id(apply_url),
                    "date_text": _clean_text(date_cell),
                    "posting_date": posting_date.isoformat() if posting_date else None,
                    "is_closed": is_closed,
                },
            )
        )
    return records


def parse_readme(markdown: str, source_id: str, raw_url: str) -> list[RawJobRecord]:
    """Parse either an HTML table or a markdown pipe-table into RawJobRecords."""
    html_rows = _extract_html_rows(markdown)
    md_rows = _extract_markdown_rows(markdown)
    records = _rows_to_records(html_rows, source_id, raw_url)
    records += _rows_to_records(md_rows, source_id, raw_url)
    return records


@register("github_list")
class GitHubListConnector(BaseConnector):
    requires_supervision = False

    def _raw_url(self) -> str:
        repo = self.params["repo"]
        branch = self.params.get("readme_branch", "main")
        return RAW_URL.format(repo=repo, branch=branch)

    def fetch(self, since: datetime | None = None) -> list[RawJobRecord]:
        url = self._raw_url()
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        records = parse_readme(resp.text, self.source_id, url)
        records = [r for r in records if not r.payload.get("is_closed")]
        log.info("github_list_fetched", source_id=self.source_id, n=len(records))
        return records

    def health(self) -> SourceHealth:
        try:
            resp = httpx.head(self._raw_url(), timeout=15, follow_redirects=True)
            ok = resp.status_code == 200
            return SourceHealth(source_id=self.source_id, ok=ok, detail=f"HTTP {resp.status_code}")
        except Exception as exc:  # pragma: no cover
            return SourceHealth(source_id=self.source_id, ok=False, detail=str(exc))
