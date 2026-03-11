import reflex as rx

from web.state import State


def export_panel() -> rx.Component:
    return rx.hstack(
        rx.button(
            rx.icon("download", size=14),
            "Export Mapping Spec",
            size="2",
            variant="outline",
            on_click=State.download_mapping,
        ),
        rx.button(
            rx.icon("download", size=14),
            "Export OTLP JSON",
            size="2",
            variant="outline",
            on_click=State.download_otlp,
        ),
        spacing="2",
        padding="1em",
    )
