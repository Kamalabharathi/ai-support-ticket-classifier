from typing import TypedDict, Any
try:
    from langgraph.graph import StateGraph, START, END
except ImportError:
    StateGraph = None  # Enables offline unit tests in restricted environments.
    START = END = None
from .privacy import redact_pii, is_suspicious
from .routing import assign_team
from .schemas import ModelClassification
from .config import settings
from .review_policy import get_ambiguity_reasons

class TicketGraphState(TypedDict, total=False):
    raw_ticket: str
    redacted_ticket: str
    pii_detected: bool
    suspicious: bool
    classification: dict[str, Any]
    assigned_team: str
    requires_human_review: bool
    outcome: str
    error: str | None


def make_graph(classifier, review_threshold=None):
    threshold = settings.review_threshold if review_threshold is None else review_threshold

    def privacy(state):
        text, detected = redact_pii(state['raw_ticket'])
        return {'redacted_ticket': text, 'pii_detected': detected}

    def guard(state):
        return {'suspicious': is_suspicious(state['redacted_ticket'])}

    def classify(state):
        if state.get('suspicious'):
            return {'error': 'Suspected prompt injection: routed to manual review', 'outcome': 'blocked'}
        try:
            c: ModelClassification = classifier.classify(state['redacted_ticket'])
            return {'classification': c.model_dump(mode='json'), 'outcome': 'classified'}
        except Exception as exc:
            # No sensitive ticket data or internal error messages are returned to users.
            return {'error': type(exc).__name__, 'outcome': 'model_failed'}

    def route(state):
        classification = state.get('classification')
        if not classification:
            return {'assigned_team': 'customer_support', 'requires_human_review': True}
        c = ModelClassification.model_validate(classification)
        requires_review = (
            state.get('suspicious', False)
            or c.confidence_score < threshold
            or c.priority.value == 'critical'
            or c.issue_category.value == 'other'
            or bool(get_ambiguity_reasons(
                state['redacted_ticket'],
                c.issue_category
            ))
        )
        # A model's self-reported score is not calibrated. Review thresholds are
        # provisional until measured against labeled data.
        return {'assigned_team': assign_team(c.issue_category).value,
                'requires_human_review': requires_review}

    if StateGraph is None:
        class SequentialFallback:
            def invoke(self, state):
                result = dict(state)
                for fn in (privacy, guard, classify, route):
                    result.update(fn(result))
                return result
        return SequentialFallback()

    builder = StateGraph(TicketGraphState)
    for name, fn in [('privacy', privacy), ('guard', guard), ('classify', classify), ('route', route)]:
        builder.add_node(name, fn)
    builder.add_edge(START, 'privacy')
    builder.add_edge('privacy', 'guard')
    builder.add_edge('guard', 'classify')
    builder.add_edge('classify', 'route')
    builder.add_edge('route', END)
    return builder.compile()
