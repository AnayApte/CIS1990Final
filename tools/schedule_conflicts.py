"""
Schedule fit checker for course recommendations.

Uses Penn Course Review section meeting times to determine whether a candidate
course has at least one enrollable bundle of sections that can fit alongside a
planned set of courses and any time-of-day preferences.
"""

from __future__ import annotations

from itertools import product
from typing import Callable

from tools.course_search.course_search import get_course_details


PRIMARY_ACTIVITY_CODES = ("LEC", "SEM")
SECONDARY_REQUIRED_ACTIVITY_CODES = ("REC", "LAB", "STU", "QUI")


def _time_float_to_minutes(value: float | int | None) -> int | None:
    if value is None:
        return None
    whole_hours = int(value)
    minute_component = int(round((float(value) - whole_hours) * 100))
    return whole_hours * 60 + minute_component


def _format_time(value: float | int | None) -> str:
    minutes = _time_float_to_minutes(value)
    if minutes is None:
        return ""
    hours = minutes // 60
    mins = minutes % 60
    suffix = "AM" if hours < 12 else "PM"
    display_hour = hours % 12 or 12
    return f"{display_hour}:{mins:02d} {suffix}"


def _normalize_course_code(course_code: str) -> str:
    return course_code.strip().upper().replace(" ", "-")


def _meetings_conflict(meetings_a: list[dict], meetings_b: list[dict]) -> bool:
    for meeting_a in meetings_a:
        for meeting_b in meetings_b:
            if meeting_a.get("day") != meeting_b.get("day"):
                continue
            start_a = _time_float_to_minutes(meeting_a.get("start"))
            end_a = _time_float_to_minutes(meeting_a.get("end"))
            start_b = _time_float_to_minutes(meeting_b.get("start"))
            end_b = _time_float_to_minutes(meeting_b.get("end"))
            if None in {start_a, end_a, start_b, end_b}:
                continue
            if start_a < end_b and start_b < end_a:
                return True
    return False


def _bundles_conflict(bundle_a: list[dict], bundle_b: list[dict]) -> bool:
    return any(
        _meetings_conflict(section_a.get("meetings", []), section_b.get("meetings", []))
        for section_a in bundle_a
        for section_b in bundle_b
    )


def _bundle_violates_earliest_start(bundle: list[dict], earliest_start: float | int | None) -> bool:
    if earliest_start is None:
        return False
    earliest_minutes = _time_float_to_minutes(earliest_start)
    return any(
        (
            _time_float_to_minutes(meeting.get("start")) is not None
            and _time_float_to_minutes(meeting.get("start")) < earliest_minutes
        )
        for section in bundle
        for meeting in section.get("meetings", [])
    )


def _section_summary(section: dict) -> dict:
    return {
        "section_id": section["section_id"],
        "activity": section.get("activity", ""),
        "status": section.get("status", ""),
        "meetings": section.get("meetings", []),
        "instructors": section.get("instructors", []),
    }


def _bundle_summary(bundle: list[dict]) -> list[dict]:
    return [_section_summary(section) for section in bundle]


def _open_sections_with_meetings(course_detail: dict) -> list[dict]:
    sections = []
    for section in course_detail.get("sections", []):
        if section.get("status") != "open":
            continue
        if not section.get("meetings"):
            continue
        sections.append(section)
    return sections


