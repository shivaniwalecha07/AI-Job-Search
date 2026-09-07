from job_agent.matching.matcher import company_preference_score, match, role_match_score

PROFILE = {
    "education": [{"degree": "M.S. Computer Science"}],
    "preferences": {
        "employment_type": ["internship"],
        "arrangement": ["remote", "hybrid"],
        "locations_preferred": ["Seattle", "Bay Area", "Remote"],
        "target_companies": ["Stripe", "Scale AI"],
    },
    "skills": {"languages": ["Python", "Java"], "cloud": ["AWS"], "other": ["distributed systems"]},
}
ROLES = ["Software Engineer Intern Summer 2027", "Backend Engineering Intern"]


def test_role_match_high_for_aligned_title():
    assert role_match_score("Backend Engineering Intern", ROLES) >= 80
    assert role_match_score("Marketing Coordinator", ROLES) < 40


def test_company_preference():
    assert company_preference_score("Stripe, Inc.", PROFILE["preferences"]["target_companies"]) == 100
    assert company_preference_score("Nobody Corp", PROFILE["preferences"]["target_companies"]) == 0


def test_match_returns_bounded_subscores():
    job = {"title": "Software Engineer Intern", "employment_type": "internship", "location": "Seattle, WA"}
    m = match(job, PROFILE, ROLES)
    for v in (m.overall, m.technical, m.domain, m.location, m.experience, m.seniority, m.education):
        assert 0 <= v <= 100
    assert m.location == 100  # Seattle is preferred


def test_technical_flags_missing_description():
    job = {"title": "Software Engineer Intern", "employment_type": "internship"}
    m = match(job, PROFILE, ROLES)
    assert any("description" in g.lower() for g in m.gaps)


def test_skill_overlap_becomes_strength():
    job = {
        "title": "Backend Intern",
        "description": "Work with Python and AWS on distributed systems.",
        "employment_type": "internship",
        "location": "Remote",
    }
    m = match(job, PROFILE, ROLES)
    joined = " ".join(m.strengths).lower()
    assert "python" in joined and "aws" in joined
    assert m.resume_opportunities  # emphasize matched skills
