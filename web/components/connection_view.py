import reflex as rx

from web.state import State
from otel_registry import OTEL_TARGETS

MCS_ENTITY_LABELS: list[str] = [
    "SessionInfo",
    "turn",
    "UniversalSearchToolTraceData",
    "DynamicPlanReceived",
    "DynamicPlanStepBindUpdate",
    "DynamicPlanStepFinished",
    "DynamicPlanFinished",
    "DynamicServerInitialize",
    "DynamicServerToolsList",
    "DialogRedirect",
    "DialogTracing",
    "VariableAssignment",
    "ErrorTraceData",
]

OTEL_COLORS: dict[str, str] = {
    "agent.turn": "blue",
    "gen_ai.chat": "green",
    "tool.execute": "orange",
    "knowledge.retrieval": "teal",
    "chain": "purple",
    "text_completion": "gray",
    "create_agent": "cyan",
    "topic_classification": "amber",
}


def _mcs_card(label: str) -> rx.Component:
    return rx.box(
        rx.text(label, size="2", weight="medium"),
        padding="0.5em 1em",
        border_radius="var(--radius-2)",
        border=rx.cond(
            State.selected_mcs_entity == label,
            "2px solid var(--green-9)",
            "1px solid var(--gray-a5)",
        ),
        background=rx.cond(
            State.selected_mcs_entity == label,
            "var(--green-a3)",
            "transparent",
        ),
        cursor="pointer",
        on_click=State.select_mcs_entity(label),
        _hover={"background": "var(--gray-a3)"},
    )


def _otel_card(target: str) -> rx.Component:
    color = OTEL_COLORS.get(target, "gray")
    return rx.box(
        rx.text(target, size="2", weight="medium"),
        padding="0.5em 1em",
        border_radius="var(--radius-2)",
        border=f"1px solid var(--{color}-a5)",
        cursor="pointer",
        on_click=State.connect_to_otel(target),
        _hover={"background": f"var(--{color}-a3)"},
    )


def _connection_badge(conn: rx.Var[dict]) -> rx.Component:
    mcs = conn["mcs_entity_type"].to(str)
    otel = conn["otel_target"].to(str)
    rid = conn["rule_id"].to(str)
    return rx.hstack(
        rx.badge(mcs, variant="surface"),
        rx.icon("arrow_right", size=14),
        rx.badge(otel, color_scheme="green"),
        rx.icon_button(
            rx.icon("x", size=12),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=State.remove_connection(rid),
        ),
        spacing="2",
        align="center",
    )


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
        rx.hstack(
            # Left: MCS entities
            rx.vstack(
                rx.text(
                    "MCS Entities",
                    size="2",
                    weight="bold",
                    color="var(--gray-11)",
                ),
                *[_mcs_card(label) for label in MCS_ENTITY_LABELS],
                spacing="2",
                min_width="200px",
            ),
            # Middle: connections
            rx.vstack(
                rx.text(
                    "Connections",
                    size="2",
                    weight="bold",
                    color="var(--gray-11)",
                ),
                rx.cond(
                    State.connections.length() > 0,
                    rx.vstack(
                        rx.foreach(State.connections, _connection_badge),
                        spacing="2",
                    ),
                    rx.text(
                        "Click MCS then OTEL to connect",
                        size="1",
                        color="var(--gray-9)",
                    ),
                ),
                spacing="2",
                flex="1",
                align="center",
            ),
            # Right: OTEL targets
            rx.vstack(
                rx.text(
                    "OTEL Targets",
                    size="2",
                    weight="bold",
                    color="var(--gray-11)",
                ),
                *[_otel_card(target) for target in OTEL_TARGETS],
                spacing="2",
                min_width="200px",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
