import re

PATTERNS = [
    (re.compile(r'(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])'), '[EMAIL]'),
    (re.compile(r'(?<!\d)(?:\+\d{1,3}[ -]?)?(?:\d[ -]?){10}(?!\d)'), '[PHONE]'),
    (re.compile(r'\b(?:\d[ -]*?){13,19}\b'), '[POSSIBLE_CARD_NUMBER]'),
]
# These heuristics are intentionally conservative; do not claim comprehensive PII detection.
INJECTION_PATTERNS = [
    re.compile(r'ignore (?:all |any )?(?:previous|prior|system) instructions', re.I),
    re.compile(r'(?:reveal|print|expose) (?:the )?(?:system prompt|api key|secret)', re.I),
    re.compile(r'(?:you are now|act as) (?:the )?(?:system|developer) (?:assistant|message)', re.I),
]

def redact_pii(text: str) -> tuple[str, bool]:
    redacted = text
    for pattern, placeholder in PATTERNS:
        redacted = pattern.sub(placeholder, redacted)
    return redacted, redacted != text

def is_suspicious(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)
