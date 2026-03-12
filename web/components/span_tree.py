import reflex as rx

from web.state import State


def _span_row(span: rx.Var[dict]) -> rx.Component:
    """Single span or event row in the tree."""
    depth = span["depth"].to(int)
    name = span["name"].to(str)
    duration = span["duration_ms"].to(float)
    child_count = span["child_count"].to(int)
    span_id = span["span_id"].to(str)
    is_event = span["is_event"].to(bool)

    return rx.hstack(
        # Indentation based on depth
        rx.box(
            width=rx.cond(
                depth > 0,
                (depth * 24).to(str) + "px",
                "0px",
            ),
        ),
        rx.cond(
            depth > 0,
            rx.text(
                rx.cond(is_event, "* ", "+- "),
                size="1",
                color=rx.cond(is_event, "var(--orange-8)", "var(--gray-8)"),
                font_family="monospace",
            ),
            rx.fragment(),
        ),
        # Dot indicator — diamond for events, circle for spans
        rx.cond(
            is_event,
            rx.box(
                width="8px",
                height="8px",
                background="var(--orange-9)",
                flex_shrink="0",
                transform="rotate(45deg)",
            ),
            rx.box(
                width="8px",
                height="8px",
                border_radius="50%",
                background="var(--green-9)",
                flex_shrink="0",
            ),
        ),
        # Name
        rx.text(
            name,
            size="2",
            weight="medium",
            flex="1",
            font_style=rx.cond(is_event, "italic", "normal"),
        ),
        # Child count
        rx.cond(
            child_count > 0,
            rx.badge(
                child_count.to(str),
                variant="surface",
                color_scheme="gray",
                size="1",
            ),
            rx.fragment(),
        ),
        # Duration (only for spans)
        rx.cond(
            is_event,
            rx.text(
                "event",
                size="1",
                color="var(--orange-9)",
                font_family="JetBrains Mono, monospace",
            ),
            rx.text(
                duration.to(str) + " ms",
                size="1",
                color="var(--gray-9)",
                font_family="JetBrains Mono, monospace",
            ),
        ),
        spacing="2",
        width="100%",
        padding_y="0.25em",
        padding_x="0.5em",
        cursor="pointer",
        on_click=State.select_span(span_id),
        border_radius="var(--radius-1)",
        background=rx.cond(
            State.selected_span_id == span_id,
            "var(--green-a3)",
            "transparent",
        ),
        _hover={"background": "var(--gray-a3)"},
    )


def span_tree() -> rx.Component:
    """Span tree + timeline panel."""
    return rx.vstack(
        rx.hstack(
            rx.heading("Trace Preview", size="4"),
            rx.spacer(),
            rx.button(
                "Refresh",
                on_click=State.refresh_preview,
                size="2",
                variant="outline",
            ),
        ),
        # Stats bar
        rx.cond(
            State.preview_spans.length() > 0,
            rx.hstack(
                rx.badge(
                    rx.hstack(
                        rx.text("Spans: "),
                        rx.text(State.preview_total_spans),
                        spacing="1",
                    ),
                    color_scheme="blue",
                ),
                rx.badge(
                    rx.hstack(
                        rx.text("Duration: "),
                        rx.text(State.preview_duration_ms),
                        rx.text(" ms"),
                        spacing="1",
                    ),
                    color_scheme="green",
                ),
                spacing="2",
            ),
            rx.fragment(),
        ),
        # Span tree
        rx.cond(
            State.preview_spans.length() > 0,
            rx.vstack(
                rx.foreach(State.preview_spans, _span_row),
                spacing="0",
                width="100%",
                border="1px solid var(--gray-a4)",
                border_radius="var(--radius-2)",
                padding="0.5em",
            ),
            rx.text(
                "Upload a transcript and refresh to see trace preview.",
                size="2",
                color="var(--gray-9)",
            ),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
