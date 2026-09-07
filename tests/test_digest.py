from job_agent.digest.builder import build_digest

ITEMS = [
    {
        "company": "Scale AI", "title": "Software Engineer Intern", "location": "SF",
        "apply_url": "https://job-boards.greenhouse.io/scaleai/jobs/1", "final_score": 88.0,
        "match_overall": 84, "freshness": "NEW", "age": "2d ago",
        "sponsor_status": "UNKNOWN", "sponsor_conf": 0.0, "needs_verification": True,
        "why": "role_match +20, technical +18", "strengths": ["Skill match: python"],
    }
]


def test_build_digest_returns_subject_and_html():
    subject, body = build_digest(ITEMS)
    assert "1 top matches" in subject
    assert "Scale AI" in body and "Software Engineer Intern" in body
    assert "88" in body


def test_digest_shows_sponsorship_and_disclaimer():
    _, body = build_digest(ITEMS)
    assert "Sponsorship" in body
    assert "verification recommended" in body  # needs_verification flagged
    assert "not legal or" in body.lower() or "not legal" in body.lower()


def test_digest_links_to_apply():
    _, body = build_digest(ITEMS)
    assert "greenhouse.io/scaleai/jobs/1" in body
