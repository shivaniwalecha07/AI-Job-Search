"""CLI entrypoints (see ARCHITECTURE.md 13). `job-agent --help` lists commands.

Each stage is its own command so cron can call exactly the unattended lane. The supervised
lane (--supervised, includes LinkedIn) must be run by a present human, never from cron.
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from job_agent.observability import get_logger
from job_agent.pipeline import stages

app = typer.Typer(add_completion=False, help="Human-in-the-loop SWE job-search agent.")
console = Console()
log = get_logger("cli")


@app.command()
def run(
    stage: str = typer.Option("discovery", help="Stage to run: discovery | digest"),
    supervised: bool = typer.Option(
        False, "--supervised", help="Include supervised connectors (LinkedIn). Run only when present."
    ),
) -> None:
    """Run a pipeline stage. Without --supervised this is the cron-safe unattended lane."""
    if supervised:
        result = stages.run_discovery(supervised=True)
        console.print({"stage": "discovery", "lane": "supervised", **result})
        return
    if stage not in stages.STAGES:
        raise typer.BadParameter(f"Unknown stage {stage!r}. Options: {list(stages.STAGES)}")
    result = stages.STAGES[stage](False)
    console.print({"stage": stage, "lane": "unattended", "result": result})


@app.command()
def sources() -> None:
    """List configured connectors and their supervision lane."""
    config = stages.load_source_config()
    table = Table(title="Configured connectors")
    table.add_column("id"); table.add_column("type"); table.add_column("enabled")
    table.add_column("lane")
    for c in config.get("connectors", []):
        lane = "supervised" if c.get("requires_supervision") else "unattended"
        table.add_row(c["id"], c["type"], str(c.get("enabled", False)), lane)
    console.print(table)


@app.command()
def init_db() -> None:
    """Dev convenience: create all tables (and pgvector extension on Postgres). Use Alembic for prod."""
    from sqlalchemy import text

    from job_agent.db.base import Base, get_engine
    import job_agent.db.models  # noqa: F401  (register tables)

    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    console.print(f"[green]Database initialized ({engine.dialect.name}): tables created.[/green]")


@app.command()
def jobs(
    limit: int = typer.Option(20, help="How many jobs to show."),
    new_only: bool = typer.Option(False, "--new-only", help="Only jobs still marked NEW."),
) -> None:
    """List jobs currently in the database (most recently seen first)."""
    from datetime import datetime

    from sqlalchemy import func, select

    from job_agent.db.base import get_session
    from job_agent.db.models import Company, Job

    with get_session() as session:
        stmt = select(Job, Company).join(Company, Job.company_id == Company.id)
        if new_only:
            stmt = stmt.where(Job.freshness == "NEW")
        stmt = stmt.order_by(Job.last_seen_at.desc()).limit(limit)
        rows = session.execute(stmt).all()
        total = session.scalar(select(func.count(Job.id)))

    table = Table(title=f"Jobs in DB (showing {len(rows)} of {total})")
    table.add_column("ID"); table.add_column("Company"); table.add_column("Role")
    table.add_column("Location"); table.add_column("ATS"); table.add_column("Fresh")
    table.add_column("Age")
    for job, company in rows:
        age = ""
        if job.posting_date:
            age = f"{(datetime.now(job.posting_date.tzinfo) - job.posting_date).days}d"
        table.add_row(
            str(job.id), company.name, job.title[:44], (job.location or "")[:22],
            job.ats or "", job.freshness, age,
        )
    console.print(table)


@app.command()
def top(limit: int = typer.Option(15, help="Top jobs by final rank score.")) -> None:
    """Show the highest-ranked jobs after enrichment (score + match + sponsorship)."""
    from sqlalchemy import select

    from job_agent.db.base import get_session
    from job_agent.db.models import Company, Job, JobMatch, SponsorshipAssessment

    with get_session() as session:
        stmt = (
            select(Job, Company, JobMatch, SponsorshipAssessment)
            .join(Company, Job.company_id == Company.id)
            .join(JobMatch, JobMatch.job_id == Job.id)
            .outerjoin(SponsorshipAssessment, SponsorshipAssessment.job_id == Job.id)
            .order_by(JobMatch.final_score.desc()).limit(limit)
        )
        rows = session.execute(stmt).all()

    table = Table(title=f"Top {len(rows)} ranked jobs")
    table.add_column("ID"); table.add_column("Score"); table.add_column("Match")
    table.add_column("Company"); table.add_column("Role"); table.add_column("Sponsorship")
    for job, company, m, spon in rows:
        table.add_row(
            str(job.id), f"{m.final_score:.1f}" if m.final_score else "-", f"{m.overall}",
            company.name[:20], job.title[:38],
            f"{spon.status if spon else 'UNKNOWN'}{' ⚠️' if (spon and spon.needs_human_verification) else ''}",
        )
    console.print(table)


@app.command()
def shortlist(job_ids: list[int] = typer.Argument(..., help="Job IDs to shortlist.")) -> None:
    """Shortlist jobs (creates applications, advances them to SHORTLISTED)."""
    from job_agent.application.service import get_candidate, shortlist_jobs
    from job_agent.db.base import get_session

    with get_session() as session:
        cand = get_candidate(session)
        if not cand:
            console.print("[red]No candidate. Run `job-agent load-profile` first.[/red]")
            raise typer.Exit(1)
        done = shortlist_jobs(session, job_ids, cand.id)
    console.print(f"[green]Shortlisted {len(done)} job(s):[/green] {done}")


@app.command()
def reject(job_ids: list[int] = typer.Argument(..., help="Job IDs to mark not interested.")) -> None:
    """Mark jobs as not interested (records a negative signal for the feedback loop)."""
    from job_agent.application.service import advance_to, get_candidate, get_or_create_application
    from job_agent.application.states import ApplicationStatus
    from job_agent.db.base import get_session

    with get_session() as session:
        cand = get_candidate(session)
        if not cand:
            console.print("[red]No candidate. Run `job-agent load-profile` first.[/red]")
            raise typer.Exit(1)
        done = []
        for jid in job_ids:
            app_row = get_or_create_application(session, jid, cand.id)
            if advance_to(session, app_row, ApplicationStatus.WITHDRAWN, actor="human", detail="rejected"):
                done.append(jid)
    console.print(f"[green]Marked {len(done)} job(s) not interested:[/green] {done}")


@app.command()
def prepare(job_ids: list[int] = typer.Argument(..., help="Job IDs to prepare applications for.")) -> None:
    """Prepare application packages (resume, cover-letter draft, classified answers). Stops at AWAITING_REVIEW."""
    from job_agent.application.service import get_candidate, prepare_applications
    from job_agent.db.base import get_session
    from job_agent.profile import load_profile

    profile = load_profile()
    with get_session() as session:
        cand = get_candidate(session)
        if not cand:
            console.print("[red]No candidate. Run `job-agent load-profile` first.[/red]")
            raise typer.Exit(1)
        results = prepare_applications(session, job_ids, cand.id, profile)
    for r in results:
        console.print(f"[green]App {r['app_id']}[/green] (job {r['job_id']}) → AWAITING_REVIEW")
        if r["questions_for_you"]:
            console.print(f"  Questions requiring you: {r['questions_for_you']}")
        if r["concerns"]:
            console.print(f"  [yellow]Concerns:[/yellow] {r['concerns']}")


@app.command()
def applications() -> None:
    """List applications and their status."""
    from sqlalchemy import select

    from job_agent.db.base import get_session
    from job_agent.db.models import Application, Company, Job

    with get_session() as session:
        rows = session.execute(
            select(Application, Job, Company)
            .join(Job, Application.job_id == Job.id)
            .join(Company, Job.company_id == Company.id)
            .order_by(Application.updated_at.desc())
        ).all()

    table = Table(title=f"Applications ({len(rows)})")
    table.add_column("App"); table.add_column("Status"); table.add_column("Company"); table.add_column("Role")
    for app_row, job, company in rows:
        table.add_row(str(app_row.id), app_row.status, company.name[:22], job.title[:40])
    console.print(table)


@app.command()
def review(app_id: int = typer.Argument(..., help="Application ID to review.")) -> None:
    """Show the review package for an application (resume, cover letter, answers, concerns)."""
    from sqlalchemy import select

    from job_agent.db.base import get_session
    from job_agent.db.models import Application, ApplicationAnswer, Company, Job

    with get_session() as session:
        row = session.execute(
            select(Application, Job, Company)
            .join(Job, Application.job_id == Job.id)
            .join(Company, Job.company_id == Company.id)
            .where(Application.id == app_id)
        ).first()
        if not row:
            console.print(f"[red]No application {app_id}[/red]")
            raise typer.Exit(1)
        app_row, job, company = row
        answers = session.scalars(
            select(ApplicationAnswer).where(ApplicationAnswer.application_id == app_id)
        ).all()

    console.print(f"[bold]APPLICATION REVIEW — App {app_id} · {app_row.status}[/bold]")
    console.print(f"Company: {company.name}\nRole: {job.title}\nNotes: {app_row.notes or ''}")
    console.print(f"\n[bold]Cover letter[/bold]\n{app_row.cover_letter or '(none)'}")
    console.print("\n[bold]Answers[/bold]")
    for a in answers:
        console.print(f"  [{a.classification}] {a.question}")
        if a.draft_answer:
            console.print(f"      → {a.draft_answer}")
    console.print("\n[yellow]Approve with `job-agent approve %d`, then submit yourself, then `job-agent submit %d`.[/yellow]" % (app_id, app_id))


@app.command()
def approve(app_id: int = typer.Argument(...)) -> None:
    """Approve an application (human action: AWAITING_REVIEW → APPROVED)."""
    _human_transition(app_id, "APPROVED")


@app.command()
def submit(app_id: int = typer.Argument(...)) -> None:
    """Mark an application submitted AFTER you submitted it yourself (APPROVED → SUBMITTED)."""
    _human_transition(app_id, "SUBMITTED")


def _human_transition(app_id: int, target_name: str) -> None:
    from job_agent.application.states import ApplicationStatus
    from job_agent.application.service import transition
    from job_agent.db.base import get_session
    from job_agent.db.models import Application

    with get_session() as session:
        app_row = session.get(Application, app_id)
        if not app_row:
            console.print(f"[red]No application {app_id}[/red]")
            raise typer.Exit(1)
        ok = transition(session, app_row, ApplicationStatus(target_name), actor="human")
    if ok:
        console.print(f"[green]App {app_id} → {target_name}[/green]")
    else:
        console.print(f"[red]Cannot move app {app_id} to {target_name} from its current state.[/red]")


@app.command()
def load_profile() -> None:
    """Load config/profile.yaml into the DB as the candidate (needed before shortlist/prepare)."""
    from job_agent.db.base import get_session
    from job_agent.profile import bootstrap_candidate, load_profile as _load, register_master_resume

    profile = _load()
    with get_session() as session:
        cand = bootstrap_candidate(session, profile)
        resume = register_master_resume(session, cand, profile)
        cid, cname = cand.id, cand.name
        rpath = resume.source_path if resume else None
    console.print(f"[green]Candidate loaded:[/green] {cname or '(unnamed)'} (id={cid})")
    if rpath:
        console.print(f"[green]Master resume registered:[/green] {rpath}")


@app.command()
def feedback(apply_changes: bool = typer.Option(False, "--apply", help="Apply suggested weights (backs up current).")) -> None:
    """Suggest ranking-weight changes from your shortlist/reject history (transparent, reversible)."""
    from job_agent.feedback import analyze, apply_weights

    s = analyze()
    if s["status"] == "insufficient_data":
        console.print(f"[yellow]{s['message']}[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Weight suggestions ({s['n_positive']} liked / {s['n_negative']} rejected)")
    table.add_column("Factor"); table.add_column("Current"); table.add_column("Proposed")
    for f, prop in s["proposed_weights"].items():
        cur = s["current_weights"].get(f, 0.0)
        table.add_row(f, f"{cur:.3f}", f"{prop:.3f}")
    console.print(table)
    console.print(f"Rationale: {s['rationale']}")
    if apply_changes:
        backup = apply_weights(s["proposed_weights"])
        console.print(f"[green]Applied new weights. Backup at {backup}. Re-run `enrich` to re-score.[/green]")
    else:
        console.print("[cyan]Logged to config/ranking.history.jsonl. Re-run with --apply to apply.[/cyan]")


@app.command()
def dashboard(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8000)) -> None:
    """Launch the web dashboard (jobs, sponsorship/match, applications)."""
    import uvicorn

    from job_agent.dashboard import create_app

    console.print(f"[green]Dashboard at http://{host}:{port}[/green]")
    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def test_email() -> None:
    """Send a single test email to DIGEST_TO to verify your SMTP/.env setup."""
    from job_agent.digest.email import send_email
    from job_agent.settings import get_settings

    s = get_settings()
    missing = [k for k, v in {
        "SMTP_HOST": s.smtp_host, "SMTP_USER": s.smtp_user,
        "SMTP_PASSWORD": s.smtp_password, "DIGEST_TO": s.digest_to,
    }.items() if not v]
    if missing:
        console.print(f"[red]Missing in .env:[/red] {', '.join(missing)}")
        raise typer.Exit(1)

    console.print(f"Sending test email to {s.digest_to} via {s.smtp_host}:{s.smtp_port} …")
    try:
        send_email(
            "job-agent — email delivery works ✅",
            "<div style='font-family:sans-serif'><h2>It works 🎉</h2>"
            "<p>Your job-agent digest email is configured correctly. "
            "Daily digests will arrive here.</p></div>",
        )
    except Exception as exc:
        console.print(f"[red]Send failed:[/red] {exc}")
        console.print("[yellow]Common causes:[/yellow] 2-Step Verification off, wrong App Password, "
                      "or SMTP blocked by your network.")
        raise typer.Exit(1)
    console.print(f"[green]Sent![/green] Check {s.digest_to} (peek in Spam the first time).")


@app.command()
def status() -> None:
    """Show scaffold status."""
    console.print("job-agent scaffold — see README.md for component status.")


if __name__ == "__main__":
    app()
