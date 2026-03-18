"""Upload & Preview sub-step — upload transcript and see generation results."""

import reflex as rx

from web.components.upload import upload_panel
from web.state import State


def evaluate_upload_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Upload & Preview", size="4"),
        rx.text(
            "Upload a transcript to evaluate your mapping. Preview generates automatically.",
            size="2",
            color="var(--gray-9)",
        ),
        upload_panel(),
        rx.cond(
            State.has_preview,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("check-circle", size=16, color="var(--green-9)"),
                        rx.text("Preview Generated", weight="bold", size="3"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.badge(
                            State.preview_total_spans.to(str),
                            " spans",
                            color_scheme="green",
                            size="2",
                        ),
                        rx.badge(
                            State.preview_total_events.to(str),
                            " events",
                            color_scheme="blue",
                            size="2",
                        ),
                        rx.badge(
                            State.entities.length().to(str),
                            " entities",
                            color_scheme="purple",
                            size="2",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.text(
                        "Use the sub-menu on the left to explore Span Tree, Session Dashboard, Entities, and more.",
                        size="2",
                        color="var(--gray-9)",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
            rx.cond(
                State.has_transcript,
                rx.cond(
                    State.has_mapping,
                    rx.callout(
                        "Generating preview...",
                        icon="loader",
                        color_scheme="blue",
                        size="1",
                    ),
                    rx.callout(
                        "Load a mapping first (step 1) to generate a preview.",
                        icon="info",
                        color_scheme="orange",
                        size="1",
                    ),
                ),
            ),
        ),
        rx.cond(
            State.has_preview,
            rx.button(
                rx.icon("refresh-cw", size=14),
                "Regenerate Preview",
                on_click=State.refresh_preview,
                size="2",
                variant="outline",
                disabled=State.preview_loading,
            ),
        ),
        spacing="4",
        width="100%",
    )
