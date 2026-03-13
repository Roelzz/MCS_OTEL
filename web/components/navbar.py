import reflex as rx


def navbar() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.heading("MCS-OTEL Mapper", size="5"),
            href="/",
            underline="none",
            color="inherit",
        ),
        rx.spacer(),
        rx.link(
            rx.button(
                rx.icon("map", size=14),
                "Mapper",
                size="2",
                variant="outline",
            ),
            href="/",
        ),
        rx.link(
            rx.button(
                rx.icon("sparkles", size=14),
                "Improve Mapping",
                size="2",
                variant="outline",
                color_scheme="purple",
            ),
            href="/improve",
        ),
        rx.color_mode.button(size="2"),
        padding_x="2em",
        padding_y="1em",
        width="100%",
        border_bottom="1px solid var(--gray-a4)",
        background=rx.color_mode_cond("white", "var(--gray-1)"),
    )
