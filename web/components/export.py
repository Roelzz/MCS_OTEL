import reflex as rx

from web.state import State


def export_panel() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("package", size=16, color="var(--green-9)"),
                rx.heading("Export", size="3"),
                rx.spacer(),
                rx.cond(
                    State.has_mapping,
                    rx.badge(
                        State.total_rule_count.to(str),
                        " rules",
                        color_scheme="green",
                        size="1",
                    ),
                ),
                rx.cond(
                    State.preview_total_spans > 0,
                    rx.badge(
                        State.preview_total_spans.to(str),
                        " spans",
                        color_scheme="blue",
                        size="1",
                    ),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.hstack(
                rx.button(
                    rx.icon("file_json", size=14),
                    "Mapping Spec",
                    size="2",
                    variant="outline",
                    on_click=State.download_mapping,
                    disabled=~State.has_mapping,
                ),
                rx.button(
                    rx.icon("file_output", size=14),
                    "OTLP Trace JSON",
                    size="2",
                    variant="outline",
                    on_click=State.download_otlp,
                    disabled=State.preview_total_spans == 0,
                ),
                spacing="2",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1em",
    )
