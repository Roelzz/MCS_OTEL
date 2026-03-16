import reflex as rx

from web.state import State


def _status_badge(status: rx.Var[str]) -> rx.Component:
    return rx.badge(
        status,
        size="1",
        color_scheme=rx.cond(
            status == "covered",
            "green",
            rx.cond(
                status == "gap",
                "orange",
                rx.cond(status == "unused", "gray", "red"),
            ),
        ),
    )


def _event_row(em: rx.Var[dict]) -> rx.Component:
    vt = em["value_type"].to(str)
    label = em["label"].to(str)
    desc = em["description"].to(str)
    ec = em["entity_count"].to(int)
    output = em["default_output_type"].to(str)
    has_rule = em["has_rule"].to(bool)
    status = em["status"].to(str)
    rule_id = em["rule_id"].to(str)

    return rx.table.row(
        rx.table.cell(rx.text(label, size="2", weight="medium")),
        rx.table.cell(rx.code(vt, size="1")),
        rx.table.cell(rx.text(desc, size="1", color="var(--gray-9)", no_of_lines=1)),
        rx.table.cell(
            rx.badge(
                ec.to(str),
                size="1",
                color_scheme=rx.cond(ec > 0, "blue", "gray"),
            ),
        ),
        rx.table.cell(
            rx.cond(
                output != "",
                rx.badge(output, size="1", variant="outline"),
                rx.fragment(),
            ),
        ),
        rx.table.cell(
            rx.cond(
                has_rule,
                rx.badge(rule_id[:12], size="1", color_scheme="green", variant="outline"),
                rx.text("—", size="1", color="var(--gray-8)"),
            ),
        ),
        rx.table.cell(_status_badge(status)),
        _hover={"background": "var(--gray-a3)"},
        cursor="pointer",
        on_click=State.set_rule_filter_text(vt),
    )


def _error_row(err: rx.Var[dict]) -> rx.Component:
    name = err["name"].to(str)
    detail = err["detail"].to(str)
    span_id = err["span_id"].to(str)
    error_type = err["error_type"].to(str)

    return rx.hstack(
        rx.badge(
            error_type,
            size="1",
            color_scheme="red",
        ),
        rx.text(name, size="2", weight="medium"),
        rx.text(detail, size="1", color="var(--gray-9)", no_of_lines=1, flex="1"),
        rx.icon_button(
            rx.icon("arrow-right", size=12),
            size="1",
            variant="ghost",
            on_click=State.select_span(span_id),
        ),
        spacing="2",
        width="100%",
        padding_y="4px",
    )


def _error_section() -> rx.Component:
    return rx.cond(
        State.error_summary.length() > 0,  # type: ignore
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("alert-triangle", size=16, color="var(--red-9)"),
                    rx.text("Errors", weight="bold", size="3"),
                    rx.badge(
                        State.error_summary.length(),  # type: ignore
                        size="1",
                        color_scheme="red",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.vstack(
                    rx.foreach(State.error_summary, _error_row),
                    spacing="1",
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
    )


def event_registry() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Event Registry", size="4"),
            rx.spacer(),
            rx.cond(
                State.event_metadata_list.length() > 0,  # type: ignore
                rx.badge(
                    State.event_metadata_list.length(),  # type: ignore
                    " event types",
                    size="2",
                    variant="soft",
                ),
            ),
        ),
        _error_section(),
        rx.cond(
            State.event_metadata_list.length() > 0,  # type: ignore
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Label"),
                        rx.table.column_header_cell("Value Type"),
                        rx.table.column_header_cell("Description"),
                        rx.table.column_header_cell("Entities"),
                        rx.table.column_header_cell("Output"),
                        rx.table.column_header_cell("Rule"),
                        rx.table.column_header_cell("Status"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(State.event_metadata_list, _event_row),
                ),
                width="100%",
            ),
            rx.callout(
                "Load a mapping with event_metadata to see the registry.",
                icon="info",
                size="2",
            ),
        ),
        rx.text(
            "Green = entities + rule (covered), Orange = entities but no rule (gap), "
            "Gray = rule but no entities (unused), Red = neither (inactive). "
            "Click a covered row to filter mapping rules.",
            size="1",
            color="var(--gray-9)",
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
