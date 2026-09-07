"""Feedback loop: suggestions are bounded, renormalized, and reflect decision signal."""
import contextlib
import importlib
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from job_agent.db.base import Base
from job_agent.db.models import Application, Candidate, Company, Job, JobMatch
from job_agent.ranking.ranker import FACTORS


def _wire(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextlib.contextmanager
    def fake_session():
        s = factory()
        try:
            yield s; s.commit()
        finally:
            s.close()

    mod = importlib.import_module("job_agent.feedback.analyzer")
    monkeypatch.setattr(mod, "get_session", fake_session)
    monkeypatch.setattr(mod, "HISTORY_PATH", __import__("pathlib").Path("/tmp/ja_hist.jsonl"))
    return factory


def _job(s, comp, title, i):
    j = Job(dedup_key=f"k{i}", company_id=comp.id, title=title, title_norm=title.lower(),
            source_url="http://x", source_id="t",
            first_seen_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc), freshness="NEW")
    s.add(j); s.flush()
    return j


def _seed(factory):
    s = factory()
    cand = Candidate(name="S", email="s@x", needs_sponsorship=True, profile_json="{}")
    comp = Company(name="C", name_norm="c"); s.add_all([cand, comp]); s.flush()
    # Positive jobs: high technical contribution. Negative: high location, low technical.
    for i in range(4):
        j = _job(s, comp, f"backend {i}", i)
        s.add(JobMatch(job_id=j.id, candidate_id=cand.id, overall=80, technical=90, experience=80,
                       education=90, domain=80, location=40, authorization=40, seniority=90,
                       final_score=70, strengths_json="[]", gaps_json="[]",
                       rank_components_json=json.dumps({"technical_match": 18, "location_match": 2})))
        s.add(Application(job_id=j.id, candidate_id=cand.id, status="SHORTLISTED"))
    for i in range(4, 6):
        j = _job(s, comp, f"frontend {i}", i)
        s.add(JobMatch(job_id=j.id, candidate_id=cand.id, overall=60, technical=30, experience=80,
                       education=90, domain=60, location=100, authorization=40, seniority=90,
                       final_score=55, strengths_json="[]", gaps_json="[]",
                       rank_components_json=json.dumps({"technical_match": 6, "location_match": 5})))
        s.add(Application(job_id=j.id, candidate_id=cand.id, status="REJECTED"))
    s.commit(); s.close()


def test_insufficient_data(monkeypatch):
    _wire(monkeypatch)
    from job_agent.feedback.analyzer import analyze
    assert analyze()["status"] == "insufficient_data"


def test_suggestions_bounded_and_signaled(monkeypatch):
    factory = _wire(monkeypatch)
    _seed(factory)
    from job_agent.feedback.analyzer import analyze
    s = analyze()
    assert s["status"] == "ok"
    assert abs(sum(s["proposed_weights"].values()) - 1.0) < 0.01   # renormalized
    assert set(s["proposed_weights"]) == set(FACTORS)
    # technical drove liked jobs -> its weight should not drop below current
    assert s["proposed_weights"]["technical_match"] >= s["current_weights"]["technical_match"] - 1e-9
