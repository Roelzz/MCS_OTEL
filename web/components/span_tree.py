import reflex as rx

from web.components.timeline import timeline_gantt
from web.state import State


def _span_row(span: rx.Var[dict]) -> rx.Component:
    """Single span or event row in the tree."""
    depth = span["depth"].to(int)
    name = span["name"].to(str)
    child_count = span["child_count"].to(int)
    span_id = span["span_id"].to(str)
    is_event = span["is_event"].to(bool)
    status = span["status"].to(str)
    dur_display = span["duration_display"].to(str)
    row_index = span["index"].to(int)

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
        # Duration
        rx.cond(
            is_event,
            rx.text(
                "event",
                size="1",
                color="var(--orange-9)",
                font_family="JetBrains Mono, monospace",
            ),
            rx.text(
                dur_display,
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
        border_left=rx.cond(
            status == "ERROR",
            "3px solid var(--red-9)",
            rx.cond(status == "OK", "3px solid var(--green-a5)", "3px solid transparent"),
        ),
        background=rx.cond(
            State.selected_span_id == span_id,
            "var(--green-a3)",
            rx.cond(row_index % 2 == 0, "var(--gray-a2)", "transparent"),
        ),
        _hover={"background": "var(--gray-a3)"},
    )


def _attr_row(attr: rx.Var[dict]) -> rx.Component:
    """Single attribute key-value row."""
    key = attr["key"].to(str)
    value = attr["value"].to(str)
    return rx.hstack(
        rx.text(
            key,
            size="1",
            weight="medium",
            font_family="JetBrains Mono, monospace",
            color="var(--blue-11)",
            min_width="200px",
        ),
        rx.cond(
            value != "",
            rx.text(
                value,
                size="1",
                font_family="JetBrains Mono, monospace",
                flex="1",
                style={"word_break": "break_all"},
            ),
            rx.text(
                "(empty)",
                size="1",
                color="var(--gray-8)",
                font_style="italic",
            ),
        ),
        spacing="2",
        width="100%",
        padding_y="2px",
        padding_x="0.5em",
        border_bottom="1px solid var(--gray-a3)",
    )


def _span_detail() -> rx.Component:
    """Detail panel for the selected span."""
    detail = State.selected_span_detail
    return rx.cond(
        State.selected_span_id != "",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("info", size=16, color="var(--blue-9)"),
                    rx.heading(detail["name"].to(str), size="3"),
                    rx.spacer(),
                    rx.badge(
                        detail["kind"].to(str),
                        color_scheme="blue",
                        size="1",
                    ),
                    rx.badge(
                        detail["status"].to(str),
                        color_scheme=rx.cond(
                            detail["status"].to(str) == "ERROR",
                            "red",
                            rx.cond(detail["status"].to(str) == "OK", "green", "gray"),
                        ),
                        size="1",
                    ),
                    rx.cond(
                        detail["rule_id"].to(str) != "",
                        rx.badge(
                            detail["rule_id"].to(str),
                            color_scheme="purple",
                            size="1",
                            variant="outline",
                        ),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                # IDs with copy buttons
                rx.hstack(
                    rx.text("Span ID: ", size="1", color="var(--gray-9)"),
                    rx.code(detail["span_id"].to(str), size="1"),
                    rx.icon_button(
                        rx.icon("copy", size=12),
                        size="1",
                        variant="ghost",
                        on_click=rx.set_clipboard(detail["span_id"].to(str)),
                    ),
                    spacing="2",
                    align="center",
                ),
                # Timing info
                rx.hstack(
                    rx.badge(
                        detail["duration_display"].to(str),
                        color_scheme="green",
                        size="1",
                    ),
                    rx.cond(
                        detail["event_count"].to(int) > 0,
                        rx.badge(
                            detail["event_count"].to(str),
                            " events",
                            color_scheme="orange",
                            size="1",
                        ),
                    ),
                    spacing="2",
                ),
                # Start/end timestamps
                rx.hstack(
                    rx.text("Start: ", size="1", color="var(--gray-9)"),
                    rx.code(detail["start_time_ns"].to(str), size="1"),
                    rx.text("End: ", size="1", color="var(--gray-9)"),
                    rx.code(detail["end_time_ns"].to(str), size="1"),
                    spacing="2",
                    align="center",
                ),
                # Attributes table
                rx.cond(
                    State.selected_span_attrs.length() > 0,
                    rx.vstack(
                        rx.hstack(
                            rx.text("Attributes", size="2", weight="bold"),
                            rx.badge(
                                State.selected_span_attrs.length().to(str),
                                color_scheme="gray",
                                size="1",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.box(
                            rx.foreach(State.selected_span_attrs, _attr_row),
                            width="100%",
                            border="1px solid var(--gray-a4)",
                            border_radius="var(--radius-2)",
                            max_height="300px",
                            overflow_y="auto",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.text(
                        "No attributes on this span.",
                        size="1",
                        color="var(--gray-8)",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
    )


def _format_duration(ms: rx.Var) -> rx.Component:
    """Format duration for the stats bar."""
    return rx.cond(
        ms >= 1000,
        rx.text((ms / 1000).to(int).to(str) + "." + ((ms % 1000) / 100).to(int).to(str) + "s"),
        rx.text(ms.to(int).to(str) + " ms"),
    )


def span_tree() -> rx.Component:
    """Span tree + timeline panel."""
    total_events = State.preview_total_events
    duration_ms = State.preview_duration_ms

    return rx.vstack(
        rx.hstack(
            rx.heading("Trace Preview", size="4"),
            rx.hstack(
                rx.icon("search", size=14, color="var(--gray-9)"),
                rx.input(
                    placeholder="Filter spans...",
                    value=State.span_filter_text,
                    on_change=State.set_span_filter_text,
                    size="1",
                    width="180px",
                ),
                rx.cond(
                    State.span_filter_text != "",
                    rx.icon_button(
                        rx.icon("x", size=12),
                        size="1",
                        variant="ghost",
                        on_click=State.set_span_filter_text(""),
                    ),
                ),
                spacing="1",
                align="center",
            ),
            rx.cond(
                State.span_filter_text != "",
                rx.badge(
                    State.filtered_preview_spans.length().to(str),
                    " of ",
                    State.total_span_count.to(str),
                    color_scheme="blue",
                    size="1",
                ),
            ),
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
                        rx.icon("hash", size=12),
                        rx.text("Trace: "),
                        rx.text(State.preview_trace_id[:8]),
                        spacing="1",
                    ),
                    color_scheme="gray",
                    variant="surface",
                ),
                rx.badge(
                    rx.hstack(
                        rx.icon("layers", size=12),
                        rx.text(State.preview_total_spans),
                        rx.text(" spans"),
                        spacing="1",
                    ),
                    color_scheme="blue",
                ),
                rx.badge(
                    rx.hstack(
                        rx.icon("zap", size=12),
                        rx.text("Events: "),
                        rx.text(total_events),
                        spacing="1",
                    ),
                    color_scheme="orange",
                ),
                rx.badge(
                    rx.hstack(
                        rx.icon("clock", size=12),
                        _format_duration(duration_ms),
                        spacing="1",
                    ),
                    color_scheme="green",
                ),
                spacing="2",
            ),
            rx.fragment(),
        ),
        # Span tree / timeline tabs
        rx.cond(
            State.preview_loading,
            rx.center(
                rx.spinner(size="3"),
                width="100%",
                padding="2em",
            ),
            rx.cond(
                State.filtered_preview_spans.length() > 0,
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Tree", value="tree"),
                        rx.tabs.trigger("Timeline", value="timeline"),
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.foreach(State.filtered_preview_spans, _span_row),
                            spacing="0",
                            width="100%",
                            border="1px solid var(--gray-a4)",
                            border_radius="var(--radius-2)",
                            padding="0.5em",
                        ),
                        value="tree",
                        padding_top="0.5em",
                    ),
                    rx.tabs.content(
                        timeline_gantt(),
                        value="timeline",
                        padding_top="0.5em",
                    ),
                    default_value="timeline",
                    width="100%",
                ),
                rx.text(
                    "Upload a transcript and refresh to see trace preview.",
                    size="2",
                    color="var(--gray-9)",
                ),
            ),
        ),
        # Span detail panel
        _span_detail(),
        spacing="3",
        width="100%",
        padding="1em",
    )
