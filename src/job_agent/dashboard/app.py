"""FastAPI dashboard (see ARCHITECTURE.md 17). Server-rendered HTML, no build step.

Views: jobs list (filter by score/sponsorship/freshness, sort), job detail (sponsorship
evidence + match breakdown), application tracker. Actions: shortlist, reject, prepare,
approve, submit — approve/submit are human-only, enforced by the state machine.
"""
from __future__ import annotations

import html
import json
from typing import Any

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from job_agent.application.service import (
    advance_to,
    get_or_create_application,
    prepare_applications,
    transition,
)
from job_agent.application.states import ApplicationStatus
from job_agent.db.base import get_session
from job_agent.db.models import (
    Application,
    Company,
    Job,
    JobMatch,
    SponsorshipAssessment,
    SponsorshipEvidence,
)
from job_agent.profile import bootstrap_candidate, load_profile

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1024px;margin:0 auto;padding:16px;color:#111}
a{color:#1a56db;text-decoration:none} a:hover{text-decoration:underline}
table{border-collapse:collapse;width:100%;font-size:13px} th,td{padding:7px 9px;border-bottom:1px solid #eee;text-align:left}
th{background:#fafafa} .badge{border-radius:6px;padding:2px 7px;font-size:11px;color:#fff}
.score{background:#111;color:#fff;border-radius:6px;padding:2px 7px;font-weight:600}
.bar{display:inline-block;height:8px;background:#1a56db;border-radius:4px} .muted{color:#777}
form.inline{display:inline} button{cursor:pointer;border:1px solid #ccc;background:#fff;border-radius:6px;padding:4px 10px;font-size:12px}
button.primary{background:#111;color:#fff;border-color:#111} nav a{margin-right:14px;font-weight:600}
.filters input,.filters select{padding:5px;margin-right:6px;border:1px solid #ccc;border-radius:6px}
"""

_SPON_COLOR = {"YES": "#1a7f37", "NO": "#b42318", "UNKNOWN": "#6c757d"}


def _color(status: str) -> str:
    return _SPON_COLOR.get(status, "#b54708")


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<nav><a href='/'>Jobs</a><a href='/applications'>Applications</a></nav><hr>"
            f"{body}</body></html>")


def _candidate_id(session) -> int:
    from job_agent.db.models import Candidate

    cand = session.scalar(select(Candidate).limit(1))
    if cand is None:
        cand = bootstrap_candidate(session, load_profile())
    return cand.id


def create_app() -> FastAPI:
    app = FastAPI(title="job-agent dashboard")

    @app.get("/", response_class=HTMLResponse)
    def jobs_list(q: str = "", min_score: float = 0.0, sponsorship: str = "",
                  freshness: str = "", sort: str = "score") -> str:
        with get_session() as session:
            stmt = (select(Job, Company, JobMatch, SponsorshipAssessment)
                    .join(Company, Job.company_id == Company.id)
                    .join(JobMatch, JobMatch.job_id == Job.id)
                    .outerjoin(SponsorshipAssessment, SponsorshipAssessment.job_id == Job.id))
            if q:
                like = f"%{q.lower()}%"
                stmt = stmt.where((Job.title_norm.like(like)) | (Company.name_norm.like(like)))
            if min_score:
                stmt = stmt.where(JobMatch.final_score >= min_score)
            if sponsorship:
                stmt = stmt.where(SponsorshipAssessment.status == sponsorship)
            if freshness:
                stmt = stmt.where(Job.freshness == freshness)
            order = JobMatch.overall.desc() if sort == "match" else JobMatch.final_score.desc()
            rows = session.execute(stmt.order_by(order).limit(100)).all()

            filters = (
                "<form class='filters' method='get'>"
                f"<input name='q' placeholder='search…' value='{html.escape(q)}'>"
                f"<input name='min_score' type='number' step='1' placeholder='min score' value='{min_score or ''}'>"
                "<select name='sponsorship'>"
                + "".join(f"<option{' selected' if sponsorship==o else ''}>{o}</option>"
                          for o in ["", "YES", "NO", "UNKNOWN", "UNCLEAR", "JOB_SPECIFIC"])
                + "</select>"
                "<select name='sort'>"
                + "".join(f"<option value='{v}'{' selected' if sort==v else ''}>{lbl}</option>"
                          for v, lbl in [("score", "sort: score"), ("match", "sort: match")])
                + "</select><button class='primary'>Filter</button></form>")

            body_rows = []
            for job, company, m, spon in rows:
                s = spon.status if spon else "UNKNOWN"
                verify = " ⚠️" if (spon and spon.needs_human_verification) else ""
                body_rows.append(
                    f"<tr><td><span class='score'>{(m.final_score or 0):.0f}</span></td>"
                    f"<td>{m.overall}</td>"
                    f"<td><a href='/job/{job.id}'>{html.escape(job.title[:52])}</a></td>"
                    f"<td>{html.escape(company.name[:26])}</td>"
                    f"<td>{html.escape((job.location or '')[:22])}</td>"
                    f"<td><span class='badge' style='background:{_color(s)}'>{s}{verify}</span></td>"
                    f"<td><form class='inline' method='post' action='/shortlist/{job.id}'>"
                    f"<button>Shortlist</button></form></td></tr>")
            table = ("<table><tr><th>Score</th><th>Match</th><th>Role</th><th>Company</th>"
                     "<th>Location</th><th>Sponsorship</th><th></th></tr>" + "".join(body_rows) + "</table>")
            return _page("Jobs", f"<h2>Jobs — {len(rows)} shown</h2>{filters}{table}")

    @app.get("/job/{job_id}", response_class=HTMLResponse)
    def job_detail(job_id: int) -> str:
        with get_session() as session:
            row = session.execute(
                select(Job, Company, JobMatch, SponsorshipAssessment)
                .join(Company, Job.company_id == Company.id)
                .outerjoin(JobMatch, JobMatch.job_id == Job.id)
                .outerjoin(SponsorshipAssessment, SponsorshipAssessment.job_id == Job.id)
                .where(Job.id == job_id)).first()
            if not row:
                return _page("Not found", "<p>No such job.</p>")
            job, company, m, spon = row
            evidence = session.scalars(
                select(SponsorshipEvidence).where(SponsorshipEvidence.job_id == job_id)).all()

            spon_html = "<p class='muted'>Not assessed.</p>"
            if spon:
                ev = "".join(
                    f"<li>[{e.claim_type}] {html.escape(e.evidence_text or '')} "
                    f"<span class='muted'>({e.source_type}, conf {e.confidence:.0%}"
                    f"{', historical' if e.is_historical else ''})</span></li>" for e in evidence)
                spon_html = (
                    f"<p><b>Status:</b> <span class='badge' style='background:{_color(spon.status)}'>"
                    f"{spon.status}</span> · confidence {spon.confidence:.0%}"
                    f"{' · ⚠️ verify' if spon.needs_human_verification else ''}</p>"
                    f"<p>{html.escape(spon.reason)}</p><ul>{ev or '<li class=muted>No evidence rows.</li>'}</ul>")

            match_html = "<p class='muted'>Not scored.</p>"
            if m:
                subs = [("Technical", m.technical), ("Domain", m.domain), ("Experience", m.experience),
                        ("Education", m.education), ("Location", m.location), ("Auth", m.authorization),
                        ("Seniority", m.seniority)]
                bars = "".join(
                    f"<tr><td>{n}</td><td><span class='bar' style='width:{v}px'></span> {v}</td></tr>"
                    for n, v in subs)
                strengths = "".join(f"<li>{html.escape(s)}</li>" for s in json.loads(m.strengths_json or "[]"))
                gaps = "".join(f"<li>{html.escape(s)}</li>" for s in json.loads(m.gaps_json or "[]"))
                match_html = (
                    f"<p><b>Overall {m.overall}/100</b> · rank score "
                    f"<span class='score'>{(m.final_score or 0):.0f}</span></p><table>{bars}</table>"
                    f"<p><b>Strengths</b></p><ul>{strengths or '<li class=muted>—</li>'}</ul>"
                    f"<p><b>Gaps</b></p><ul>{gaps or '<li class=muted>—</li>'}</ul>")

            apply = job.apply_url or job.source_url
            actions = (
                f"<form class='inline' method='post' action='/shortlist/{job.id}'><button class='primary'>Shortlist</button></form> "
                f"<form class='inline' method='post' action='/reject/{job.id}'><button>Not interested</button></form> "
                f"<form class='inline' method='post' action='/prepare/{job.id}'><button>Prepare application</button></form>")
            return _page(job.title, (
                f"<h2>{html.escape(job.title)}</h2>"
                f"<p><b>{html.escape(company.name)}</b> · {html.escape(job.location or '')} · "
                f"{html.escape(job.employment_type or '')} · <a href='{html.escape(apply)}'>Apply ↗</a></p>"
                f"<p>{actions}</p><hr><h3>Sponsorship</h3>{spon_html}<hr><h3>Match</h3>{match_html}"))

    @app.post("/shortlist/{job_id}")
    def do_shortlist(job_id: int):
        with get_session() as session:
            app_row = get_or_create_application(session, job_id, _candidate_id(session))
            advance_to(session, app_row, ApplicationStatus.SHORTLISTED, actor="human", detail="dashboard shortlist")
        return RedirectResponse(f"/job/{job_id}", status_code=303)

    @app.post("/reject/{job_id}")
    def do_reject(job_id: int):
        with get_session() as session:
            app_row = get_or_create_application(session, job_id, _candidate_id(session))
            advance_to(session, app_row, ApplicationStatus.WITHDRAWN, actor="human", detail="dashboard reject")
        return RedirectResponse("/", status_code=303)

    @app.post("/prepare/{job_id}")
    def do_prepare(job_id: int):
        with get_session() as session:
            cid = _candidate_id(session)
            prepare_applications(session, [job_id], cid, load_profile())
        return RedirectResponse("/applications", status_code=303)

    @app.get("/applications", response_class=HTMLResponse)
    def applications_list() -> str:
        with get_session() as session:
            rows = session.execute(
                select(Application, Job, Company)
                .join(Job, Application.job_id == Job.id)
                .join(Company, Job.company_id == Company.id)
                .order_by(Application.updated_at.desc())).all()
            trs = []
            for app_row, job, company in rows:
                act = ""
                if app_row.status == "AWAITING_REVIEW":
                    act = (f"<form class='inline' method='post' action='/app/{app_row.id}/approve'>"
                           f"<button class='primary'>Approve</button></form>")
                elif app_row.status == "APPROVED":
                    act = (f"<form class='inline' method='post' action='/app/{app_row.id}/submit'>"
                           f"<button class='primary'>Mark submitted</button></form>")
                trs.append(f"<tr><td>{app_row.id}</td><td>{app_row.status}</td>"
                           f"<td>{html.escape(company.name[:24])}</td><td>{html.escape(job.title[:46])}</td>"
                           f"<td>{act}</td></tr>")
            table = ("<table><tr><th>App</th><th>Status</th><th>Company</th><th>Role</th><th></th></tr>"
                     + "".join(trs) + "</table>")
            return _page("Applications", f"<h2>Applications — {len(rows)}</h2>{table}")

    @app.post("/app/{app_id}/approve")
    def do_approve(app_id: int):
        _human(app_id, ApplicationStatus.APPROVED)
        return RedirectResponse("/applications", status_code=303)

    @app.post("/app/{app_id}/submit")
    def do_submit(app_id: int):
        _human(app_id, ApplicationStatus.SUBMITTED)
        return RedirectResponse("/applications", status_code=303)

    def _human(app_id: int, target: ApplicationStatus) -> None:
        with get_session() as session:
            app_row = session.get(Application, app_id)
            if app_row:
                transition(session, app_row, target, actor="human", detail="dashboard action")

    return app
