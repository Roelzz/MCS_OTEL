import reflex as rx

from web.components import (
    connection_view,
    evaluate_panel,
    load_mapping_panel,
    mapping_editor,
    save_panel,
    sidebar,
)
from web.components.improve_dashboard import improve_dashboard
from web.state import State  # noqa: F401 — must import so Reflex registers state

_BODY_FONT = "Outfit, sans-serif"


def _main_content() -> rx.Component:
    return rx.box(
        rx.match(
            State.current_step,
            ("load", load_mapping_panel()),
            ("connections", connection_view()),
            ("rules", mapping_editor()),
            ("improve", improve_dashboard()),
            ("evaluate", evaluate_panel()),
            ("save", save_panel()),
            load_mapping_panel(),
        ),
        width="100%",
        max_width="1200px",
        margin_x="auto",
        padding="1em",
        flex="1",
    )


def index_page() -> rx.Component:
    return rx.hstack(
        sidebar(),
        _main_content(),
        width="100%",
        min_height="100vh",
        spacing="0",
        align="start",
    )


app = rx.App(
    theme=rx.theme(
        appearance="inherit",
        accent_color="green",
        radius="medium",
        scaling="100%",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@300;400;500;600&display=swap",
    ],
    style={"font_family": _BODY_FONT},
)

app.add_page(index_page, route="/", on_load=State.scan_mappings)
