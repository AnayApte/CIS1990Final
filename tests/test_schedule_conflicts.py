from tools.schedule_conflicts import check_schedule_fit


def _make_section(section_id: str, day: str, start: float, end: float, activity: str = "LEC") -> dict:
    return {
        "section_id": section_id,
        "activity": activity,
        "status": "open",
        "meetings": [{"day": day, "start": start, "end": end, "room": "TEST"}],
        "instructors": [],
    }


def _fake_detail_fetcher(course_code: str, semester: str = "current") -> dict:
    data = {
        "CIS-1000": {
            "code": "CIS-1000",
            "sections": [
                _make_section("CIS-1000-001", "M", 10.00, 11.00),
                _make_section("CIS-1000-002", "M", 8.30, 9.30),
            ],
        },
        "CIS-1500": {
            "code": "CIS-1500",
            "sections": [
                _make_section("CIS-1500-001", "M", 10.00, 11.00),
                _make_section("CIS-1500-201", "W", 12.00, 13.00, activity="REC"),
                _make_section("CIS-1500-202", "W", 8.30, 9.30, activity="REC"),
            ],
        },
        "MATH-2000": {
            "code": "MATH-2000",
            "sections": [
                _make_section("MATH-2000-001", "M", 9.00, 10.00),
                _make_section("MATH-2000-002", "M", 11.00, 12.00),
            ],
        },
        "STAT-3000": {
            "code": "STAT-3000",
            "sections": [
                _make_section("STAT-3000-001", "M", 12.00, 13.00),
            ],
        },
        "PHYS-4000": {
            "code": "PHYS-4000",
            "sections": [
                _make_section("PHYS-4000-001", "M", 10.00, 11.00),
            ],
        },
        "ESE-4000": {
            "code": "ESE-4000",
            "sections": [
                _make_section("ESE-4000-001", "M", 10.30, 11.30),
                _make_section("ESE-4000-002", "M", 11.30, 12.30),
            ],
        },
        "PHYS-5000": {
            "code": "PHYS-5000",
            "sections": [
                _make_section("PHYS-5000-001", "T", 10.00, 11.00),
                _make_section("PHYS-5000-151", "W", 12.00, 13.00, activity="LAB"),
                _make_section("PHYS-5000-152", "W", 14.00, 15.00, activity="LAB"),
            ],
        },
    }
    return data[course_code]


def test_finds_compatible_section_with_planned_courses():
    result = check_schedule_fit(
        "CIS-1000",
        planned_courses=["MATH-2000", "STAT-3000"],
        detail_fetcher=_fake_detail_fetcher,
    )
    assert result["fits_schedule"] is True
    assert any(
        item["candidate_bundle"][0]["section_id"] == "CIS-1000-001"
        for item in result["compatible_bundles"]
    )


def test_respects_earliest_start_preference():
    result = check_schedule_fit(
        "CIS-1500",
        earliest_start=9.00,
        detail_fetcher=_fake_detail_fetcher,
    )
    assert result["fits_schedule"] is True
    rejected_ids = {
        section["section_id"]
        for item in result["rejected_bundles"]
        for section in item["bundle"]
    }
    assert "CIS-1500-202" in rejected_ids


def test_reports_no_fit_when_all_sections_conflict():
    result = check_schedule_fit(
        "ESE-4000",
        planned_courses=["MATH-2000", "STAT-3000", "PHYS-4000"],
        detail_fetcher=_fake_detail_fetcher,
    )
    assert result["fits_schedule"] is False


def test_requires_recitation_bundle_for_course():
    result = check_schedule_fit(
        "CIS-1500",
        detail_fetcher=_fake_detail_fetcher,
    )
    assert result["fits_schedule"] is True
    assert result["candidate_bundle_metadata"]["required_activity_types"] == ["REC"]
    assert all(len(item["candidate_bundle"]) == 2 for item in result["compatible_bundles"])


def test_requires_lab_bundle_for_course():
    result = check_schedule_fit(
        "PHYS-5000",
        detail_fetcher=_fake_detail_fetcher,
    )
    assert result["fits_schedule"] is True
    assert result["candidate_bundle_metadata"]["required_activity_types"] == ["LAB"]
    assert all(len(item["candidate_bundle"]) == 2 for item in result["compatible_bundles"])
