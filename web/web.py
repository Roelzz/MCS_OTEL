import reflex as rx

from web.components import (
    navbar,
    upload_panel,
    connection_view,
    mapping_editor,
    span_tree,
    export_panel,
    entity_browser,
    session_dashboard,
    conversation_view,
    rule_hierarchy,
    event_registry,
    improve_page,
)
from web.components.span_tree import span_detail as _span_detail_import
from web.components.timeline import timeline_view
from web.state import State  # noqa: F401 — must import so Reflex registers state

_BODY_FONT = "Outfit, sans-serif"


def _overview_tab() -> rx.Component:
    """Existing linear flow: Upload → Connection → Rules → Spans → Export."""
    return rx.vstack(
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
    )



def index_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.box(
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Overview", value="overview"),
                    rx.tabs.trigger("Session", value="session"),
                    rx.tabs.trigger("Entities", value="entities"),
                    rx.tabs.trigger("Rule Graph", value="rule_graph"),
                    rx.tabs.trigger("Timeline", value="timeline"),
                    rx.tabs.trigger("Registry", value="registry"),
                    size="2",
                ),
                rx.tabs.content(_overview_tab(), value="overview"),
                rx.tabs.content(
                    rx.vstack(
                        session_dashboard(),
                        rx.separator(),
                        conversation_view(),
                        spacing="4",
                        width="100%",
                    ),
                    value="session",
                ),
                rx.tabs.content(entity_browser(), value="entities"),
                rx.tabs.content(rule_hierarchy(), value="rule_graph"),
                rx.tabs.content(
                    rx.vstack(
                        rx.hstack(
                            rx.heading("Timeline", size="4"),
                            rx.spacer(),
                            rx.button(
                                "Refresh",
                                on_click=State.refresh_preview,
                                size="2",
                                variant="outline",
                            ),
                        ),
                        timeline_view(),
                        _span_detail_import(),
                        spacing="3",
                        width="100%",
                        padding="1em",
                    ),
                    value="timeline",
                ),
                rx.tabs.content(event_registry(), value="registry"),
                default_value="overview",
                width="100%",
            ),
            width="100%",
            max_width="1200px",
            margin_x="auto",
            padding="1em",
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
