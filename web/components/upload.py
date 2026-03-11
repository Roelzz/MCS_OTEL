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
            value=State.raw_content,
            on_change=State.set_raw_content,
            width="100%",
            min_height="120px",
            font_family="JetBrains Mono, monospace",
            font_size="12px",
        ),
        rx.button(
            "Parse Transcript",
            on_click=State.handle_paste(State.raw_content),
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
            rx.callout(
                rx.hstack(
                    rx.text("Parsed "),
                    rx.text(State.entities.length(), weight="bold"),
                    rx.text(" entities"),
                ),
                icon="check",
                color_scheme="green",
            ),
            rx.fragment(),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
