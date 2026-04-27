from tools.major_planner import evaluate_course_for_major_plan


def _fake_progress(major: str, classes_taken: list[str]) -> dict:
    return {
        "program": "Computer Science, BSE",
        "unsatisfied_requirements": [
            {
                "section": "Engineering",
                "label": "Introduction to Computer Systems",
                "codes": ["CIS-2400"],
                "alternatives": [],
            },
            {
                "section": "Math and Natural Science",
                "label": "Probability",
                "codes": ["CIS-2610"],
                "alternatives": [{"codes": ["STAT-4300"], "label": "Probability"}],
            },
        ],
    }


def _fake_eligibility(course_code: str, classes_taken: list[str], current_schedule: list[str] | None = None) -> dict:
    return {
        "code": course_code,
        "eligible": course_code != "STAT-4300",
    }


def _fake_schedule_fit(course_code: str, planned_courses: list[str] | None = None, earliest_start=None) -> dict:
    return {
        "course_code": course_code,
        "fits_schedule": course_code != "CIS-2400",
    }


def test_flags_direct_requirement_match():
    result = evaluate_course_for_major_plan(
        "CIS-2400",
        "CIS",
        ["CIS-1100", "CIS-1200"],
        degree_progress_fetcher=_fake_progress,
        eligibility_fetcher=_fake_eligibility,
        schedule_fit_fetcher=_fake_schedule_fit,
    )
    assert result["supports_major_plan"] is True
    assert result["relevant_requirements"][0]["direct_match"] is True


def test_flags_alternative_requirement_match():
    result = evaluate_course_for_major_plan(
        "STAT-4300",
        "CIS",
        ["CIS-1100", "CIS-1200"],
        degree_progress_fetcher=_fake_progress,
        eligibility_fetcher=_fake_eligibility,
        schedule_fit_fetcher=_fake_schedule_fit,
    )
    assert result["supports_major_plan"] is True
    assert result["relevant_requirements"][0]["alternative_match"] is True


def test_recommended_now_requires_all_checks():
    result = evaluate_course_for_major_plan(
        "CIS-2400",
        "CIS",
        ["CIS-1100", "CIS-1200"],
        degree_progress_fetcher=_fake_progress,
        eligibility_fetcher=lambda *args, **kwargs: {"eligible": True},
        schedule_fit_fetcher=lambda *args, **kwargs: {"fits_schedule": True},
    )
    assert result["recommended_now"] is True


def test_not_recommended_when_schedule_fails():
    result = evaluate_course_for_major_plan(
        "CIS-2400",
        "CIS",
        ["CIS-1100", "CIS-1200"],
        degree_progress_fetcher=_fake_progress,
        eligibility_fetcher=_fake_eligibility,
        schedule_fit_fetcher=_fake_schedule_fit,
    )
    assert result["recommended_now"] is False
