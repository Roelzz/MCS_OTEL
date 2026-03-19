"""Fixed sidebar with 6-step navigation and evaluate sub-steps."""

import reflex as rx

from web.state import State

SIDEBAR_STEPS: list[dict] = [
    {"key": "load", "label": "Load Mapping", "icon": "folder-open", "number": "1"},
    {"key": "connections", "label": "Connections", "icon": "git-branch", "number": "2"},
    {"key": "rules", "label": "Rules", "icon": "list", "number": "3"},
    {"key": "improve", "label": "Improve", "icon": "sparkles", "number": "4"},
    {"key": "evaluate", "label": "Evaluate", "icon": "flask-conical", "number": "5"},
    {"key": "save", "label": "Save", "icon": "save", "number": "6"},
]

EVALUATE_SUBS: list[dict] = [
    {"key": "upload", "label": "Upload & Preview", "icon": "upload"},
    {"key": "span_tree", "label": "Span Tree", "icon": "git-commit-horizontal"},
    {"key": "session", "label": "Session", "icon": "layout-dashboard"},
    {"key": "conversation", "label": "Conversation", "icon": "message-square"},
    {"key": "entities", "label": "Entities", "icon": "database"},
    {"key": "rule_graph", "label": "Rule Graph", "icon": "network"},
    {"key": "registry", "label": "Event Registry", "icon": "scroll-text"},
]


def _status_dot(step_key: str) -> rx.Component:
    """Green dot if step has data, gray otherwise."""
    has_data = rx.cond(
        step_key == "load",
        State.has_mapping,
        rx.cond(
            step_key == "connections",
            State.has_mapping,
            rx.cond(
                step_key == "rules",
                State.has_mapping,
                rx.cond(
                    step_key == "evaluate",
                    State.has_transcript,
                    False,
                ),
            ),
        ),
    )
    return rx.cond(
        has_data,
        rx.box(
            width="8px",
            height="8px",
            border_radius="50%",
            background="var(--green-9)",
            flex_shrink="0",
        ),
        rx.box(
            width="8px",
            height="8px",
            border_radius="50%",
            background="var(--gray-6)",
            flex_shrink="0",
        ),
    )


def _sub_status_dot(sub_key: str) -> rx.Component:
    """Green dot for sub-step items based on data availability."""
    has_data = rx.cond(
        sub_key == "upload",
        State.has_transcript,
        rx.cond(
            sub_key == "entities",
            State.has_transcript,
            State.has_preview,
        ),
    )
    return rx.cond(
        has_data,
        rx.box(
            width="6px",
            height="6px",
            border_radius="50%",
            background="var(--green-9)",
            flex_shrink="0",
        ),
        rx.box(
            width="6px",
            height="6px",
            border_radius="50%",
            background="var(--gray-5)",
            flex_shrink="0",
        ),
    )


def _step_button(step: dict) -> rx.Component:
    key = step["key"]
    is_active = State.current_step == key
    return rx.box(
        rx.hstack(
            rx.cond(
                is_active,
                rx.box(
                    rx.text(step["number"], size="1", weight="bold", color="white"),
                    width="24px",
                    height="24px",
                    border_radius="50%",
                    background="var(--green-9)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    flex_shrink="0",
                ),
                rx.box(
                    rx.text(step["number"], size="1", weight="bold", color="var(--gray-8)"),
                    width="24px",
                    height="24px",
                    border_radius="50%",
                    background="var(--gray-3)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    flex_shrink="0",
                ),
            ),
            rx.icon(step["icon"], size=16, color=rx.cond(is_active, "var(--green-11)", "var(--gray-9)")),
            rx.text(
                step["label"],
                size="2",
                weight=rx.cond(is_active, "medium", "regular"),
                color=rx.cond(is_active, "var(--green-11)", "var(--gray-11)"),
            ),
            rx.spacer(),
            _status_dot(key),
            spacing="2",
            align="center",
            width="100%",
        ),
        padding_x="12px",
        padding_y="10px",
        border_radius="var(--radius-2)",
        background=rx.cond(is_active, "var(--green-a3)", "transparent"),
        cursor="pointer",
        _hover={"background": rx.cond(is_active, "var(--green-a3)", "var(--gray-a3)")},
        on_click=State.set_step(key),
        width="100%",
    )


def _sub_step_button(sub: dict) -> rx.Component:
    key = sub["key"]
    is_active = (State.current_step == "evaluate") & (State.evaluate_sub_step == key)
    return rx.box(
        rx.hstack(
            rx.icon(sub["icon"], size=14, color=rx.cond(is_active, "var(--green-11)", "var(--gray-8)")),
            rx.text(
                sub["label"],
                size="1",
                weight=rx.cond(is_active, "medium", "regular"),
                color=rx.cond(is_active, "var(--green-11)", "var(--gray-11)"),
            ),
            rx.spacer(),
            _sub_status_dot(key),
            spacing="2",
            align="center",
            width="100%",
        ),
        padding_left="44px",
        padding_right="12px",
        padding_y="6px",
        border_radius="var(--radius-2)",
        background=rx.cond(is_active, "var(--green-a2)", "transparent"),
        cursor="pointer",
        _hover={"background": rx.cond(is_active, "var(--green-a2)", "var(--gray-a2)")},
        on_click=State.set_evaluate_sub_step(key),
        width="100%",
    )


def sidebar() -> rx.Component:
    step_items = []
    for step in SIDEBAR_STEPS:
        step_items.append(_step_button(step))
        if step["key"] == "evaluate":
            step_items.append(
                rx.cond(
                    State.current_step == "evaluate",
                    rx.vstack(
                        *[_sub_step_button(sub) for sub in EVALUATE_SUBS],
                        spacing="0",
                        width="100%",
                    ),
                )
            )

    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading("MCS-OTEL", size="4", weight="bold"),
                rx.color_mode.button(size="1"),
                width="100%",
                justify="between",
                align="center",
                padding_x="12px",
                padding_y="16px",
            ),
            rx.separator(),
            rx.vstack(
                *step_items,
                spacing="1",
                width="100%",
                padding="8px",
            ),
            spacing="0",
            width="100%",
            height="100%",
        ),
        width="220px",
        min_width="220px",
        height="100vh",
        border_right="1px solid var(--gray-a4)",
        background=rx.color_mode_cond("white", "var(--gray-1)"),
        position="sticky",
        top="0",
        flex_shrink="0",
        overflow_y="auto",
    )
