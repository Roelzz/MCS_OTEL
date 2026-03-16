import reflex as rx

from web.state import State


def _turn_bubble(turn: dict) -> rx.Component:
    is_greeting = turn["is_greeting"]
    user_msg = turn["user_msg"]
    bot_msg = turn["bot_msg"]
    topic = turn["topic_name"]
    action = turn["action_type"]

    return rx.vstack(
        # User message (right-aligned)
        rx.cond(
            user_msg != "",
            rx.hstack(
                rx.spacer(),
                rx.box(
                    rx.text(
                        user_msg,
                        size="2",
                        color="white",
                        font_style=rx.cond(is_greeting, "italic", "normal"),
                    ),
                    background=rx.cond(is_greeting, "var(--gray-8)", "var(--blue-9)"),
                    padding="8px 12px",
                    border_radius="12px 12px 2px 12px",
                    max_width="70%",
                ),
                width="100%",
            ),
        ),
        # Bot message (left-aligned)
        rx.cond(
            bot_msg != "",
            rx.hstack(
                rx.box(
                    rx.text(
                        bot_msg,
                        size="2",
                        font_style=rx.cond(is_greeting, "italic", "normal"),
                    ),
                    background=rx.cond(is_greeting, "var(--gray-a3)", "var(--green-a3)"),
                    padding="8px 12px",
                    border_radius="12px 12px 12px 2px",
                    max_width="70%",
                ),
                rx.spacer(),
                width="100%",
            ),
        ),
        # Metadata line
        rx.hstack(
            rx.cond(
                topic != "",
                rx.text(topic, size="1", color="var(--gray-8)"),
            ),
            rx.cond(
                action != "",
                rx.badge(action, size="1", variant="outline", color_scheme="gray"),
            ),
            spacing="2",
            padding_left="4px",
        ),
        spacing="2",
        width="100%",
        padding_y="4px",
    )


def conversation_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Conversation", size="4"),
            rx.spacer(),
            rx.cond(
                State.conversation_turns.length() > 0,  # type: ignore
                rx.badge(
                    State.conversation_turns.length(),  # type: ignore
                    " turns",
                    size="2",
                    variant="soft",
                ),
            ),
        ),
        rx.cond(
            State.conversation_turns.length() > 0,  # type: ignore
            rx.box(
                rx.vstack(
                    rx.foreach(State.conversation_turns, _turn_bubble),
                    spacing="2",
                    width="100%",
                ),
                max_height="600px",
                overflow_y="auto",
                width="100%",
                padding="8px",
                border="1px solid var(--gray-a4)",
                border_radius="var(--radius-2)",
            ),
            rx.callout(
                "Upload a transcript to see conversation turns.",
                icon="info",
                size="2",
            ),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
