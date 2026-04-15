"""
Guardrails: input/output validation and exception handling.
Applied at entry (before Router) and exit (before returning to user).
"""


class Guardrails:
    MAX_INPUT_LENGTH = 2000

    def check_input(self, text: str) -> str:
        if not text or not isinstance(text, str):
            raise ValueError("Input must be a non-empty string.")
        text = text.strip()
        if len(text) > self.MAX_INPUT_LENGTH:
            raise ValueError(f"Input too long (max {self.MAX_INPUT_LENGTH} chars).")
        # TODO: add prompt-injection detection, profanity filter, etc.
        return text

    def check_output(self, text: str) -> str:
        if not text:
            return "Sorry, I couldn't generate a response. Please try rephrasing."
        # TODO: PII scrubbing, hallucination flags, length limits
        return text
