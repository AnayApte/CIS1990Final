import pytest
from agent.guardrails import Guardrails

g = Guardrails()

def test_rejects_empty_input():
    with pytest.raises(ValueError):
        g.check_input("")

def test_rejects_too_long_input():
    with pytest.raises(ValueError):
        g.check_input("x" * 3000)

def test_accepts_valid_input():
    assert g.check_input("  Build me a schedule  ") == "Build me a schedule"

def test_output_fallback_on_empty():
    result = g.check_output("")
    assert "Sorry" in result
