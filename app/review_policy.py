
import json
import re
from pathlib import Path

POLICY_FILE = Path(__file__).with_name("review_policy.json")

def get_ambiguity_reasons(ticket_text, predicted_category):
    """Return triggered review rules without changing classification."""
    config = json.loads(POLICY_FILE.read_text(encoding="utf-8"))

    text = ticket_text.lower()
    category = getattr(predicted_category, "value", predicted_category)
    reasons = []

    for rule in config["rules"]:
        if category == rule["expected_category"]:
            continue

        intent = re.search(
            rule["intent_pattern"],
            text,
            flags=re.IGNORECASE
        )

        if not intent:
            continue

        context_pattern = rule.get("context_pattern")

        if context_pattern and not re.search(
            context_pattern,
            text,
            flags=re.IGNORECASE
        ):
            continue

        reasons.append(rule["name"])

    return reasons
