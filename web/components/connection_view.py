import reflex as rx

from web.components.react_flow import mapping_flow
from web.state import State


def connection_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Connection Mapping", size="4"),
            rx.spacer(),
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
            ),
            width="100%",
            height="650px",
            border_radius="var(--radius-2)",
            border="1px solid var(--gray-a5)",
            overflow="hidden",
        ),
        rx.text(
            "Drag from MCS entity handle (right) to OTEL target handle (left) to create connections. "
            "Select an edge and press Delete/Backspace to remove it.",
            size="1",
            color="var(--gray-9)",
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
