"""Sidebar navigation state mixin."""

import reflex as rx

STEPS = ("load", "connections", "rules", "improve", "evaluate", "save")

EVALUATE_SUB_STEPS = (
    "upload", "span_tree", "session", "conversation", "entities", "rule_graph", "registry"
)


class NavigationMixin(rx.State, mixin=True):
    current_step: str = "load"
    evaluate_sub_step: str = "upload"

    def set_step(self, step: str):
        if step in STEPS:
            self.current_step = step

    def set_evaluate_sub_step(self, sub: str):
        if sub in EVALUATE_SUB_STEPS:
            self.evaluate_sub_step = sub
            self.current_step = "evaluate"

    @rx.var(cache=True)
    def has_transcript(self) -> bool:
        return bool(getattr(self, "transcript", None))

    @rx.var(cache=True)
    def has_preview(self) -> bool:
        return getattr(self, "preview_total_spans", 0) > 0
