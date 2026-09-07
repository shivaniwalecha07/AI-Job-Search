"""Application prep agent (see ARCHITECTURE.md 11 & 12). Builds a review package; NEVER
advances past AWAITING_REVIEW on its own. Generation is constrained to verified profile facts
(no fabrication). Cover letter uses the LLM only if a key is configured; otherwise a factual
template assembled from the profile.
"""
from __future__ import annotations

from typing import Any

from job_agent.application.classify import classify_question
from job_agent.schemas.core import ApplicationPackage, QuestionClass

DEFAULT_QUESTIONS = [
    "Why do you want to work here?",
    "Describe your experience with your primary programming language.",
    "Are you authorized to work in the United States?",
    "Will you now or in the future require visa sponsorship?",
    "What is your expected graduation date?",
]


def _template_cover_letter(job: dict[str, Any], profile: dict[str, Any]) -> str:
    cand = profile.get("candidate", {}) or {}
    edu = (profile.get("education") or [{}])[0]
    skills = profile.get("skills", {}) or {}
    langs = ", ".join(skills.get("languages", []) or [])
    name = cand.get("name", "")
    return (
        f"Dear {job.get('company','Hiring Team')} team,\n\n"
        f"I'm excited to apply for the {job.get('title','role')} position. I'm a "
        f"{edu.get('degree','')} student at {edu.get('school','')} (expected {edu.get('graduation','')}), "
        f"with hands-on experience in {langs}. "
        f"I'd welcome the chance to contribute to your team.\n\n"
        f"Best regards,\n{name}\n\n"
        f"[DRAFT — review and personalize before sending. Assembled from your profile; nothing invented.]"
    )


def _llm_cover_letter(job: dict[str, Any], profile: dict[str, Any]) -> str | None:
    from job_agent.settings import get_settings

    if not get_settings().anthropic_api_key:
        return None
    try:
        from job_agent.llm import get_llm

        llm = get_llm()
        prompt = (
            "Write a concise, sincere 150-word cover letter. Use ONLY these verified facts; "
            "do not invent anything.\n"
            f"Candidate profile: {profile.get('candidate')}, education: {profile.get('education')}, "
            f"skills: {profile.get('skills')}.\n"
            f"Role: {job.get('title')} at {job.get('company')}.\n"
        )
        return llm.complete(prompt, system="You never fabricate experience or credentials.")
    except Exception:
        return None


def prepare(
    job: dict[str, Any],
    profile: dict[str, Any],
    *,
    sponsorship_status: str | None = None,
    match_overall: int | None = None,
    questions: list[str] | None = None,
) -> ApplicationPackage:
    resume_version = ((profile.get("resumes", {}) or {}).get("master")) or "master"
    cover_letter = _llm_cover_letter(job, profile) or _template_cover_letter(job, profile)

    answers = [classify_question(q, profile) for q in (questions or DEFAULT_QUESTIONS)]
    must_ask = [a.question for a in answers if a.classification == QuestionClass.MUST_ASK_USER]

    concerns: list[str] = []
    if sponsorship_status in {"UNKNOWN", "UNCLEAR", "NO", "JOB_SPECIFIC"}:
        concerns.append(f"Sponsorship status is {sponsorship_status} — verify before applying.")
    if match_overall is not None and match_overall < 60:
        concerns.append(f"Match score is low ({match_overall}/100).")

    return ApplicationPackage(
        job_id=str(job.get("id", "")),
        resume_version=resume_version,
        cover_letter=cover_letter,
        answers=answers,
        questions_requiring_user=must_ask,
        concerns=concerns,
    )
