"""Improvement dashboard component — visual reporting for the mapper improvement loop."""

import json

import reflex as rx

from web.state import State

STEPS = ["Configure", "Analyze", "Review & Approve", "Apply", "Verify"]


def _step_indicator() -> rx.Component:
    """Horizontal step indicator bar."""

    def _step_circle(label: str, index: int) -> rx.Component:
        active = State.step_index >= index
        return rx.hstack(
            rx.cond(
                active,
                rx.box(
                    rx.text(str(index + 1), size="1", weight="bold", color="white"),
                    width="24px",
                    height="24px",
                    border_radius="50%",
                    background="var(--green-9)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
                rx.box(
                    rx.text(str(index + 1), size="1", weight="bold", color="var(--gray-8)"),
                    width="24px",
                    height="24px",
                    border_radius="50%",
                    background="var(--gray-3)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
            ),
            rx.cond(
                active,
                rx.text(label, size="1", weight="medium"),
                rx.text(label, size="1", color="var(--gray-8)"),
            ),
            spacing="1",
            align="center",
        )

    def _separator(index: int) -> rx.Component:
        return rx.cond(
            State.step_index >= index,
            rx.box(height="2px", flex="1", background="var(--green-9)"),
            rx.box(height="2px", flex="1", background="var(--gray-4)"),
        )

    return rx.card(
        rx.hstack(
            _step_circle("Configure", 0),
            _separator(1),
            _step_circle("Analyze", 1),
            _separator(2),
            _step_circle("Review", 2),
            _separator(3),
            _step_circle("Apply", 3),
            _separator(4),
            _step_circle("Verify", 4),
            width="100%",
            align="center",
            spacing="2",
        ),
        width="100%",
    )


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
                    rx.tooltip(
                        rx.text("Max iterations", size="1", weight="medium"),
                        content="Number of analyze-fix-reanalyze cycles. Stops early if no more improvements found.",
                    ),
                    rx.input(
                        value=State.improve_max_iterations.to(str),
                        on_change=State.set_improve_max_iterations,
                        width="80px",
                    ),
                ),
                rx.box(
                    rx.tooltip(
                        rx.text("Min conversations", size="1", weight="medium"),
                        content="A new event type must appear in at least this many conversations to be auto-fixed. Lower = more aggressive, higher = more conservative.",
                    ),
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


def _run_summary() -> rx.Component:
    """Summary card shown after improvement run completes."""
    return rx.card(
        rx.vstack(
            rx.heading(
                rx.text.span("Improvement Complete — "),
                rx.text.span(State.iteration_count.to(str)),
                rx.text.span(" iterations"),
                size="4",
            ),
            rx.hstack(
                rx.badge(
                    rx.text(State.files_analyzed.to(str)),
                    rx.text(" files analyzed"),
                    color_scheme="blue",
                    size="2",
                ),
                rx.badge(
                    rx.text(State.final_coverage.to(str)),
                    rx.text("% coverage"),
                    color_scheme="green",
                    size="2",
                ),
                rx.badge(
                    rx.text(State.final_fill_rate.to(str)),
                    rx.text("% fill rate"),
                    color_scheme="blue",
                    size="2",
                ),
                spacing="2",
                wrap="wrap",
            ),
            rx.hstack(
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("check-circle", size=16, color="var(--green-9)"),
                            rx.text("Auto-Applied", weight="bold", size="2"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            State.auto_applied_total.to(str),
                            size="5",
                            weight="bold",
                            color="var(--green-11)",
                        ),
                        rx.text(
                            "Changes automatically applied to in-memory mapping",
                            size="1",
                            color_scheme="gray",
                        ),
                        spacing="2",
                    ),
                    flex="1",
                    style={"border": "1px solid var(--green-6)"},
                ),
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("alert-circle", size=16, color="var(--orange-9)"),
                            rx.text("Needs Review", weight="bold", size="2"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            State.review_total.to(str),
                            size="5",
                            weight="bold",
                            color="var(--orange-11)",
                        ),
                        rx.text(
                            "Changes require your approval",
                            size="1",
                            color_scheme="gray",
                        ),
                        spacing="2",
                    ),
                    flex="1",
                    style={"border": "1px solid var(--orange-6)"},
                ),
                width="100%",
                spacing="3",
            ),
            rx.callout(
                "Review pending items below, accept or reject each, then apply to source files. Re-run to verify improvements.",
                icon="info",
                size="1",
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
            rx.hstack(
                rx.heading("Pending Review", size="3"),
                rx.badge(
                    State.pending_review.length().to(str),
                    color_scheme="orange",
                    size="1",
                ),
                spacing="2",
                align="center",
            ),
            rx.text(
                "Accept or reject each finding. Accepted items are added to the code export.",
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
    """Single review item with accept/reject buttons."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(finding["category"].to(str), color_scheme="purple", size="1"),
                rx.text(finding["value_type"].to(str), weight="bold", size="2"),
                rx.text(finding["property_name"].to(str), size="2", color_scheme="gray"),
                rx.spacer(),
                rx.button(
                    rx.icon("check", size=14),
                    "Accept",
                    size="1",
                    variant="outline",
                    color_scheme="green",
                    on_click=State.accept_finding(finding["id"]),
                ),
                rx.button(
                    rx.icon("x", size=14),
                    "Reject",
                    size="1",
                    variant="outline",
                    color_scheme="red",
                    on_click=State.reject_finding(finding["id"]),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.code_block(
                finding["suggested_config_display"],
                language="json",
            ),
            spacing="2",
        ),
        width="100%",
    )



def _apply_section() -> rx.Component:
    """Guided apply card shown during review step — generates a preview diff first."""
    return rx.card(
        rx.vstack(
            rx.heading("Apply Changes to Source Files", size="3"),
            rx.text(
                "Preview the exact changes to parsers.py, converter.py, and otel_registry.py before applying.",
                size="2",
                color_scheme="gray",
            ),
            rx.button(
                rx.icon("eye", size=14),
                "Preview Diff",
                on_click=State.preview_apply,
                color_scheme="blue",
                size="2",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def _diff_preview() -> rx.Component:
    """Shows the diff preview with confirm/cancel buttons."""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("git-compare", size=20, color="var(--blue-9)"),
                    rx.heading("Preview: Changes to Source Files", size="3"),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    "Review the diff below. These changes will be written to your source files.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.code_block(
                    State.apply_diff,
                    language="diff",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("check", size=14),
                        "Confirm & Apply",
                        on_click=State.confirm_apply,
                        color_scheme="green",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("arrow-left", size=14),
                        "Back to Review",
                        on_click=State.cancel_preview,
                        variant="outline",
                        size="2",
                    ),
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def _post_apply() -> rx.Component:
    """Post-apply section with per-file results and re-run option."""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("check-circle", size=20, color="var(--green-9)"),
                    rx.heading("Changes Applied", size="3"),
                    spacing="2",
                    align="center",
                ),
                rx.foreach(
                    State.apply_results_list,
                    _apply_result_item,
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        rx.card(
            rx.vstack(
                rx.text(
                    "Run the improvement loop again to confirm coverage improved and no new gaps appeared.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("refresh-cw", size=14),
                        "Re-run to Verify",
                        on_click=State.rerun_verification,
                        color_scheme="green",
                        size="2",
                    ),
                    rx.button(
                        "Start Over",
                        on_click=State.reset_improvement,
                        variant="outline",
                        size="2",
                    ),
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def _apply_result_item(item: dict) -> rx.Component:
    """Single file apply result."""
    return rx.hstack(
        rx.cond(
            item["success"],
            rx.icon("check", size=14, color="var(--green-9)"),
            rx.icon("x", size=14, color="var(--red-9)"),
        ),
        rx.text(item["file"].to(str), size="2"),
        rx.cond(
            item["success"],
            rx.badge("success", color_scheme="green", size="1"),
            rx.badge("failed", color_scheme="red", size="1"),
        ),
        spacing="2",
        align="center",
    )


def _delta_badge(delta: rx.Var, label: str) -> rx.Component:
    """Badge showing positive/negative delta."""
    return rx.cond(
        delta > 0,
        rx.badge(
            rx.text.span("+"),
            delta.to(str),
            rx.text.span(label),
            color_scheme="green",
            size="2",
        ),
        rx.cond(
            delta < 0,
            rx.badge(
                delta.to(str),
                rx.text.span(label),
                color_scheme="red",
                size="2",
            ),
            rx.badge(
                rx.text.span("0"),
                rx.text.span(label),
                color_scheme="orange",
                size="2",
            ),
        ),
    )


def _verification_results() -> rx.Component:
    """Before/after comparison after verification re-run."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("bar-chart-3", size=20, color="var(--green-9)"),
                rx.heading("Verification Results", size="3"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.card(
                    rx.vstack(
                        rx.text("Coverage", size="1", color_scheme="gray"),
                        rx.hstack(
                            rx.text(
                                State.pre_verify_coverage.to(str),
                                size="2",
                                color="var(--gray-9)",
                            ),
                            rx.text(" → ", size="2"),
                            rx.text(
                                State.final_coverage.to(str),
                                size="2",
                                weight="bold",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        _delta_badge(State.coverage_delta, "%"),
                        spacing="2",
                    ),
                    flex="1",
                ),
                rx.card(
                    rx.vstack(
                        rx.text("Fill Rate", size="1", color_scheme="gray"),
                        rx.hstack(
                            rx.text(
                                State.pre_verify_fill_rate.to(str),
                                size="2",
                                color="var(--gray-9)",
                            ),
                            rx.text(" → ", size="2"),
                            rx.text(
                                State.final_fill_rate.to(str),
                                size="2",
                                weight="bold",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        _delta_badge(State.fill_rate_delta, "%"),
                        spacing="2",
                    ),
                    flex="1",
                ),
                width="100%",
                spacing="3",
            ),
            rx.separator(),
            rx.button(
                "Start Over",
                on_click=State.reset_improvement,
                variant="outline",
                size="2",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def improve_dashboard() -> rx.Component:
    """Full improvement dashboard page component."""
    return rx.vstack(
        _controls(),
        _step_indicator(),
        # Review step: full analysis results
        rx.cond(
            State.improve_step == "review",
            rx.vstack(
                _run_summary(),
                _iteration_timeline(),
                _coverage_chart(),
                _pending_review(),
                _apply_section(),
                spacing="4",
                width="100%",
            ),
        ),
        # Previewing step: diff preview with confirm/cancel
        rx.cond(
            State.improve_step == "previewing",
            rx.vstack(
                _run_summary(),
                _diff_preview(),
                spacing="4",
                width="100%",
            ),
        ),
        # Applied step: results + post-apply actions
        rx.cond(
            State.improve_step == "applied",
            rx.vstack(
                _run_summary(),
                _iteration_timeline(),
                _coverage_chart(),
                _pending_review(),
                _post_apply(),
                spacing="4",
                width="100%",
            ),
        ),
        # Verified step: before/after comparison
        rx.cond(
            State.improve_step == "verified",
            rx.vstack(
                _verification_results(),
                _iteration_timeline(),
                _coverage_chart(),
                spacing="4",
                width="100%",
            ),
        ),
        spacing="4",
        width="100%",
    )


