"""Evaluate step — upload transcript, preview, and inspect all analysis views."""

import reflex as rx

from web.components.conversation_view import conversation_view
from web.components.entity_browser import entity_browser
from web.components.event_registry import event_registry
from web.components.rule_hierarchy import rule_hierarchy
from web.components.session_dashboard import session_dashboard
from web.components.span_tree import span_tree
from web.components.upload import upload_panel
from web.state import State


def evaluate_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Evaluate Mapping", size="4"),
        rx.text(
            "Upload a transcript, generate a preview, then inspect the results.",
            size="2",
            color="var(--gray-9)",
        ),
        upload_panel(),
        rx.cond(
            State.has_transcript,
            rx.vstack(
                rx.button(
                    rx.cond(
                        State.preview_loading,
                        rx.hstack(rx.spinner(size="1"), rx.text("Generating...")),
                        rx.hstack(rx.icon("play", size=14), rx.text("Generate Preview")),
                    ),
                    on_click=State.refresh_preview,
                    disabled=State.preview_loading,
                    color_scheme="green",
                    size="2",
                ),
                rx.cond(
                    State.preview_total_spans > 0,
                    rx.accordion.root(
                        rx.accordion.item(
                            header="Span Tree",
                            content=span_tree(),
                            value="span_tree",
                        ),
                        rx.accordion.item(
                            header="Session Dashboard",
                            content=session_dashboard(),
                            value="session",
                        ),
                        rx.accordion.item(
                            header="Conversation",
                            content=conversation_view(),
                            value="conversation",
                        ),
                        rx.accordion.item(
                            header="Entities",
                            content=entity_browser(),
                            value="entities",
                        ),
                        rx.accordion.item(
                            header="Rule Graph",
                            content=rule_hierarchy(),
                            value="rule_graph",
                        ),
                        rx.accordion.item(
                            header="Event Registry",
                            content=event_registry(),
                            value="registry",
                        ),
                        type="multiple",
                        width="100%",
                        variant="surface",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
        ),
        spacing="4",
        width="100%",
    )
