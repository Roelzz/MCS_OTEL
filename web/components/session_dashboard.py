import reflex as rx

from web.state import State


def _outcome_color(outcome: rx.Var[str]) -> rx.Var[str]:
    return rx.cond(
        outcome == "Resolved",
        "green",
        rx.cond(outcome == "Escalated", "red", "gray"),
    )


def _metric_tile(label: str, value: rx.Var, color_scheme: str = "gray") -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(label, size="1", color="var(--gray-9)", weight="medium"),
            rx.text(value, size="4", weight="bold", trim="both"),
            spacing="1",
            align="center",
        ),
        min_width="120px",
    )


def session_dashboard() -> rx.Component:
    ctx = State.session_context
    return rx.vstack(
        rx.heading("Session Dashboard", size="4"),
        rx.cond(
            State.has_session_context,
            rx.vstack(
                # Top row: key metrics
                rx.hstack(
                    rx.card(
                        rx.vstack(
                            rx.text("Outcome", size="1", color="var(--gray-9)", weight="medium"),
                            rx.badge(
                                ctx["outcome"].to(str),  # type: ignore
                                size="2",
                                variant="solid",
                                color_scheme=_outcome_color(ctx["outcome"].to(str)),  # type: ignore
                            ),
                            spacing="1",
                            align="center",
                        ),
                        min_width="120px",
                    ),
                    _metric_tile("Turn Count", ctx["turnCount"].to(str)),  # type: ignore
                    _metric_tile("Channel", ctx["channel"].to(str)),  # type: ignore
                    _metric_tile("Environment", ctx["environment"].to(str)),  # type: ignore
                    _metric_tile("Session Type", ctx["session_type"].to(str)),  # type: ignore
                    wrap="wrap",
                    spacing="3",
                    width="100%",
                ),
                # Second row: bot info + user context
                rx.hstack(
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.icon("bot", size=16, color="var(--blue-9)"),
                                rx.text("Bot Info", weight="bold", size="2"),
                            ),
                            rx.text(
                                rx.text("Name: ", as_="span", weight="medium"),
                                State.transcript["bot_name"].to(str),  # type: ignore
                                size="2",
                            ),
                            rx.text(
                                rx.text("ID: ", as_="span", weight="medium"),
                                State.transcript["bot_id"].to(str),  # type: ignore
                                size="2",
                                font_family="JetBrains Mono",
                            ),
                            spacing="1",
                        ),
                        flex="1",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.icon("user", size=16, color="var(--green-9)"),
                                rx.text("User Context", weight="bold", size="2"),
                            ),
                            rx.text(
                                rx.text("Locale: ", as_="span", weight="medium"),
                                ctx["user_locale"].to(str),  # type: ignore
                                size="2",
                            ),
                            rx.text(
                                rx.text("Timezone: ", as_="span", weight="medium"),
                                ctx["user_timezone"].to(str),  # type: ignore
                                size="2",
                            ),
                            spacing="1",
                        ),
                        flex="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                # Third row: entity type distribution chart
                rx.cond(
                    State.entity_type_distribution.length() > 0,  # type: ignore
                    rx.card(
                        rx.vstack(
                            rx.text("Entity Type Distribution", weight="bold", size="2"),
                            rx.recharts.bar_chart(
                                rx.recharts.bar(
                                    data_key="count",
                                    fill="var(--green-9)",
                                    radius=[0, 4, 4, 0],
                                ),
                                rx.recharts.x_axis(data_key="name", font_size=11, angle=-35),
                                rx.recharts.y_axis(font_size=11),
                                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                                data=State.entity_type_distribution,
                                width="100%",
                                height=250,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            rx.callout(
                "Upload a transcript to see session context.",
                icon="info",
                size="2",
            ),
        ),
        spacing="3",
        width="100%",
        padding="1em",
    )
