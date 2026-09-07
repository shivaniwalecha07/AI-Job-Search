from job_agent.normalize.dedup import (
    compute_dedup_key,
    normalize_company,
    normalize_title,
)


def test_company_suffix_stripped():
    assert normalize_company("Stripe, Inc.") == "stripe"
    assert normalize_company("Acme LLC") == "acme"
    assert normalize_company("OpenAI") == "openai"


def test_title_noise_removed():
    a = normalize_title("Software Engineer Intern (Summer 2027)")
    b = normalize_title("Software Engineer - Internship, Summer 2027")
    assert a == b == "software engineer"


def test_primary_key_uses_ats_id():
    k1 = compute_dedup_key("Stripe, Inc.", ats_job_id="12345")
    k2 = compute_dedup_key("stripe", ats_job_id="12345")
    assert k1 == k2 == "stripe|id:12345"


def test_fallback_key_when_no_ats_id():
    k1 = compute_dedup_key("Stripe", title="SWE Intern Summer 2027", location="Seattle, WA")
    k2 = compute_dedup_key("Stripe, Inc.", title="SWE Internship 2027", location="seattle wa")
    assert k1 == k2  # normalized company/title/location collapse to the same key


def test_different_roles_do_not_collide():
    backend = compute_dedup_key("Acme", title="Backend Engineer Intern", location="NYC")
    frontend = compute_dedup_key("Acme", title="Frontend Engineer Intern", location="NYC")
    assert backend != frontend
