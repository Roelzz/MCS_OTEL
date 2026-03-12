import reflex as rx

from web.components import (
    navbar,
    upload_panel,
    connection_view,
    mapping_editor,
    span_tree,
    export_panel,
    improve_page,
)
from web.state import State  # noqa: F401 — must import so Reflex registers state

_BODY_FONT = "Outfit, sans-serif"


def index_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                upload_panel(),
                rx.separator(),
                connection_view(),
                rx.separator(),
                mapping_editor(),
                rx.separator(),
                span_tree(),
                rx.separator(),
                export_panel(),
                spacing="4",
                width="100%",
                max_width="1200px",
                margin_x="auto",
                padding="1em",
            ),
            width="100%",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
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

app.add_page(index_page, route="/")
app.add_page(improve_page, route="/improve", title="Improve Mapping")
