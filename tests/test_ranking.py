from datetime import datetime, timedelta

from job_agent.ranking.ranker import FACTORS, RankInputs, rank
from job_agent.schemas.core import (
    ClaimType,
    JobMatch,
    SponsorshipAssessment,
    SponsorshipStatus,
)

CONFIG = {
    "weights": {
        "role_match": 0.20,
        "technical_match": 0.20,
        "resume_match": 0.20,
        "authorization_match": 0.15,
        "experience_match": 0.10,
        "location_match": 0.05,
        "company_preference": 0.05,
        "recency": 0.05,
    },
    "recency": {"full_days": 2, "zero_days": 21},
}


def _match(**over):
    base = dict(
        overall=90, technical=90, experience=80, education=95,
        domain=80, location=100, authorization=70, seniority=90,
    )
    base.update(over)
    return JobMatch(**base)


def _spon(status):
    return SponsorshipAssessment(
        status=status, claim_type=ClaimType.INFERENCE, confidence=0.6, reason="test"
    )


def test_perfect_scores_cap_at_100():
    inp = RankInputs(
        job_id="1",
        match=_match(overall=100, technical=100, experience=100, location=100),
        sponsorship=_spon(SponsorshipStatus.YES),
        role_match=100,
        company_preference=100,
        posting_date=datetime.utcnow(),
    )
    result = rank(inp, CONFIG)
    assert result.final_score == 100.0
    assert set(result.components) == set(FACTORS)


def test_components_sum_to_final_score():
    inp = RankInputs(
        job_id="2",
        match=_match(),
        sponsorship=_spon(SponsorshipStatus.UNKNOWN),
        role_match=80,
        company_preference=50,
        posting_date=datetime.utcnow() - timedelta(days=10),
    )
    result = rank(inp, CONFIG)
    assert abs(sum(result.components.values()) - result.final_score) < 0.01


def test_sponsorship_no_tanks_authorization_component():
    common = dict(job_id="3", match=_match(), role_match=80, company_preference=50,
                  posting_date=datetime.utcnow())
    yes = rank(RankInputs(sponsorship=_spon(SponsorshipStatus.YES), **common), CONFIG)
    no = rank(RankInputs(sponsorship=_spon(SponsorshipStatus.NO), **common), CONFIG)
    assert yes.components["authorization_match"] > no.components["authorization_match"]
    assert no.components["authorization_match"] == 0.0
    assert yes.final_score > no.final_score


def test_recency_decays_with_age():
    common = dict(job_id="4", match=_match(), sponsorship=_spon(SponsorshipStatus.YES),
                  role_match=80, company_preference=50)
    fresh = rank(RankInputs(posting_date=datetime.utcnow(), **common), CONFIG)
    old = rank(RankInputs(posting_date=datetime.utcnow() - timedelta(days=30), **common), CONFIG)
    assert fresh.components["recency"] > old.components["recency"]
    assert old.components["recency"] == 0.0


def test_weight_change_is_reflected():
    inp = RankInputs(job_id="5", match=_match(technical=100, location=0),
                     sponsorship=_spon(SponsorshipStatus.YES), role_match=0, company_preference=0,
                     posting_date=datetime.utcnow())
    tech_heavy = {"weights": {"technical_match": 1.0}, "recency": CONFIG["recency"]}
    loc_heavy = {"weights": {"location_match": 1.0}, "recency": CONFIG["recency"]}
    assert rank(inp, tech_heavy).final_score == 100.0
    assert rank(inp, loc_heavy).final_score == 0.0
