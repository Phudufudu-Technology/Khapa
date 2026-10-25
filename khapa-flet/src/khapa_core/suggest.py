"""Suggestions: fixed, rule-based text keyed by topic and audience.

``Suggester`` is the seam for the stretch goal (an optional offline language model). Today there
is exactly one implementation, RuleBasedSuggester, and no model runs anywhere in this app. Any
future implementation must keep the AI disclosure visible wherever its output is shown.
"""

from __future__ import annotations

from typing import Protocol

from . import data


class Suggester(Protocol):
    name: str

    def tip(self, audience: str, topic: str) -> str:
        """Return one plain-language suggestion for a topic. `audience`: teacher|parent|learner."""
        ...


class RuleBasedSuggester:
    name = "rules"

    def tip(self, audience: str, topic: str) -> str:
        return data.TIPS.get(topic, {}).get(audience, "")
