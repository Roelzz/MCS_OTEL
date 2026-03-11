import reflex as rx

from web.state import State


def _rule_card(rule: rx.Var[dict]) -> rx.Component:
    """Single rule card rendered inside rx.foreach."""
    rule_id = rule["rule_id"].to(str)
    mcs_entity_type = rule["mcs_entity_type"].to(str)
    mcs_value_type = rule["mcs_value_type"].to(str)
    otel_op = rule["otel_operation_name"].to(str)
    span_name = rule["span_name_template"].to(str)
    parent_id = rule["parent_rule_id"].to(str)
    is_root = rule["is_root"].to(bool)

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(mcs_entity_type, variant="surface"),
                rx.badge(
                    mcs_value_type,
                    variant="surface",
                    color_scheme="gray",
                ),
                rx.icon("arrow_right", size=14),
                rx.badge(otel_op, color_scheme="green"),
                rx.spacer(),
                rx.icon_button(
                    rx.icon("trash_2", size=14),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=State.remove_connection(rule_id),
                ),
                spacing="2",
                width="100%",
                align="center",
            ),
            rx.separator(),
            # Span name template
            rx.hstack(
                rx.text("Name:", size="2", width="80px"),
                rx.input(
                    value=span_name,
                    size="2",
                    on_change=lambda v: State.update_rule_field(
                        rule_id, "span_name_template", v
                    ),
                    flex="1",
                ),
                width="100%",
            ),
            # Parent + root toggle
            rx.hstack(
                rx.text("Parent:", size="2", width="80px"),
                rx.input(
                    value=parent_id,
                    size="2",
                    placeholder="parent rule id",
                    on_change=lambda v: State.update_rule_field(
                        rule_id, "parent_rule_id", v
                    ),
                    flex="1",
                ),
                rx.switch(
                    checked=is_root,
                    on_change=lambda v: State.update_rule_field(
                        rule_id, "is_root", v.to(str)
                    ),
                ),
                rx.text("Root", size="2"),
                width="100%",
            ),
            # Attribute mappings heading + add button
            rx.hstack(
                rx.text("Attribute Mappings", size="2", weight="bold"),
                rx.spacer(),
                rx.button(
                    "+ Add Attribute",
                    size="1",
                    variant="outline",
                    on_click=State.add_attribute_mapping(rule_id),
                ),
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
    )


def mapping_editor() -> rx.Component:
    """Rule cards panel."""
    return rx.vstack(
        rx.heading("Mapping Rules", size="4"),
        rx.cond(
            State.has_mapping,
            rx.vstack(
                rx.foreach(
                    State.mapping_rules,
                    _rule_card,
                ),
                spacing="3",
                width="100%",
            ),
            rx.text(
                "No mapping loaded. Click 'Load Defaults' above.",
                size="2",
                color="var(--gray-9)",
            ),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
