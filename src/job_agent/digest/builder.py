"""Daily digest (see ARCHITECTURE.md 9). Top-K by final score, each with a why-line and
sponsorship shown as status + confidence + reason (never a bare claim). Ends with the
'not legal advice' note. Renders HTML; writes a file and optionally emails it.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from job_agent.db.base import get_session
from job_agent.db.models import Company, Job, JobMatch, SponsorshipAssessment
from job_agent.observability import get_logger
from job_agent.settings import get_settings

log = get_logger(__name__)

_SPONSOR_BADGE = {
    "YES": ("#1a7f37", "Likely / stated"),
    "NO": ("#b42318", "Not available"),
    "JOB_SPECIFIC": ("#b54708", "Role-specific — verify"),
    "COMPANY_SPECIFIC": ("#b54708", "Company-level only"),
    "UNCLEAR": ("#b54708", "Unclear — verify"),
    "UNKNOWN": ("#6c757d", "Unknown — verify"),
}


def collect_top(top_k: int = 15) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = (
            select(Job, Company, JobMatch, SponsorshipAssessment)
            .join(Company, Job.company_id == Company.id)
            .join(JobMatch, JobMatch.job_id == Job.id)
            .outerjoin(SponsorshipAssessment, SponsorshipAssessment.job_id == Job.id)
            .order_by(JobMatch.final_score.desc())
            .limit(top_k)
        )
        items = []
        for job, company, m, spon in session.execute(stmt).all():
            age = ""
            if job.posting_date:
                age = f"{(datetime.now(job.posting_date.tzinfo) - job.posting_date).days}d ago"
            import json
            components = json.loads(m.rank_components_json or "{}")
            top_drivers = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]
            items.append({
                "company": company.name, "title": job.title, "location": job.location or "",
                "apply_url": job.apply_url or job.source_url, "final_score": m.final_score or 0,
                "match_overall": m.overall, "freshness": job.freshness, "age": age,
                "sponsor_status": spon.status if spon else "UNKNOWN",
                "sponsor_conf": spon.confidence if spon else 0.0,
                "needs_verification": spon.needs_human_verification if spon else True,
                "why": ", ".join(f"{k} +{v:.0f}" for k, v in top_drivers if v > 0),
                "strengths": json.loads(m.strengths_json or "[]")[:3],
            })
        return items


def build_digest(items: list[dict[str, Any]]) -> tuple[str, str]:
    """Return (subject, html_body)."""
    date = datetime.now(timezone.utc).strftime("%b %d, %Y")
    subject = f"SWE Opportunities — {len(items)} top matches ({date})"
    cards = []
    for i, it in enumerate(items, 1):
        color, label = _SPONSOR_BADGE.get(it["sponsor_status"], _SPONSOR_BADGE["UNKNOWN"])
        verify = " ⚠️ human verification recommended" if it["needs_verification"] else ""
        strengths = "".join(f"<li>{_html.escape(s)}</li>" for s in it["strengths"])
        cards.append(f"""
<div style="border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:10px 0">
  <div style="display:flex;justify-content:space-between">
    <strong style="font-size:15px">{i}. {_html.escape(it['title'])} — {_html.escape(it['company'])}</strong>
    <span style="background:#111;color:#fff;border-radius:6px;padding:2px 8px;font-size:12px">
      {it['final_score']:.0f}</span>
  </div>
  <div style="color:#555;font-size:13px;margin-top:4px">
    {_html.escape(it['location'])} · {it['age']} · match {it['match_overall']}/100</div>
  <div style="margin-top:6px;font-size:13px">
    Sponsorship: <span style="color:{color};font-weight:600">{label}</span>
    <span style="color:#888">(confidence {it['sponsor_conf']:.0%}{verify})</span></div>
  <div style="margin-top:6px;font-size:12px;color:#444">Why ranked here: {_html.escape(it['why'] or '—')}</div>
  <ul style="margin:6px 0 0 18px;font-size:12px;color:#444">{strengths}</ul>
  <div style="margin-top:8px"><a href="{_html.escape(it['apply_url'])}"
     style="font-size:13px;color:#1a56db">Apply / view posting →</a></div>
</div>""")
    body = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
max-width:680px;margin:0 auto;padding:16px;color:#111">
<h2 style="margin:0 0 4px">🔥 Today's SWE Opportunities</h2>
<div style="color:#666;font-size:13px">{date} · top {len(items)} of your matches</div>
{''.join(cards)}
<hr style="border:none;border-top:1px solid #eee;margin:18px 0">
<p style="font-size:11px;color:#999">This is an informational screening tool, not legal or
immigration advice. Sponsorship values are evidence summaries with confidence levels and must be
independently verified.</p>
</body></html>"""
    return subject, body


def generate_and_send(top_k: int = 15) -> dict[str, Any]:
    settings = get_settings()
    items = collect_top(top_k)
    if not items:
        log.warning("digest_empty", detail="No scored jobs — run enrich first.")
        return {"status": "empty", "items": 0}
    subject, body = build_digest(items)

    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"digest_{datetime.now(timezone.utc):%Y%m%d}.html"
    out_file.write_text(body, encoding="utf-8")

    emailed = False
    if settings.smtp_user and settings.smtp_password and settings.digest_to:
        from job_agent.digest.email import send_email

        try:
            send_email(subject, body)
            emailed = True
        except Exception as exc:  # never let email failure crash the run
            log.error("digest_email_failed", error=str(exc))

    log.info("digest_built", items=len(items), file=str(out_file), emailed=emailed)
    return {"status": "ok", "items": len(items), "file": str(out_file), "emailed": emailed}
