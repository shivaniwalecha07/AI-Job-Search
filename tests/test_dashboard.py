"""Dashboard smoke tests against an in-memory DB via dependency-free TestClient."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_agent.dashboard import create_app
from job_agent.db.base import Base


def _wire_memory_db(monkeypatch):
    # Shared single-connection in-memory DB so TestClient's worker thread sees the same data.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    import contextlib

    @contextlib.contextmanager
    def fake_session():
        s = factory()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    # Patch every module that imported get_session by name.
    for mod in ("job_agent.dashboard.app", "job_agent.application.service"):
        import importlib
        m = importlib.import_module(mod)
        if hasattr(m, "get_session"):
            monkeypatch.setattr(m, "get_session", fake_session)
    return factory


def _seed(factory):
    from datetime import datetime, timezone

    from job_agent.db.models import Candidate, Company, Job, JobMatch
    s = factory()
    cand = Candidate(name="S", email="s@x.com", needs_sponsorship=True, profile_json="{}")
    comp = Company(name="Acme", name_norm="acme")
    s.add_all([cand, comp]); s.flush()
    job = Job(dedup_key="acme|swe", company_id=comp.id, title="SWE Intern", title_norm="swe intern",
              location="Remote", source_url="http://x", source_id="github:test",
              first_seen_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc),
              freshness="NEW")
    s.add(job); s.flush()
    s.add(JobMatch(job_id=job.id, candidate_id=cand.id, overall=80, technical=80, experience=80,
                   education=90, domain=70, location=100, authorization=40, seniority=90,
                   final_score=66.0, rank_components_json="{}", strengths_json="[]", gaps_json="[]"))
    s.commit(); jid = job.id; s.close()
    return jid


def test_jobs_list_and_detail_render(monkeypatch):
    factory = _wire_memory_db(monkeypatch)
    jid = _seed(factory)
    client = TestClient(create_app())

    r = client.get("/")
    assert r.status_code == 200 and "SWE Intern" in r.text and "Acme" in r.text

    r = client.get(f"/job/{jid}")
    assert r.status_code == 200 and "Sponsorship" in r.text and "Match" in r.text


def test_shortlist_creates_application(monkeypatch):
    factory = _wire_memory_db(monkeypatch)
    jid = _seed(factory)
    client = TestClient(create_app())
    r = client.post(f"/shortlist/{jid}", follow_redirects=False)
    assert r.status_code == 303
    r = client.get("/applications")
    assert "SHORTLISTED" in r.text
