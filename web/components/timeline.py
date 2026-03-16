import reflex as rx

from web.state import State


def _timeline_bar(span: rx.Var[dict]) -> rx.Component:
    name = span["name"].to(str)
    span_id = span["span_id"].to(str)
    dur_ms = span["duration_ms"].to(float)
    depth = span["depth"].to(int)
    color = span["color"].to(str)
    dur_display = span["duration_display"].to(str)
    max_ms = State.timeline_max_ms

    # Bar width proportional to root duration, minimum 3% for visibility
    raw_pct = dur_ms / max_ms * 100
    width_pct = rx.cond(
        raw_pct < 3,
        "3%",
        raw_pct.to(str) + "%",
    )

    return rx.hstack(
        # Span name with depth indentation
        rx.text(
            name,
            size="1",
            color="var(--gray-11)",
            weight="medium",
            white_space="nowrap",
            overflow="hidden",
            text_overflow="ellipsis",
            min_width="220px",
            max_width="220px",
            padding_left=(depth * 16).to(str) + "px",
        ),
        # Bar + duration label
        rx.hstack(
            rx.box(
                width=width_pct,
                min_width="8px",
                height="16px",
                background=color,
                border_radius="3px",
                flex_shrink="0",
            ),
            rx.text(
                dur_display,
                size="1",
                color="var(--gray-9)",
                white_space="nowrap",
                font_family="JetBrains Mono",
            ),
            spacing="2",
            align="center",
            flex="1",
            overflow="hidden",
        ),
        spacing="2",
        width="100%",
        align="center",
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
        # Legend row
        rx.hstack(
            rx.text("", min_width="220px"),
            rx.text(
                "Bar width = span duration relative to total trace (",
                rx.text(
                    State.timeline_max_ms.to(int).to(str) + "ms",
                    as_="span",
                    weight="bold",
                ),
                ")",
                size="1",
                color="var(--gray-8)",
            ),
            spacing="2",
            width="100%",
            padding_x="4px",
            padding_bottom="4px",
            border_bottom="1px solid var(--gray-a4)",
        ),
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
