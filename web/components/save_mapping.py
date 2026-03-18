"""Save step — save mapping to library or download."""

import reflex as rx

from web.state import State


def save_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Save Mapping", size="4"),
        rx.text(
            "Save your mapping to the library or download it.",
            size="2",
            color="var(--gray-9)",
        ),
        # Save to library
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("library", size=16, color="var(--green-9)"),
                    rx.text("Save to Library", weight="medium", size="3"),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="Mapping name",
                        value=State.save_as_name,
                        on_change=State.set_save_as_name,
                        width="100%",
                    ),
                    rx.button(
                        rx.icon("save", size=14),
                        "Save",
                        on_click=State.save_mapping_as,
                        size="2",
                        color_scheme="green",
                        disabled=~State.has_mapping,
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # Download section
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("download", size=16, color="var(--blue-9)"),
                    rx.text("Download", weight="medium", size="3"),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("file-json", size=14),
                        "Mapping Spec",
                        size="2",
                        variant="outline",
                        on_click=State.download_mapping,
                        disabled=~State.has_mapping,
                    ),
                    rx.button(
                        rx.icon("file-output", size=14),
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
        ),
        spacing="4",
        width="100%",
    )
