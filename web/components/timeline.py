import reflex as rx

from web.state import State


def _time_axis() -> rx.Component:
    """Time axis labels at top of timeline."""
    return rx.hstack(
        rx.text("0ms", size="1", color="var(--gray-8)", font_family="JetBrains Mono"),
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
        width="100%",
        padding_x="4px",
        padding_bottom="4px",
        border_bottom="1px solid var(--gray-a4)",
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

    # Calculate left% and width% (min 0.5% width for visibility)
    left_pct = (offset_ms / max_ms * 100).to(str) + "%"
    width_pct = rx.cond(
        dur_ms / max_ms * 100 < 0.5,
        "0.5%",
        (dur_ms / max_ms * 100).to(str) + "%",
    )

    return rx.box(
        rx.hstack(
            # Depth indentation label
            rx.text(
                name,
                size="1",
                color="var(--gray-11)",
                weight="medium",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
                max_width="180px",
                min_width="180px",
                padding_left=(depth * 12).to(str) + "px",
            ),
            # Bar container (relative)
            rx.box(
                rx.box(
                    rx.text(
                        dur_display,
                        size="1",
                        color="white",
                        padding_x="4px",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    position="absolute",
                    left=left_pct,
                    width=width_pct,
                    height="100%",
                    background=color,
                    border_radius="3px",
                    display="flex",
                    align_items="center",
                    min_width="4px",
                ),
                position="relative",
                height="22px",
                flex="1",
            ),
            spacing="2",
            width="100%",
            align="center",
        ),
        cursor="pointer",
        on_click=State.select_span(span_id),
        padding_y="2px",
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
