from job_agent.schemas.core import ClaimType, SponsorshipEvidence, SponsorshipStatus
from job_agent.sponsorship.assessor import assess


def _job(desc="", employment_type="internship"):
    return {"description": desc, "employment_type": employment_type, "source_url": "http://x"}


def test_negative_statement_is_no_fact():
    a = assess(_job("This role is not able to sponsor visas now or in the future."))
    assert a.status == SponsorshipStatus.NO
    assert a.claim_type == ClaimType.FACT
    assert a.needs_human_verification is False
    assert a.evidence and a.evidence[0].evidence_text


def test_positive_statement_is_yes_fact():
    a = assess(_job("We will sponsor qualified candidates for work visas."))
    assert a.status == SponsorshipStatus.YES
    assert a.claim_type == ClaimType.FACT


def test_citizenship_requirement_flags_for_verification():
    a = assess(_job("Applicants must be a U.S. citizen due to security clearance."))
    assert a.status == SponsorshipStatus.NO
    assert a.needs_human_verification is True


def test_silence_with_no_history_is_unknown():
    a = assess(_job(""))
    assert a.status == SponsorshipStatus.UNKNOWN
    assert a.needs_human_verification is True
    assert a.evidence == []


def test_silence_with_history_is_job_specific_for_intern():
    hist = [SponsorshipEvidence(claim_type=ClaimType.INFERENCE, confidence=0.5,
                                source_type="uscis_datahub", source_url="http://u",
                                evidence_text="past H-1B", is_historical=True)]
    a = assess(_job("", employment_type="internship"), company_h1b_history=hist)
    assert a.status == SponsorshipStatus.JOB_SPECIFIC
    assert a.needs_human_verification is True
    assert a.evidence[0].is_historical is True


def test_conflict_is_unclear():
    a = assess(_job("We will sponsor. However applicants must be a U.S. citizen."))
    assert a.status == SponsorshipStatus.UNCLEAR
    assert a.needs_human_verification is True


def test_never_bare_yes_without_evidence():
    a = assess(_job("We will sponsor candidates."))
    assert a.evidence  # YES always carries the verbatim quote
