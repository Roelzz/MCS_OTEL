import reflex as rx

from web.state import State


def _attr_mapping_row(am: rx.Var[dict]) -> rx.Component:
    rule_id = am["rule_id"].to(str)
    idx = am["idx"].to(int)
    mcs_prop = am["mcs_property"].to(str)
    otel_attr = am["otel_attribute"].to(str)
    transform = am["transform"].to(str)

    return rx.hstack(
        rx.input(
            value=mcs_prop,
            placeholder="mcs_property",
            size="1",
            on_change=lambda v: State.update_attribute_mapping(rule_id, idx, "mcs_property", v),
            flex="1",
        ),
        rx.icon("arrow_right", size=12, color="var(--gray-8)"),
        rx.input(
            value=otel_attr,
            placeholder="otel_attribute",
            size="1",
            on_change=lambda v: State.update_attribute_mapping(rule_id, idx, "otel_attribute", v),
            flex="1",
        ),
        rx.select(
            ["direct", "template", "constant", "lookup"],
            value=transform,
            size="1",
            on_change=lambda v: State.update_attribute_mapping(rule_id, idx, "transform", v),
        ),
        rx.icon_button(
            rx.icon("x", size=12),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=State.remove_attribute_mapping(rule_id, idx),
        ),
        spacing="1",
        width="100%",
        align="center",
        padding_y="2px",
    )


def _rule_header(rule: rx.Var[dict]) -> rx.Component:
    """Shared header row: chevron + badges + type indicator + delete."""
    rule_id = rule["rule_id"].to(str)
    mcs_entity_type = rule["mcs_entity_type"].to(str)
    mcs_value_type = rule["mcs_value_type"].to(str)
    otel_op = rule["otel_operation_name"].to(str)
    output_type = rule["output_type"].to(str)
    is_event = output_type == "event"
    is_collapsed = rule["is_collapsed"].to(bool)

    return rx.hstack(
        rx.icon(
            rx.cond(is_collapsed, "chevron_right", "chevron_down"),
            size=14,
            color="var(--gray-9)",
            cursor="pointer",
            flex_shrink="0",
        ),
        rx.text(rule_id, size="2", weight="bold", min_width="120px"),
        rx.badge(mcs_entity_type, variant="surface", size="1"),
        rx.badge(mcs_value_type, variant="surface", color_scheme="gray", size="1"),
        rx.icon("arrow_right", size=12, color="var(--gray-8)"),
        rx.badge(otel_op, color_scheme="green", size="1"),
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
        cursor="pointer",
        on_click=State.toggle_rule_collapse(rule_id),
    )


def _inline_stats(rule: rx.Var[dict]) -> rx.Component:
    """Inline stats badges (shown when preview has been run)."""
    match_count = rule["stat_match_count"].to(int)
    attr_count = rule["attr_count"].to(int)
    fill_rate = rule["stat_fill_rate"].to(float)
    has_stats = match_count >= 0

    return rx.cond(
        has_stats,
        rx.hstack(
            rx.badge(
                match_count.to(str),
                " matched",
                color_scheme=rx.cond(match_count > 0, "green", "gray"),
                size="1",
            ),
            rx.badge(attr_count.to(str), " attrs", color_scheme="blue", size="1"),
            rx.cond(
                attr_count > 0,
                rx.badge(
                    fill_rate.to(str),
                    "%",
                    color_scheme=rx.cond(
                        fill_rate >= 80.0,
                        "green",
                        rx.cond(fill_rate >= 50.0, "orange", "red"),
                    ),
                    size="1",
                ),
            ),
            spacing="2",
        ),
    )


