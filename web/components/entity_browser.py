import reflex as rx

from web.state import State


def _type_card(type_info: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text(type_info["value_type"], weight="bold", size="3"),
                rx.spacer(),
                rx.badge(type_info["count"], size="2", variant="solid"),
                width="100%",
            ),
            rx.hstack(
                rx.foreach(
                    type_info["top_keys"],
                    lambda k: rx.badge(k, size="1", variant="outline", color_scheme="gray"),
                ),
                wrap="wrap",
                spacing="1",
            ),
            spacing="2",
        ),
        cursor="pointer",
        on_click=State.set_entity_type_filter(type_info["value_type"]),
        _hover={"border_color": "var(--green-8)"},
        border=rx.cond(
            State.entity_type_filter == type_info["value_type"],
            "2px solid var(--green-9)",
            "1px solid var(--gray-a5)",
        ),
        width="100%",
    )


def _entity_row(entity: dict) -> rx.Component:
    eid = entity["entity_id"]
    label = entity["label"]
    prop_count = entity["properties"].length()  # type: ignore
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(label, size="2", weight="medium", trim="both"),
                rx.text(
                    eid,
                    size="1",
                    color="var(--gray-9)",
                    font_family="JetBrains Mono",
                    trim="both",
                ),
                spacing="0",
            ),
            rx.spacer(),
            rx.badge(prop_count, " props", size="1", variant="soft"),
            width="100%",
            align="center",
        ),
        cursor="pointer",
        on_click=State.select_entity(eid),
        padding="8px 12px",
        border_radius="var(--radius-2)",
        background=rx.cond(
            State.selected_entity_id == eid,
            "var(--green-a3)",
            "transparent",
        ),
        _hover={"background": "var(--gray-a3)"},
    )


def _detail_row(prop: dict) -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.text(
                prop["key"],
                size="2",
                font_family="JetBrains Mono",
                color="var(--blue-11)",
            ),
            rx.cond(
                prop["is_enriched"],
                rx.badge("enriched", size="1", color_scheme="purple", variant="outline"),
                rx.badge("original", size="1", color_scheme="gray", variant="outline"),
            ),
            min_width="220px",
            flex_shrink="0",
            spacing="1",
            align="center",
        ),
        rx.text(
            rx.cond(prop["value"] != "", prop["value"], "(empty)"),
            size="2",
            font_family="JetBrains Mono",
            color=rx.cond(prop["value"] != "", "inherit", "var(--gray-8)"),
            word_break="break-all",
        ),
        width="100%",
        padding_y="4px",
        border_bottom="1px solid var(--gray-a3)",
        align="start",
    )


def _entity_detail() -> rx.Component:
    return rx.cond(
        State.selected_entity_id != "",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("file-text", size=16, color="var(--green-9)"),
                    rx.text("Entity Detail", weight="bold", size="3"),
                    rx.spacer(),
                    rx.badge(
                        State.selected_entity_detail.length(),  # type: ignore
                        " properties",
                        size="1",
                        variant="soft",
                    ),
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.foreach(State.selected_entity_detail, _detail_row),
                        spacing="0",
                        width="100%",
                    ),
                    max_height="400px",
                    overflow_y="auto",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
    )


def entity_browser() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Entity Browser", size="4"),
            rx.spacer(),
            rx.cond(
                State.entity_type_filter != "",
                rx.button(
                    "Clear Filter",
                    on_click=State.set_entity_type_filter(""),
                    size="1",
                    variant="ghost",
                ),
            ),
        ),
        rx.cond(
            State.entities.length() > 0,  # type: ignore
            rx.hstack(
                # Left panel: type cards
                rx.vstack(
                    rx.text("Entity Types", weight="bold", size="2", color="var(--gray-11)"),
                    rx.vstack(
                        rx.foreach(State.entity_types_summary, _type_card),
                        spacing="2",
                        width="100%",
                    ),
                    width="280px",
                    min_width="280px",
                    spacing="3",
                ),
                # Right panel: entity list + detail
                rx.vstack(
                    rx.text(
                        rx.cond(
                            State.entity_type_filter != "",
                            rx.fragment(
                                "Showing: ",
                                rx.text(State.entity_type_filter, as_="span", weight="bold"),
                            ),
                            "All Entities",
                        ),
                        size="2",
                        color="var(--gray-11)",
                        weight="bold",
                    ),
                    rx.box(
                        rx.vstack(
                            rx.foreach(State.filtered_entities, _entity_row),
                            spacing="1",
                            width="100%",
                        ),
                        max_height="400px",
                        overflow_y="auto",
                        width="100%",
                        border="1px solid var(--gray-a4)",
                        border_radius="var(--radius-2)",
                        padding="4px",
                    ),
                    _entity_detail(),
                    flex="1",
                    spacing="3",
                    min_width="0",
                ),
                spacing="4",
                width="100%",
                align="start",
            ),
            rx.callout(
                "Upload a transcript to browse entities.",
                icon="info",
                size="2",
            ),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
