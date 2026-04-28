"""
Tests for PrefExtractorTool.

All tests inject a mock OpenAI client — no live API calls are made.
The mock returns a pre-built tool-call response matching what gpt-4o would
produce for each scenario, letting us test the extraction + filtering logic
in isolation.
"""

import json
from unittest.mock import MagicMock

import pytest

from tools.pref_extractor import PrefExtractorTool


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_client(prefs: dict) -> MagicMock:
    """Return a mock OpenAI client whose chat.completions.create() returns prefs."""
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(prefs)

    message = MagicMock()
    message.tool_calls = [tool_call]

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]

    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _all_null(**overrides) -> dict:
    """Full schema with every field null except the supplied overrides."""
    base = {
        "max_difficulty": None,
        "earliest_start": None,
        "latest_end": None,
        "no_friday_classes": None,
        "max_credits": None,
        "preferred_departments": None,
    }
    base.update(overrides)
    return base


# ── Extraction tests ──────────────────────────────────────────────────────────

class TestExtract:
    def test_no_morning_classes_sets_earliest_start(self):
        client = _make_client(_all_null(earliest_start="12:00"))
        result = PrefExtractorTool(client=client).extract("no morning classes")
        assert result.get("earliest_start") == "12:00"

    def test_easy_semester_sets_max_difficulty(self):
        client = _make_client(_all_null(max_difficulty=2.0))
        result = PrefExtractorTool(client=client).extract("I want an easy semester")
        assert "max_difficulty" in result
        assert 2.0 <= result["max_difficulty"] <= 2.5

    def test_no_friday_classes(self):
        client = _make_client(_all_null(no_friday_classes=True))
        result = PrefExtractorTool(client=client).extract("no classes on Friday")
        assert result.get("no_friday_classes") is True

    def test_nothing_before_10_sets_only_earliest_start(self):
        client = _make_client(_all_null(earliest_start="10:00"))
        result = PrefExtractorTool(client=client).extract("nothing before 10")
        assert result.get("earliest_start") == "10:00"
        # Partial input — no other fields should be present
        assert "max_difficulty" not in result
        assert "no_friday_classes" not in result
        assert "max_credits" not in result
        assert "latest_end" not in result
        assert "preferred_departments" not in result

    def test_max_credits_extracted(self):
        client = _make_client(_all_null(max_credits=4.0))
        result = PrefExtractorTool(client=client).extract("I want at most 4 credits this semester")
        assert result.get("max_credits") == 4.0

    def test_preferred_departments_extracted(self):
        client = _make_client(_all_null(preferred_departments=["CIS", "MATH"]))
        result = PrefExtractorTool(client=client).extract("I only want CIS and MATH courses")
        assert result.get("preferred_departments") == ["CIS", "MATH"]

    def test_latest_end_extracted(self):
        client = _make_client(_all_null(latest_end="17:00"))
        result = PrefExtractorTool(client=client).extract("I need to be done by 5pm")
        assert result.get("latest_end") == "17:00"

    def test_multiple_preferences_in_one_statement(self):
        client = _make_client(_all_null(
            earliest_start="10:00",
            no_friday_classes=True,
            max_difficulty=2.5,
        ))
        result = PrefExtractorTool(client=client).extract(
            "nothing before 10, no Fridays, and keep it easy"
        )
        assert result.get("earliest_start") == "10:00"
        assert result.get("no_friday_classes") is True
        assert "max_difficulty" in result
        assert result["max_difficulty"] <= 2.5


# ── Null-stripping tests ──────────────────────────────────────────────────────

class TestNullStripping:
    def test_null_fields_absent_from_result(self):
        client = _make_client(_all_null(earliest_start="09:00"))
        result = PrefExtractorTool(client=client).extract("no 8am classes")
        # Only earliest_start should be present
        assert set(result.keys()) == {"earliest_start"}

    def test_all_null_returns_empty_dict(self):
        client = _make_client(_all_null())
        result = PrefExtractorTool(client=client).extract("I love this university!")
        assert result == {}

    def test_empty_list_stripped(self):
        client = _make_client(_all_null(preferred_departments=[]))
        result = PrefExtractorTool(client=client).extract("any department is fine")
        assert "preferred_departments" not in result


# ── Client passthrough test ───────────────────────────────────────────────────

class TestClientPassthrough:
    def test_extract_calls_openai_once(self):
        client = _make_client(_all_null(max_credits=3.0))
        PrefExtractorTool(client=client).extract("only 3 credits please")
        client.chat.completions.create.assert_called_once()

    def test_tool_choice_forces_extract_preferences(self):
        client = _make_client(_all_null())
        PrefExtractorTool(client=client).extract("sure")
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tool_choice"]["function"]["name"] == "extract_preferences"
