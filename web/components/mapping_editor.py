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
    output_type = rule["output_type"].to(str)
    is_event = output_type == "event"
    attr_count = rule["attr_count"].to(int)
    attr_summary = rule["attr_summary"].to(str)

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
                rx.cond(
                    is_event,
                    rx.badge("event", color_scheme="orange", size="1"),
                    rx.badge("span", color_scheme="blue", size="1"),
                ),
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
            # Output type + Parent + root toggle
            rx.hstack(
                rx.text("Output:", size="2", width="80px"),
                rx.select(
                    ["span", "event"],
                    value=output_type,
                    size="2",
                    on_change=lambda v: State.update_rule_field(
                        rule_id, "output_type", v
                    ),
                ),
                rx.text("Parent:", size="2"),
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
                rx.badge(
                    attr_count.to(str),
                    color_scheme="gray",
                    size="1",
                ),
                rx.spacer(),
                rx.button(
                    "+ Add Attribute",
                    size="1",
                    variant="outline",
                    on_click=State.add_attribute_mapping(rule_id),
                ),
                width="100%",
                align="center",
            ),
            # Attribute mappings summary
            rx.cond(
                attr_count > 0,
                rx.box(
                    rx.text(
                        attr_summary,
                        size="1",
                        font_family="JetBrains Mono, monospace",
                        white_space="pre",
                    ),
                    width="100%",
                    padding="0.5em",
                    border="1px solid var(--gray-a3)",
                    border_radius="var(--radius-1)",
                    max_height="200px",
                    overflow_y="auto",
                    background="var(--gray-a2)",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
    )


def _rule_stat_row(stat: rx.Var[dict]) -> rx.Component:
    """Single rule stat row."""
    return rx.hstack(
        rx.text(
            stat["value_type"].to(str),
            size="1",
            weight="medium",
            min_width="150px",
        ),
        rx.badge(
            stat["match_count"].to(str),
            " matched",
            color_scheme=rx.cond(stat["match_count"].to(int) > 0, "green", "gray"),
            size="1",
        ),
        rx.badge(
            stat["attr_count"].to(str),
            " attrs",
            color_scheme="blue",
            size="1",
        ),
        rx.cond(
            stat["attr_count"].to(int) > 0,
            rx.badge(
                stat["fill_rate"].to(str),
                "%",
                color_scheme=rx.cond(
                    stat["fill_rate"].to(float) >= 80.0,
                    "green",
                    rx.cond(
                        stat["fill_rate"].to(float) >= 50.0,
                        "orange",
                        "red",
                    ),
                ),
                size="1",
            ),
        ),
        spacing="2",
        width="100%",
        padding_y="2px",
    )


def mapping_editor() -> rx.Component:
    """Rule cards panel with optional stats."""
    return rx.vstack(
        rx.heading("Mapping Rules", size="4"),
        # Rule match stats (shown after preview)
        rx.cond(
            State.rule_stats.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("bar-chart-3", size=14, color="var(--blue-9)"),
                        rx.text("Rule Match Stats", size="2", weight="bold"),
                        spacing="2",
                        align="center",
                    ),
                    rx.foreach(State.rule_stats, _rule_stat_row),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
        ),
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
