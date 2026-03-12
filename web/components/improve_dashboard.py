"""Improvement dashboard component — visual reporting for the mapper improvement loop."""

import reflex as rx

from web.state import State


def _controls() -> rx.Component:
    """Input directory, settings, and start button."""
    return rx.card(
        rx.vstack(
            rx.heading("Improvement Engine", size="4"),
            rx.text(
                "Analyze real transcripts to find and fix mapping gaps automatically.",
                color_scheme="gray",
                size="2",
            ),
            rx.hstack(
                rx.box(
                    rx.text("Transcript directory", size="1", weight="medium"),
                    rx.input(
                        placeholder="/path/to/transcripts/",
                        value=State.improve_input_dir,
                        on_change=State.set_improve_input_dir,
                        width="100%",
                    ),
                    flex="1",
                ),
                rx.box(
                    rx.text("Max iterations", size="1", weight="medium"),
                    rx.input(
                        value=State.improve_max_iterations.to(str),
                        on_change=State.set_improve_max_iterations,
                        width="80px",
                    ),
                ),
                rx.box(
                    rx.text("Min files", size="1", weight="medium"),
                    rx.input(
                        value=State.improve_min_files.to(str),
                        on_change=State.set_improve_min_files,
                        width="80px",
                    ),
                ),
                width="100%",
                spacing="3",
                align="end",
            ),
            rx.hstack(
                rx.button(
                    rx.cond(
                        State.improve_running,
                        rx.hstack(rx.spinner(size="1"), rx.text("Running...")),
                        rx.text("Start Improvement"),
                    ),
                    on_click=State.start_improvement,
                    disabled=State.improve_running,
                    color_scheme="green",
                    size="2",
                ),
                rx.text(State.improve_progress, size="2", color_scheme="gray"),
                spacing="3",
                align="center",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def _iteration_timeline() -> rx.Component:
    """Cards showing each iteration's metrics."""
    return rx.cond(
        State.iterations.length() > 0,
        rx.vstack(
            rx.heading("Iteration Timeline", size="3"),
            rx.hstack(
                rx.foreach(
                    State.iterations,
                    _iteration_card,
                ),
                spacing="3",
                overflow_x="auto",
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
    )


def _iteration_card(iteration: dict) -> rx.Component:
    """Single iteration card."""
    return rx.card(
        rx.vstack(
            rx.text(iteration["run_id"].to(str), size="1", weight="bold", trim="both"),
            rx.hstack(
                rx.vstack(
                    rx.text("Coverage", size="1", color_scheme="gray"),
                    rx.text(
                        iteration["avg_coverage"].to(str),
                        size="3",
                        weight="bold",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Fill Rate", size="1", color_scheme="gray"),
                    rx.text(
                        iteration["avg_fill_rate"].to(str),
                        size="3",
                        weight="bold",
                    ),
                    spacing="1",
                ),
                spacing="4",
            ),
            rx.hstack(
                rx.badge(
                    iteration["auto_applied_count"].to(str),
                    color_scheme="green",
                    size="1",
                ),
                rx.text("auto-fixed", size="1"),
                rx.badge(
                    iteration["needs_review_count"].to(str),
                    color_scheme="orange",
                    size="1",
                ),
                rx.text("review", size="1"),
                spacing="1",
            ),
            spacing="2",
        ),
        min_width="180px",
    )


def _coverage_chart() -> rx.Component:
    """Line chart showing coverage trend across iterations."""
    return rx.cond(
        State.coverage_trend.length() > 1,
        rx.vstack(
            rx.heading("Coverage Trend", size="3"),
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="coverage",
                    stroke="#22c55e",
                    name="Coverage %",
                ),
                rx.recharts.line(
                    data_key="fill_rate",
                    stroke="#3b82f6",
                    name="Fill Rate %",
                ),
                rx.recharts.x_axis(data_key="iteration"),
                rx.recharts.y_axis(),
                rx.recharts.legend(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                data=State.coverage_trend,
                width="100%",
                height=250,
            ),
            spacing="2",
            width="100%",
        ),
    )


def _pending_review() -> rx.Component:
    """List of findings needing human decision."""
    return rx.cond(
        State.has_pending,
        rx.vstack(
            rx.heading("Pending Review", size="3"),
            rx.text(
                "These findings need human review before applying.",
                size="2",
                color_scheme="gray",
            ),
            rx.foreach(
                State.pending_review,
                _review_item,
            ),
            spacing="3",
            width="100%",
        ),
    )


def _review_item(finding: dict) -> rx.Component:
    """Single review item."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(finding["category"].to(str), color_scheme="purple", size="1"),
                rx.text(finding["value_type"].to(str), weight="bold", size="2"),
                rx.text(finding["property_name"].to(str), size="2", color_scheme="gray"),
                spacing="2",
                align="center",
            ),
            rx.code_block(
                finding["code_snippet"].to(str),
                language="python",
            ),
            spacing="2",
        ),
        width="100%",
    )


def _code_export() -> rx.Component:
    """Collapsible sections per target file showing generated code."""
    return rx.cond(
        State.code_export_list.length() > 0,
        rx.vstack(
            rx.heading("Code Export", size="3"),
            rx.text(
                "Generated code changes ready to apply to source files.",
                size="2",
                color_scheme="gray",
            ),
            rx.foreach(
                State.code_export_list,
                _code_section,
            ),
            rx.button(
                "Apply to Source Files",
                on_click=State.apply_to_source,
                color_scheme="red",
                size="2",
            ),
            spacing="3",
            width="100%",
        ),
    )


def _code_section(item: dict) -> rx.Component:
    """Single code section for a file."""
    return rx.box(
        rx.text(item["file"].to(str), weight="bold", size="2"),
        rx.code_block(item["code"].to(str), language="python"),
        width="100%",
        padding_bottom="1em",
    )


def improve_dashboard() -> rx.Component:
    """Full improvement dashboard page component."""
    return rx.vstack(
        _controls(),
        _iteration_timeline(),
        _coverage_chart(),
        _pending_review(),
        _code_export(),
        spacing="4",
        width="100%",
    )


def improve_page() -> rx.Component:
    """Full page layout for /improve route."""
    from web.components.navbar import navbar

    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                improve_dashboard(),
                spacing="4",
                width="100%",
                max_width="1200px",
                margin_x="auto",
                padding="1em",
            ),
            width="100%",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
    )