def _rule_body(rule: rx.Var[dict]) -> rx.Component:
    """Expanded editor body: name, output, parent, attributes."""
    rule_id = rule["rule_id"].to(str)
    span_name = rule["span_name_template"].to(str)
    parent_id = rule["parent_rule_id"].to(str)
    is_root = rule["is_root"].to(bool)
    output_type = rule["output_type"].to(str)
    attr_count = rule["attr_count"].to(int)
    description = rule["description"].to(str)
    validation_error = rule["validation_error"].to(str)

    return rx.vstack(
        rx.separator(),
        # Description
        rx.cond(
            description != "",
            rx.text(
                description,
                size="1",
                color="var(--gray-10)",
                font_style="italic",
                padding_x="0.25em",
            ),
        ),
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
        rx.cond(
            validation_error != "",
            rx.text(
                validation_error,
                size="1",
                color="var(--red-11)",
            ),
        ),
        # Attribute mappings heading + add button
        rx.hstack(
            rx.text("Attribute Mappings", size="2", weight="bold"),
            rx.badge(attr_count.to(str), color_scheme="gray", size="1"),
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
        rx.cond(
            attr_count > 0,
            rx.vstack(
                rx.foreach(
                    rule["enriched_attribute_mappings"],
                    _attr_mapping_row,
                ),
                spacing="1",
                width="100%",
                border="1px solid var(--gray-a3)",
                border_radius="var(--radius-1)",
                padding="0.5em",
                max_height="250px",
                overflow_y="auto",
            ),
        ),
        spacing="2",
        width="100%",
    )


def _rule_card(rule: rx.Var[dict]) -> rx.Component:
    """Collapsible rule card."""
    is_collapsed = rule["is_collapsed"].to(bool)
    description = rule["description"].to(str)

    return rx.card(
        rx.vstack(
            _rule_header(rule),
            # Collapsed: show description snippet + inline stats
            rx.cond(
                is_collapsed,
                rx.vstack(
                    rx.cond(
                        description != "",
                        rx.text(
                            description,
                            size="1",
                            color="var(--gray-9)",
                            font_style="italic",
                            no_of_lines=1,
                        ),
                    ),
                    _inline_stats(rule),
                    spacing="1",
                    width="100%",
                    padding_left="22px",
                ),
                # Expanded: full editor + inline stats
                rx.vstack(
                    _inline_stats(rule),
                    _rule_body(rule),
                    spacing="2",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
    )


def _stats_explainer() -> rx.Component:
    """Explanation of what the stat badges mean."""
    return rx.callout(
        rx.vstack(
            rx.text("Rule Match Stats", weight="bold", size="2"),
            rx.text(
                "• Matched — entities from the transcript that activated this rule",
                size="1",
            ),
            rx.text(
                "• Attrs — number of attribute mappings defined on this rule",
                size="1",
            ),
            rx.text(
                "• % Score — fill rate: percentage of mapped attributes that have actual values",
                size="1",
            ),
            spacing="1",
        ),
        icon="info",
        size="1",
        color_scheme="blue",
        variant="surface",
        width="100%",
    )


def mapping_editor() -> rx.Component:
    """Rule cards panel with collapsible rules and inline stats."""
    return rx.vstack(
        rx.hstack(
            rx.heading("Mapping Rules", size="4"),
            rx.badge(
                State.mapping_rules.length().to(str),
                " rules",
                color_scheme="gray",
            ),
            rx.cond(
                State.rule_filter_text != "",
                rx.badge(
                    State.mapping_rules.length().to(str),
                    " of ",
                    State.total_rule_count.to(str),
                    color_scheme="blue",
                    size="1",
                ),
            ),
            rx.hstack(
                rx.icon("search", size=14, color="var(--gray-9)"),
                rx.input(
                    placeholder="Filter rules...",
                    value=State.rule_filter_text,
                    on_change=State.set_rule_filter_text,
                    size="1",
                    width="180px",
                ),
                rx.cond(
                    State.rule_filter_text != "",
                    rx.icon_button(
                        rx.icon("x", size=12),
                        size="1",
                        variant="ghost",
                        on_click=State.set_rule_filter_text(""),
                    ),
                ),
                spacing="1",
                align="center",
            ),
            rx.spacer(),
            rx.button(
                "Expand All",
                size="1",
                variant="ghost",
                on_click=State.expand_all_rules,
            ),
            rx.button(
                "Collapse All",
                size="1",
                variant="ghost",
                on_click=State.collapse_all_rules,
            ),
            spacing="2",
            width="100%",
            align="center",
        ),
        # Stats explainer (shown after preview)
        rx.cond(State.rule_stats.length() > 0, _stats_explainer()),
        rx.cond(
            State.has_mapping,
            rx.vstack(
                rx.foreach(State.mapping_rules, _rule_card),
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
