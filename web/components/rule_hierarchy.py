import reflex as rx

from web.components.react_flow import mapping_flow
from web.state import State


def rule_hierarchy() -> rx.Component:
    """Read-only React Flow graph showing rule parent-child hierarchy."""
    return rx.vstack(
        rx.hstack(
            rx.heading("Rule Hierarchy", size="4"),
            rx.spacer(),
            rx.cond(
                State.rule_hierarchy_nodes.length() > 0,  # type: ignore
                rx.badge(
                    State.rule_hierarchy_nodes.length(),  # type: ignore
                    " rules",
                    size="2",
                    variant="soft",
                ),
            ),
        ),
        rx.cond(
            State.rule_hierarchy_nodes.length() > 0,  # type: ignore
            rx.box(
                mapping_flow(
                    initial_nodes=State.rule_hierarchy_nodes,
                    initial_edges=State.rule_hierarchy_edges,
                    on_connect_edge=lambda _: None,  # type: ignore
                    on_delete_edge=lambda _: None,  # type: ignore
                    on_edge_click=lambda _: None,  # type: ignore
                ),
                width="100%",
                min_height="400px",
                height="60vh",
                max_height="700px",
                border_radius="var(--radius-2)",
                border="1px solid var(--gray-a5)",
                overflow="hidden",
            ),
            rx.callout(
                "Load a mapping to see rule hierarchy.",
                icon="info",
                size="2",
            ),
        ),
        rx.text(
            "Green border = high fill rate (>80%), orange = medium (50-80%), red = low (<50%), gray = no stats yet. "
            "Yellow background = event rules.",
            size="1",
            color="var(--gray-9)",
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
