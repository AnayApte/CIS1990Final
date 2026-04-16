"""
CourseSearch — core API wrapper for Penn Course Review.

Real endpoint:  https://penncoursereview.com/api/base/{semester}/
Auth:           None required (public API)
Semester codes: "current" alias, or explicit e.g. "2026C" (fall), "2026A" (spring)

NOTE: The old api.penncoursereview.com/v1 endpoint returns 404 and is no longer
available. All calls go to penncoursereview.com/api/base/.

Key design decisions:
- The /courses/ list endpoint returns all ~5800 courses with no server-side
  department filter, so we filter client-side and cache the full list.
- Review data (course_quality, instructor_quality, difficulty, work_required)
  is embedded in every course and section response — no separate reviews endpoint.
- Per-instructor breakdown is derived from LEC section data in the course detail.
"""

import logging
import requests
from .cache import _course_list_cache, _detail_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://penncoursereview.com/api/base"
DEFAULT_TIMEOUT = 10       # seconds — for single-course lookups
LIST_TIMEOUT = 60          # seconds — /courses/ returns ~5800 items, takes ~38s


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict | list:
    """GET a URL and return parsed JSON. Raises on HTTP error."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request timed out: {url}")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.response.status_code} for {url}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Request failed: {exc}")


def _all_courses(semester: str = "current") -> list[dict]:
    """
    Fetch (or return cached) full course list for a semester.

    The API returns a flat list of ~5800 courses with no pagination.
    Each entry has: id, title, description, semester, num_sections,
    course_quality, instructor_quality, difficulty, work_required, credits.
    """
    cache_key = f"course_list:{semester}"
    cached = _course_list_cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/{semester}/courses/"
    logger.info("Fetching full course list for semester=%s (this may take a moment)", semester)
    data = _get(url, timeout=LIST_TIMEOUT)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response shape from {url}: {type(data)}")
    _course_list_cache.set(cache_key, data)
    return data


def _course_detail(course_code: str, semester: str = "current") -> dict:
    """
    Fetch (or return cached) full course detail including embedded sections.

    Each section has: id, status (O/C), activity (LEC/REC), credits, capacity,
    meetings [{day, start, end, room}], instructors [{id, name}],
    course_quality, instructor_quality, difficulty, work_required.
    """
    cache_key = f"detail:{semester}:{course_code}"
    cached = _detail_cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/{semester}/courses/{course_code}/"
    data = _get(url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response shape from {url}")
    _detail_cache.set(cache_key, data)
    return data


def _format_section(section: dict) -> dict:
    """Convert a raw section dict to the clean shape we expose."""
    meetings = [
        {"day": m["day"], "start": m["start"], "end": m["end"], "room": m.get("room", "")}
        for m in section.get("meetings", [])
    ]
    instructors = [i["name"] for i in section.get("instructors", [])]
    return {
        "section_id": section["id"],
        "activity": section.get("activity", ""),
        "status": "open" if section.get("status") == "O" else "closed",
        "capacity": section.get("capacity"),
        "meetings": meetings,
        "instructors": instructors,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_courses(department: str, semester: str = "current") -> list[dict]:
    """
    Return all courses in a department for the given semester.

    Args:
        department: Department code, e.g. "CIS", "MATH", "PHYS".
        semester:   Semester code ("current", "2026C", "2025A", etc.).

    Returns:
        List of {code, title, credits, semester, num_sections,
                 course_quality, instructor_quality, difficulty, work_required}.
    """
    dept_upper = department.upper()
    all_courses = _all_courses(semester)

    # Filter client-side: course ids are formatted as "CIS-1200", "MATH-1400", etc.
    matches = [c for c in all_courses if c["id"].split("-")[0] == dept_upper]

    # Deduplicate by id (the list occasionally has duplicate entries)
    seen: set[str] = set()
    results = []
    for c in matches:
        if c["id"] not in seen:
            seen.add(c["id"])
            results.append({
                "code": c["id"],
                "title": c["title"],
                "credits": c.get("credits"),
                "semester": c.get("semester"),
                "num_sections": c.get("num_sections"),
                "course_quality": c.get("course_quality"),
                "instructor_quality": c.get("instructor_quality"),
                "difficulty": c.get("difficulty"),
                "work_required": c.get("work_required"),
            })

    results.sort(key=lambda c: c["code"])
    return results


def get_course_details(course_code: str, semester: str = "current") -> dict:
    """
    Return full details for a course, including all sections.

    Args:
        course_code: e.g. "CIS-1200" (dash-separated, case-insensitive).
        semester:    Semester code ("current", "2026C", etc.).

    Returns:
        {code, title, description, credits, prerequisites, semester,
         course_quality, instructor_quality, difficulty, work_required,
         crosslistings, sections: [{section_id, activity, status, capacity,
                                    meetings, instructors}]}
    """
    normalized = course_code.upper().replace(" ", "-")
    detail = _course_detail(normalized, semester)

    sections = [_format_section(s) for s in detail.get("sections", [])]

    return {
        "code": detail["id"],
        "title": detail.get("title", ""),
        "description": detail.get("description", ""),
        "credits": detail.get("credits"),
        "prerequisites": detail.get("prerequisites", ""),
        "semester": detail.get("semester"),
        "course_quality": detail.get("course_quality"),
        "instructor_quality": detail.get("instructor_quality"),
        "difficulty": detail.get("difficulty"),
        "work_required": detail.get("work_required"),
        "crosslistings": detail.get("crosslistings", []),
        "sections": sections,
    }


def get_course_reviews(course_code: str, semester: str = "current") -> dict:
    """
    Return aggregated review data for a course.

    Review ratings (course_quality, instructor_quality, difficulty,
    work_required) are embedded in the API response — there is no separate
    reviews endpoint. The course-level values are cumulative across all
    historical semesters. Section-level ratings let us build a per-instructor
    breakdown from the lecture sections.

    Args:
        course_code: e.g. "CIS-1200".
        semester:    Semester to pull data from ("current" gives cumulative totals).

    Returns:
        {course_code, avg_difficulty, avg_quality, avg_instructor_quality,
         avg_work_required, by_instructor: [{name, avg_quality, avg_difficulty,
                                             avg_instructor_quality, num_sections}]}
    """
    normalized = course_code.upper().replace(" ", "-")
    detail = _course_detail(normalized, semester)

    # Aggregate per-instructor from LEC sections that have review data
    instructor_stats: dict[str, dict] = {}
    for section in detail.get("sections", []):
        if section.get("activity") != "LEC":
            continue
        q = section.get("course_quality")
        iq = section.get("instructor_quality")
        d = section.get("difficulty")
        w = section.get("work_required")
        if q is None and iq is None:
            continue
        for inst in section.get("instructors", []):
            name = inst["name"]
            if name not in instructor_stats:
                instructor_stats[name] = {"quality": [], "instructor_quality": [], "difficulty": [], "work": []}
            if q is not None:
                instructor_stats[name]["quality"].append(q)
            if iq is not None:
                instructor_stats[name]["instructor_quality"].append(iq)
            if d is not None:
                instructor_stats[name]["difficulty"].append(d)
            if w is not None:
                instructor_stats[name]["work"].append(w)

    def _avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else None

    by_instructor = []
    for name, stats in instructor_stats.items():
        by_instructor.append({
            "name": name,
            "avg_quality": _avg(stats["quality"]),
            "avg_instructor_quality": _avg(stats["instructor_quality"]),
            "avg_difficulty": _avg(stats["difficulty"]),
            "avg_work_required": _avg(stats["work"]),
            "num_sections": len(stats["quality"]) or len(stats["instructor_quality"]),
        })
    by_instructor.sort(key=lambda x: x["name"])

    return {
        "course_code": detail["id"],
        "avg_quality": detail.get("course_quality"),
        "avg_instructor_quality": detail.get("instructor_quality"),
        "avg_difficulty": detail.get("difficulty"),
        "avg_work_required": detail.get("work_required"),
        "by_instructor": by_instructor,
    }


def check_course_exists(course_code: str, semester: str = "current") -> bool:
    """
    Return True if the course exists in the given semester, False otherwise.

    Args:
        course_code: e.g. "CIS-1200".
        semester:    Semester code ("current", "2026C", etc.).
    """
    normalized = course_code.upper().replace(" ", "-")
    try:
        _course_detail(normalized, semester)
        return True
    except RuntimeError as exc:
        if "404" in str(exc):
            return False
        # Re-raise unexpected errors (timeouts, 5xx, etc.)
        raise
