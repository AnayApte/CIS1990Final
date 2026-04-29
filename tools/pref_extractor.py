"""
Pref. Extractor Tool.

Extracts structured preferences from a user's natural language input using
an OpenAI function-calling call. Returns only the fields the user mentioned —
null/unmentioned fields are stripped so callers can safely merge with existing
preferences without overwriting anything the user didn't touch.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

_SCHEMA = {
    "name": "extract_preferences",
    "description": "Extract scheduling preferences from natural language. Set a field to null if the user did not mention it.",
    "parameters": {
        "type": "object",
        "properties": {
            "max_difficulty": {
                "type": "number",
                "description": (
                    "Maximum acceptable Penn Course Review difficulty rating (1–4 scale). "
                    "'easy semester' or 'light workload' → 2.0; 'not too hard' → 2.5."
                ),
            },
            "earliest_start": {
                "type": "string",
                "description": (
                    "Earliest acceptable class start time as HH:MM (24-hour). "
                    "'no 8am' → '09:00'; 'nothing before 10' → '10:00'; "
                    "'no morning classes' or 'nothing before noon' → '12:00'."
                ),
            },
            "latest_end": {
                "type": "string",
                "description": (
                    "Latest acceptable class end time as HH:MM (24-hour). "
                    "'done by 5' → '17:00'; 'no evening classes' → '18:00'."
                ),
            },
            "no_friday_classes": {
                "type": "boolean",
                "description": "True when the user wants no classes on Fridays.",
            },
            "max_credits": {
                "type": "number",
                "description": "Maximum credit units the student wants this semester.",
            },
            "preferred_departments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Department codes the student prefers, e.g. ['CIS', 'MATH'].",
            },
        },
        # All keys required so the model always emits the full object;
        # null values are stripped by extract() before returning.
        "required": [
            "max_difficulty",
            "earliest_start",
            "latest_end",
            "no_friday_classes",
            "max_credits",
            "preferred_departments",
        ],
    },
}

_SYSTEM = (
    "You extract scheduling preferences from a student's natural language message. "
    "Only populate a field if the student clearly stated that preference. "
    "Leave everything else as JSON null — do not guess or infer unstated preferences."
)


class PrefExtractorTool:
    def __init__(self, client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client = client

    def extract(self, user_text: str) -> dict:
        """
        Extract scheduling preferences from free-form text.

        Returns a dict containing only the fields the user mentioned.
        Fields not mentioned are absent from the returned dict, so callers
        can safely merge with existing preferences (no silent overwrites).
        """
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_text},
            ],
            tools=[{"type": "function", "function": _SCHEMA}],
            tool_choice={"type": "function", "function": {"name": "extract_preferences"}},
        )
        raw = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )
        # Strip null / empty-list values — absence means "not mentioned"
        return {
            k: v
            for k, v in raw.items()
            if v is not None and v != []
        }
