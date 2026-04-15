"""
Pref. Extractor Tool ("Pref. Extractor Guy" on whiteboard).

Extracts structured preferences from a user's natural language input.
Updates Memory with the extracted preferences so the Router can use them.

Examples of extractable preferences:
  - "no 8am classes" → {"avoid_early_morning": true}
  - "I want to take at least one CIS elective" → {"required_depts": ["CIS"]}
  - "light workload this semester" → {"max_difficulty": "low"}
"""


class PrefExtractorTool:
    def extract(self, user_text: str) -> dict:
        """
        TODO: Use LLM to extract structured preferences from free-form text.
        Returns a preferences dict to be merged into MemoryStore.preferences.
        """
        raise NotImplementedError(
            "Implement LLM-based preference extraction here.\n"
            "Prompt the model to return JSON with keys like: "
            "avoid_times, preferred_depts, max_credits, difficulty_pref, etc."
        )
