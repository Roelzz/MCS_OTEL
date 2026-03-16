import reflex as rx

from web.state import State


def _time_axis() -> rx.Component:
    """Time axis labels at top of timeline."""
    return rx.hstack(
        rx.text("", min_width="200px"),
        rx.hstack(
            rx.text("0", size="1", color="var(--gray-8)", font_family="JetBrains Mono"),
            rx.spacer(),
            rx.text("25%", size="1", color="var(--gray-8)", font_family="JetBrains Mono"),
            rx.spacer(),
            rx.text("50%", size="1", color="var(--gray-8)", font_family="JetBrains Mono"),
            rx.spacer(),
            rx.text("75%", size="1", color="var(--gray-8)", font_family="JetBrains Mono"),
            rx.spacer(),
            rx.text(
                State.timeline_max_ms.to(int).to(str) + "ms",
                size="1",
                color="var(--gray-8)",
                font_family="JetBrains Mono",
            ),
            flex="1",
        ),
        width="100%",
        padding_x="4px",
        padding_bottom="4px",
        border_bottom="1px solid var(--gray-a4)",
        spacing="2",
    )


def _timeline_bar(span: rx.Var[dict]) -> rx.Component:
    name = span["name"].to(str)
    span_id = span["span_id"].to(str)
    offset_ms = span["start_offset_ms"].to(float)
    dur_ms = span["duration_ms"].to(float)
    depth = span["depth"].to(int)
    color = span["color"].to(str)
    dur_display = span["duration_display"].to(str)
    max_ms = State.timeline_max_ms

    # Margin-left positions the bar start, width shows duration
    # Use calc() with max() to ensure minimum visible bar width
    margin_left_pct = (offset_ms / max_ms * 100).to(str) + "%"
    width_pct = (dur_ms / max_ms * 100).to(str) + "%"

    return rx.box(
        rx.hstack(
            # Span name label with depth indentation
            rx.text(
                name,
                size="1",
                color="var(--gray-11)",
                weight="medium",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
                min_width="200px",
                max_width="200px",
                padding_left=(depth * 16).to(str) + "px",
            ),
            # Bar track
            rx.box(
                # The colored bar
                rx.box(
                    background=color,
                    border_radius="3px",
                    height="18px",
                    min_width="6px",
                    width="100%",
                ),
                # Duration label positioned after the bar
                rx.text(
                    dur_display,
                    size="1",
                    color="var(--gray-9)",
                    white_space="nowrap",
                    padding_left="4px",
                    font_family="JetBrains Mono",
                ),
                display="flex",
                align_items="center",
                margin_left=margin_left_pct,
                width=rx.cond(
                    dur_ms / max_ms * 100 < 1.5,
                    "1.5%",
                    width_pct,
                ),
                flex_shrink="0",
            ),
            flex="1",
            overflow="hidden",
            spacing="2",
            align="center",
        ),
        cursor="pointer",
        on_click=State.select_span(span_id),
        padding_y="1px",
        padding_x="4px",
        border_radius="var(--radius-1)",
        background=rx.cond(
            State.selected_span_id == span_id,
            "var(--green-a3)",
            "transparent",
        ),
        _hover={"background": "var(--gray-a3)"},
    )


def timeline_view() -> rx.Component:
    return rx.vstack(
        _time_axis(),
        rx.cond(
            State.timeline_data.length() > 0,  # type: ignore
            rx.box(
                rx.vstack(
                    rx.foreach(State.timeline_data, _timeline_bar),
                    spacing="0",
                    width="100%",
                ),
                width="100%",
                max_height="600px",
                overflow_y="auto",
            ),
            rx.text(
                "No span data. Refresh the preview first.",
                size="2",
                color="var(--gray-9)",
            ),
        ),
        spacing="2",
        width="100%",
    )