def _group_sections_by_activity(course_detail: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for section in _open_sections_with_meetings(course_detail):
        grouped.setdefault(section.get("activity", ""), []).append(section)
    return grouped


def _build_course_bundles(course_detail: dict) -> tuple[list[list[dict]], dict]:
    grouped = _group_sections_by_activity(course_detail)

    primary_sections = []
    for activity in PRIMARY_ACTIVITY_CODES:
        primary_sections.extend(grouped.get(activity, []))
    if not primary_sections:
        primary_sections = list(_open_sections_with_meetings(course_detail))

    required_groups = [
        grouped[activity]
        for activity in SECONDARY_REQUIRED_ACTIVITY_CODES
        if grouped.get(activity)
    ]

    bundles: list[list[dict]] = []
    if required_groups:
        for primary in primary_sections:
            for combo in product(*required_groups):
                bundle = [primary, *combo]
                if _bundle_has_internal_conflict(bundle):
                    continue
                bundles.append(bundle)
    else:
        bundles = [[primary] for primary in primary_sections]

    metadata = {
        "required_activity_types": [
            activity for activity in SECONDARY_REQUIRED_ACTIVITY_CODES if grouped.get(activity)
        ],
        "primary_activity_types": [
            activity for activity in PRIMARY_ACTIVITY_CODES if grouped.get(activity)
        ] or sorted({section.get("activity", "") for section in primary_sections}),
        "bundle_count": len(bundles),
    }
    return bundles, metadata


def _bundle_has_internal_conflict(bundle: list[dict]) -> bool:
    for index, section in enumerate(bundle):
        for other in bundle[index + 1:]:
            if _meetings_conflict(section.get("meetings", []), other.get("meetings", [])):
                return True
    return False


def _find_compatible_plan(
    candidate_bundle: list[dict],
    planned_options: list[tuple[str, list[list[dict]]]],
) -> list[dict] | None:
    assignments: list[dict] = []

    def backtrack(index: int) -> bool:
        if index == len(planned_options):
            return True

        course_code, bundles = planned_options[index]
        for bundle in bundles:
            if _bundles_conflict(candidate_bundle, bundle):
                continue
            if any(_bundles_conflict(bundle, existing["bundle"]) for existing in assignments):
                continue
            assignments.append({"course_code": course_code, "bundle": bundle})
            if backtrack(index + 1):
                return True
            assignments.pop()
        return False

    if backtrack(0):
        return assignments
    return None


def check_schedule_fit(
    course_code: str,
    planned_courses: list[str] | None = None,
    earliest_start: float | int | None = None,
    semester: str = "current",
    detail_fetcher: Callable[[str, str], dict] = get_course_details,
) -> dict:
    """
    Determine whether a candidate course can fit alongside planned courses.

    This check builds enrollable section bundles by combining one primary
    section (lecture or seminar when available) with one open section from each
    required secondary activity group such as recitation or lab.
    """
    normalized = _normalize_course_code(course_code)
    planned = [
        _normalize_course_code(code)
        for code in (planned_courses or [])
        if _normalize_course_code(code) != normalized
    ]

    candidate_detail = detail_fetcher(normalized, semester)
    candidate_bundles, candidate_meta = _build_course_bundles(candidate_detail)

    planned_details = {code: detail_fetcher(code, semester) for code in planned}
    planned_bundle_map = {}
    planned_options = []
    for code, detail in planned_details.items():
        bundles, metadata = _build_course_bundles(detail)
        planned_bundle_map[code] = {"bundles": bundles, "metadata": metadata}
        planned_options.append((code, bundles))

    compatible_bundles = []
    rejected_bundles = []

    for bundle in candidate_bundles:
        rejection_reasons: list[str] = []
        if _bundle_violates_earliest_start(bundle, earliest_start):
            rejection_reasons.append(
                f"contains a meeting before preferred earliest time {_format_time(earliest_start)}"
            )

        compatible_plan = None
        if not rejection_reasons:
            compatible_plan = _find_compatible_plan(bundle, planned_options)
            if compatible_plan is None and planned_options:
                rejection_reasons.append(
                    "conflicts with all feasible section-bundle combinations of the planned courses"
                )

        if rejection_reasons:
            rejected_bundles.append({
                "bundle": _bundle_summary(bundle),
                "reasons": rejection_reasons,
            })
            continue

        compatible_bundles.append({
            "candidate_bundle": _bundle_summary(bundle),
            "compatible_plan": [
                {
                    "course_code": item["course_code"],
                    "bundle": _bundle_summary(item["bundle"]),
                }
                for item in (compatible_plan or [])
            ],
        })

    return {
        "course_code": normalized,
        "planned_courses": planned,
        "earliest_start": earliest_start,
        "fits_schedule": len(compatible_bundles) > 0,
        "compatible_bundles": compatible_bundles,
        "rejected_bundles": rejected_bundles,
        "checked_bundle_count": len(candidate_bundles),
        "candidate_bundle_metadata": candidate_meta,
        "planned_bundle_metadata": {
            code: {
                "bundle_count": info["metadata"]["bundle_count"],
                "required_activity_types": info["metadata"]["required_activity_types"],
                "primary_activity_types": info["metadata"]["primary_activity_types"],
            }
            for code, info in planned_bundle_map.items()
        },
        "assumption_note": (
            "This check treats lectures/seminars as the primary section choice and "
            "pairs them with one open section from each secondary activity group "
            "present for the course, such as recitation or lab."
        ),
    }
