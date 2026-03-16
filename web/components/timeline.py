import reflex as rx

from web.state import State


def _tick_label(pct: int) -> rx.Component:
    """Single tick mark on the time axis header."""
    return rx.box(
        rx.text(
            f"{pct}%",
            size="1",
            color="var(--gray-8)",
            font_family="JetBrains Mono, monospace",
        ),
        position="absolute",
        left=f"{pct}%",
        transform="translateX(-50%)",
        top="0",
    )


def _time_axis_header() -> rx.Component:
    """Header row with tick marks at 0%, 25%, 50%, 75%, 100%."""
    return rx.box(
        _tick_label(0),
        _tick_label(25),
        _tick_label(50),
        _tick_label(75),
        _tick_label(100),
        position="relative",
        width="100%",
        height="20px",
        border_bottom="1px solid var(--gray-a4)",
    )


def _gantt_row(span: rx.Var[dict], max_ms: rx.Var[float]) -> rx.Component:
    """Single row in the Gantt chart: name label + bar track."""
    depth = span["depth"].to(int)
    name = span["name"].to(str)
    span_id = span["span_id"].to(str)
    is_event = span["is_event"].to(bool)
    is_point = span["is_point_event"].to(bool)
    dur_ms = span["duration_ms"].to(float)
    dur_display = span["duration_display"].to(str)
    offset_ms = span["start_offset_ms"].to(float)
    status = span["status"].to(str)
    row_index = span["index"].to(int)

    # Position as percentage of total trace duration
    left_pct = rx.cond(max_ms > 0, (offset_ms / max_ms) * 100, 0)
    # Width as percentage — minimum 0.5% for visibility, point events get 0 (handled separately)
    width_pct = rx.cond(
        max_ms > 0,
        rx.cond(dur_ms > 0, rx.cond((dur_ms / max_ms) * 100 > 0.5, (dur_ms / max_ms) * 100, 0.5), 0),
        0,
    )

    return rx.hstack(
        # Left column: name with depth indentation
        rx.hstack(
            rx.box(
                width=rx.cond(depth > 0, (depth * 16).to(str) + "px", "0px"),
                flex_shrink="0",
            ),
            rx.cond(
                is_event,
                rx.box(
                    width="6px",
                    height="6px",
                    background="var(--orange-9)",
                    flex_shrink="0",
                    transform="rotate(45deg)",
                ),
                rx.box(
                    width="6px",
                    height="6px",
                    border_radius="50%",
                    background="var(--green-9)",
                    flex_shrink="0",
                ),
            ),
            rx.text(
                name,
                size="1",
                weight="medium",
                overflow="hidden",
                text_overflow="ellipsis",
                white_space="nowrap",
                font_style=rx.cond(is_event, "italic", "normal"),
            ),
            spacing="1",
            align="center",
            width="220px",
            min_width="220px",
            max_width="220px",
            overflow="hidden",
            padding_left="0.5em",
        ),
        # Right column: bar track
        rx.box(
            # Duration bar (for spans with duration)
            rx.cond(
                is_point,
                # Point event: narrow diamond marker
                rx.box(
                    width="6px",
                    height="14px",
                    background=rx.cond(is_event, "var(--orange-9)", "var(--blue-9)"),
                    border_radius="1px",
                    position="absolute",
                    left=left_pct.to(str) + "%",
                    top="50%",
                    transform="translateY(-50%)",
                ),
                # Duration bar: proportional width
                rx.box(
                    rx.text(
                        dur_display,
                        size="1",
                        color="white",
                        font_family="JetBrains Mono, monospace",
                        white_space="nowrap",
                        padding_x="4px",
                    ),
                    background=rx.cond(
                        status == "ERROR",
                        "var(--red-9)",
                        "var(--green-9)",
                    ),
                    border_radius="2px",
                    height="16px",
                    display="flex",
                    align_items="center",
                    position="absolute",
                    left=left_pct.to(str) + "%",
                    width=width_pct.to(str) + "%",
                    min_width="4px",
                    top="50%",
                    transform="translateY(-50%)",
                    overflow="hidden",
                ),
            ),
            # Duration label to the right for point events
            rx.cond(
                is_point,
                rx.text(
                    "—",
                    size="1",
                    color="var(--gray-8)",
                    font_family="JetBrains Mono, monospace",
                    position="absolute",
                    left=(left_pct + 1.5).to(str) + "%",
                    top="50%",
                    transform="translateY(-50%)",
                    white_space="nowrap",
                ),
                rx.fragment(),
            ),
            position="relative",
            flex="1",
            height="24px",
            min_height="24px",
        ),
        spacing="0",
        width="100%",
        cursor="pointer",
        on_click=State.select_span(span_id),
        border_radius="var(--radius-1)",
        background=rx.cond(
            State.selected_span_id == span_id,
            "var(--green-a3)",
            rx.cond(row_index % 2 == 0, "var(--gray-a2)", "transparent"),
        ),
        _hover={"background": "var(--gray-a3)"},
        border_left=rx.cond(
            status == "ERROR",
            "3px solid var(--red-9)",
            rx.cond(status == "OK", "3px solid var(--green-a5)", "3px solid transparent"),
        ),
    )


def timeline_gantt() -> rx.Component:
    """Gantt-style timeline view of the trace."""
    max_ms = State.preview_duration_ms

    return rx.vstack(
        # Column headers
        rx.hstack(
            rx.text(
                "Span",
                size="1",
                weight="bold",
                color="var(--gray-9)",
                width="220px",
                min_width="220px",
                padding_left="0.5em",
            ),
            rx.box(
                _time_axis_header(),
                flex="1",
            ),
            spacing="0",
            width="100%",
        ),
        # Gantt rows
        rx.foreach(
            State.filtered_preview_spans,
            lambda span: _gantt_row(span, max_ms),
        ),
        spacing="0",
        width="100%",
        border="1px solid var(--gray-a4)",
        border_radius="var(--radius-2)",
        padding="0.25em",
        overflow_x="auto",
    )
