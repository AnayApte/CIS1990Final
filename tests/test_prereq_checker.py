import pytest
from tools.prereq_checker import PrereqCheckerTool

# Uses the stub data/prerequisites.json (empty), so no prereqs required
checker = PrereqCheckerTool()

def test_no_prereqs_always_eligible():
    result = checker.check("CIS-9999", [])
    assert result["eligible"] is True
    assert result["missing_prereqs"] == []
