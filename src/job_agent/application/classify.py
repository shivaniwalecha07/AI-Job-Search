"""Application-question classification (see ARCHITECTURE.md 12).

Sensitive/legal/authorization/demographic questions -> MUST_ASK_USER (never auto-answered).
Open-ended motivation -> NEEDS_REVIEW (drafted but flagged). Factual profile questions ->
AUTO_ANSWERABLE (answered only from verified profile facts, with a source note).
"""
from __future__ import annotations

from typing import Any

from job_agent.schemas.core import ClassifiedAnswer, QuestionClass

_MUST_ASK = [
    "sponsor", "visa", "work authorization", "authorized to work", "citizen", "clearance",
    "felony", "convicted", "criminal", "background check", "gender", "race", "ethnicity",
    "veteran", "disability", "salary", "compensation", "expected pay", "relocat",
    "start date", "notice period", "reference", "certify", "acknowledge",
]
_NEEDS_REVIEW = [
    "why do you want", "why are you interested", "why this", "cover letter", "tell us about",
    "tell me about yourself", "describe a time", "greatest", "challenge", "passion",
    "what interests you", "proud", "weakness", "strength",
]
_FACTUAL = [
    "years of experience", "proficient", "do you have experience", "rate your",
    "programming language", "gpa", "graduat", "degree", "authorized university",
    "which of the following", "familiar with",
]


def _profile_answer(question: str, profile: dict[str, Any]) -> tuple[str | None, str | None]:
    q = question.lower()
    edu = (profile.get("education") or [{}])[0]
    skills = profile.get("skills", {}) or {}
    langs = ", ".join(skills.get("languages", []) or [])
    if "gpa" in q and edu.get("gpa"):
        return str(edu["gpa"]), "profile.education.gpa"
    if "graduat" in q and edu.get("graduation"):
        return f"Expected {edu['graduation']}", "profile.education.graduation"
    if "degree" in q and edu.get("degree"):
        return f"{edu.get('degree')} at {edu.get('school','')}".strip(), "profile.education"
    if ("programming language" in q or "proficient" in q or "familiar" in q) and langs:
        return f"Proficient in {langs}.", "profile.skills.languages"
    return None, None


def classify_question(question: str, profile: dict[str, Any] | None = None) -> ClassifiedAnswer:
    profile = profile or {}
    q = question.lower()

    if any(k in q for k in _MUST_ASK):
        return ClassifiedAnswer(
            question=question, classification=QuestionClass.MUST_ASK_USER,
            draft_answer=None,
            source_note="Sensitive/legal/authorization or judgment question — requires your input.",
        )

    if any(k in q for k in _FACTUAL):
        draft, note = _profile_answer(question, profile)
        if draft:
            return ClassifiedAnswer(
                question=question, classification=QuestionClass.AUTO_ANSWERABLE,
                draft_answer=draft, source_note=note,
            )
        return ClassifiedAnswer(
            question=question, classification=QuestionClass.NEEDS_REVIEW,
            draft_answer=None, source_note="Factual question but no matching profile field.",
        )

    if any(k in q for k in _NEEDS_REVIEW):
        return ClassifiedAnswer(
            question=question, classification=QuestionClass.NEEDS_REVIEW,
            draft_answer=None, source_note="Open-ended — draft with the prep agent, then review.",
        )

    return ClassifiedAnswer(
        question=question, classification=QuestionClass.NEEDS_REVIEW,
        draft_answer=None, source_note="Unclassified — review before answering.",
    )
