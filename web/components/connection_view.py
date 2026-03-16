import reflex as rx

from web.components.react_flow import mapping_flow
from web.state import State


def _import_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button("Import Mapping", size="2", variant="outline"),
        ),
        rx.dialog.content(
            rx.dialog.title("Import Mapping"),
            rx.dialog.description("Paste a mapping JSON specification below."),
            rx.text_area(
                value=State.import_json_text,
                on_change=State.set_import_json_text,
                placeholder='{"version": "1.0", "name": "...", "rules": [...]}',
                rows="10",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="soft", color_scheme="gray"),
                ),
                rx.dialog.close(
                    rx.button(
                        "Import",
                        on_click=State.import_mapping(State.import_json_text),
                    ),
                ),
                spacing="3",
                justify="end",
                width="100%",
                margin_top="1em",
            ),
        ),
    )


def _connection_detail_row(am: dict) -> rx.Component:
    return rx.hstack(
        rx.text(am["mcs_property"], size="2", font_family="JetBrains Mono", color="var(--blue-11)"),
        rx.icon("arrow-right", size=14, color="var(--gray-8)"),
        rx.text(am["otel_attribute"], size="2", font_family="JetBrains Mono"),
        rx.badge(am["transform"], size="1", variant="outline"),
        spacing="2",
        width="100%",
        padding_y="2px",
    )


def _connection_detail() -> rx.Component:
    return rx.cond(
        State.selected_connection_rule_id != "",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("link", size=16, color="var(--green-9)"),
                    rx.text(State.selected_connection_rule_name, weight="bold", size="3"),
                    rx.spacer(),
                    rx.badge(
                        rx.text(State.selected_connection_detail.length(), size="1"),  # type: ignore
                        " attrs",
                        size="1",
                        variant="soft",
                    ),
                    width="100%",
                ),
                rx.cond(
                    State.selected_connection_detail.length() > 0,  # type: ignore
                    rx.vstack(
                        rx.foreach(State.selected_connection_detail, _connection_detail_row),
                        spacing="1",
                        width="100%",
                    ),
                    rx.text("No attribute mappings", size="2", color="var(--gray-9)"),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
    )


def connection_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Connection Mapping", size="4"),
            rx.spacer(),
            _import_dialog(),
            rx.button(
                "Load Defaults",
                on_click=State.load_defaults,
                size="2",
                variant="outline",
            ),
        ),
        rx.box(
            mapping_flow(
                initial_nodes=State.flow_nodes,
                initial_edges=State.flow_edges,
                on_connect_edge=State.on_flow_connect,
                on_delete_edge=State.on_flow_edge_delete,
                on_edge_click=State.select_connection_rule,
            ),
            width="100%",
            min_height="500px",
            height="70vh",
            max_height="900px",
            border_radius="var(--radius-2)",
            border="1px solid var(--gray-a5)",
            overflow="hidden",
        ),
        rx.text(
            "Drag from MCS entity handle (right) to OTEL target handle (left) to create connections. "
            "Select an edge and press Delete/Backspace to remove it. Click an edge to inspect its mapping.",
            size="1",
            color="var(--gray-9)",
        ),
        _connection_detail(),
        spacing="3",
        width="100%",
        padding="1em",
    )
