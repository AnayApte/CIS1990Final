"""
Guardrails: input/output validation and exception handling.
Applied at entry (before Router) and exit (before returning to user).
"""

_INJECTION_PHRASES = [
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "disregard",
    "forget previous",
    "you are now",
    "new instructions",
    "jailbreak",
    "bypass",
    "override instructions",
]

_ADVISORY_TRIGGERS = [
    "requirement",
    "degree",
    "major",
    "credit",
    "graduate",
    "recommend",
    "suggest",
    "should take",
    "prerequisite",
    "elective",
    "core",
    "satisfy",
]

_ADVISORY_NOTE = (
    "\n\n---\n*Note: This tool is advisory only. "
    "Please verify your degree requirements through Path@Penn "
    "and your academic advisor.*"
)

MAX_OUTPUT_LENGTH = 4000


class Guardrails:
    MAX_INPUT_LENGTH = 2000

    def check_input(self, text: str) -> str:
        if not text or not isinstance(text, str):
            raise ValueError("Input must be a non-empty string.")
        text = text.strip()
        if len(text) > self.MAX_INPUT_LENGTH:
            raise ValueError(f"Input too long (max {self.MAX_INPUT_LENGTH} chars).")
        lower = text.lower()
        for phrase in _INJECTION_PHRASES:
            if phrase in lower:
                raise ValueError("Input contains disallowed content.")
        return text

    def check_output(self, text: str) -> str:
        if not text:
            return "Sorry, I couldn't generate a response. Please try rephrasing."
        if len(text) > MAX_OUTPUT_LENGTH:
            text = text[:MAX_OUTPUT_LENGTH] + "…\n\n*(Response truncated)*"
        lower = text.lower()
        if any(trigger in lower for trigger in _ADVISORY_TRIGGERS):
            text += _ADVISORY_NOTE
        return text
