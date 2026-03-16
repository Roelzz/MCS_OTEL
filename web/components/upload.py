import reflex as rx

from web.state import State


def upload_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Upload Transcript", size="4"),
        rx.upload(
            rx.vstack(
                rx.text(
                    "Drop JSON file here or click to browse",
                    color="var(--gray-9)",
                ),
                rx.icon("upload", size=32, color="var(--green-9)"),
                align="center",
                spacing="2",
            ),
            id="transcript_upload",
            accept={".json": ["application/json"]},
            max_files=1,
            border="2px dashed var(--gray-a6)",
            border_radius="var(--radius-3)",
            padding="2em",
            width="100%",
            on_drop=State.handle_upload,
        ),
        rx.text("-- or paste JSON below --", size="2", color="var(--gray-9)"),
        rx.text_area(
            placeholder="Paste transcript JSON here...",
            value=State.paste_content,
            on_change=State.set_paste_content,
            width="100%",
            min_height="120px",
            font_family="JetBrains Mono, monospace",
            font_size="12px",
        ),
        rx.button(
            "Parse Transcript",
            on_click=State.handle_paste(State.paste_content),
            width="100%",
            color_scheme="green",
        ),
        rx.cond(
            State.upload_error,
            rx.callout(
                State.upload_error,
                icon="triangle_alert",
                color_scheme="red",
            ),
            rx.fragment(),
        ),
        rx.cond(
            State.entities.length() > 0,
            rx.vstack(
                rx.callout(
                    rx.hstack(
                        rx.text("Parsed "),
                        rx.text(State.entities.length(), weight="bold"),
                        rx.text(" entities"),
                    ),
                    icon="check",
                    color_scheme="green",
                ),
                rx.upload(
                    rx.vstack(
                        rx.text(
                            "Optional: drop botContent.yml for enrichment",
                            color="var(--gray-9)",
                            size="2",
                        ),
                        rx.icon("file-plus", size=24, color="var(--blue-9)"),
                        align="center",
                        spacing="2",
                    ),
                    id="bot_content_upload",
                    accept={".yml": ["application/x-yaml"], ".yaml": ["application/x-yaml"]},
                    max_files=1,
                    border="2px dashed var(--blue-a6)",
                    border_radius="var(--radius-3)",
                    padding="1em",
                    width="100%",
                    on_drop=State.handle_bot_content_upload,
                ),
                spacing="2",
                width="100%",
            ),
            rx.fragment(),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
