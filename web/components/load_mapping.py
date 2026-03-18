"""Load Mapping step — landing screen with 4 ways to load a mapping."""

import reflex as rx

from web.state import State


def _mapping_card(mapping: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("file-json", size=16, color="var(--green-9)"),
                rx.text(mapping["name"], weight="bold", size="2"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.cond(
                    mapping["version"] != "",
                    rx.badge(mapping["version"], size="1", variant="outline"),
                ),
                rx.badge(
                    mapping["rule_count"].to(str),
                    " rules",
                    size="1",
                    color_scheme="green",
                ),
                spacing="2",
            ),
            spacing="2",
        ),
        cursor="pointer",
        _hover={"border_color": "var(--green-8)"},
        on_click=State.load_library_mapping(mapping["name"]),
    )


def _import_file_section() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("upload", size=16, color="var(--blue-9)"),
                rx.text("Import from file", weight="medium", size="2"),
                spacing="2",
                align="center",
            ),
            rx.upload(
                rx.vstack(
                    rx.text("Drop .json file here or click to browse", size="2", color="var(--gray-9)"),
                    align="center",
                    padding="2em",
                ),
                id="mapping_upload",
                accept={".json": ["application/json"]},
                max_files=1,
                border="1px dashed var(--gray-7)",
                border_radius="var(--radius-2)",
                width="100%",
            ),
            rx.button(
                "Upload",
                on_click=State.handle_mapping_file_upload(rx.upload_files(upload_id="mapping_upload")),
                size="2",
                variant="outline",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def _paste_section() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("clipboard-paste", size=16, color="var(--purple-9)"),
                rx.text("Paste JSON", weight="medium", size="2"),
                spacing="2",
                align="center",
            ),
            rx.text_area(
                value=State.import_json_text,
                on_change=State.set_import_json_text,
                placeholder='{"version": "1.0", "name": "...", "rules": [...]}',
                rows="6",
                width="100%",
            ),
            rx.button(
                "Load",
                on_click=State.import_mapping(State.import_json_text),
                size="2",
                variant="outline",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def load_mapping_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Load Mapping", size="4"),
        rx.text(
            "Choose a mapping to start editing, or create a new one.",
            size="2",
            color="var(--gray-9)",
        ),
        # Library grid
        rx.cond(
            State.available_mappings.length() > 0,
            rx.vstack(
                rx.text("Mapping Library", weight="medium", size="2"),
                rx.flex(
                    rx.foreach(State.available_mappings, _mapping_card),
                    wrap="wrap",
                    spacing="3",
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
            rx.callout(
                "No mappings found in library. Import one or start blank.",
                icon="info",
                size="1",
            ),
        ),
        rx.separator(),
        rx.grid(
            _import_file_section(),
            _paste_section(),
            columns="2",
            spacing="3",
            width="100%",
        ),
        rx.separator(),
        rx.button(
            rx.icon("plus", size=14),
            "Start Blank",
            on_click=State.load_blank_mapping,
            size="2",
            variant="outline",
        ),
        spacing="4",
        width="100%",
    )
