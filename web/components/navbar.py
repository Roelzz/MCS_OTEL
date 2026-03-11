import reflex as rx


def navbar() -> rx.Component:
    return rx.hstack(
        rx.heading("MCS-OTEL Mapper", size="5"),
        rx.spacer(),
        rx.color_mode.button(size="2"),
        padding_x="2em",
        padding_y="1em",
        width="100%",
        border_bottom="1px solid var(--gray-a4)",
        background=rx.color_mode_cond("white", "var(--gray-1)"),
    )
