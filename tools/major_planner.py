"""
Helpers for combining degree progress, eligibility, and schedule fit.
"""

from __future__ import annotations

from typing import Callable

from tools.catalog_search.catalog_search import check_catalog_eligibility
from tools.degree_requirements.degree_requirements import evaluate_engineering_degree_progress
from tools.schedule_conflicts import check_schedule_fit


def evaluate_course_for_major_plan(
    course_code: str,
    major: str,
    classes_taken: list[str],
    planned_courses: list[str] | None = None,
    earliest_start: float | int | None = None,
    degree_progress_fetcher: Callable[[str, list[str]], dict] = evaluate_engineering_degree_progress,
    eligibility_fetcher: Callable[[str, list[str], list[str] | None], dict] = check_catalog_eligibility,
    schedule_fit_fetcher: Callable[[str, list[str] | None, float | int | None], dict] = check_schedule_fit,
) -> dict:
    progress = degree_progress_fetcher(major, classes_taken)
    normalized = course_code.strip().upper().replace(" ", "-")

    relevant_requirements = []
    for requirement in progress["unsatisfied_requirements"]:
        direct_match = normalized in requirement.get("codes", [])
        alternative_match = any(
            normalized in alternative.get("codes", [])
            for alternative in requirement.get("alternatives", [])
        )
        if direct_match or alternative_match:
            relevant_requirements.append({
                "section": requirement["section"],
                "label": requirement["label"],
                "direct_match": direct_match,
                "alternative_match": alternative_match,
            })

    eligibility = eligibility_fetcher(
        normalized,
        classes_taken=classes_taken,
        current_schedule=planned_courses or [],
    )
    schedule_fit = schedule_fit_fetcher(
        normalized,
        planned_courses=planned_courses or [],
        earliest_start=earliest_start,
    )

    return {
        "course_code": normalized,
        "major": progress["program"],
        "supports_major_plan": len(relevant_requirements) > 0,
        "relevant_requirements": relevant_requirements,
        "eligibility": eligibility,
        "schedule_fit": schedule_fit,
        "recommended_now": (
            len(relevant_requirements) > 0
            and eligibility.get("eligible", False)
            and schedule_fit.get("fits_schedule", False)
        ),
        "note": (
            "A course is marked recommended_now only if it helps with at least one "
            "currently unsatisfied course-based requirement, passes prerequisite and "
            "restriction checks, and has a feasible schedule bundle."
        ),
    }
