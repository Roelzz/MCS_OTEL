"""Evaluate step — routes to sub-step components based on sidebar selection."""

import reflex as rx

from web.components.conversation_view import conversation_view
from web.components.entity_browser import entity_browser
from web.components.evaluate_upload import evaluate_upload_panel
from web.components.event_registry import event_registry
from web.components.rule_hierarchy import rule_hierarchy
from web.components.session_dashboard import session_dashboard
from web.components.span_tree import span_tree
from web.state import State


def evaluate_panel() -> rx.Component:
    return rx.match(
        State.evaluate_sub_step,
        ("upload", evaluate_upload_panel()),
        ("span_tree", span_tree()),
        ("session", session_dashboard()),
        ("conversation", conversation_view()),
        ("entities", entity_browser()),
        ("rule_graph", rule_hierarchy()),
        ("registry", event_registry()),
        evaluate_upload_panel(),
    )
