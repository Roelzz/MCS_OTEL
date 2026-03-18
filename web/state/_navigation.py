"""Sidebar navigation state mixin."""

import reflex as rx

STEPS = ("load", "connections", "rules", "improve", "evaluate", "save")


class NavigationMixin(rx.State, mixin=True):
    current_step: str = "load"

    def set_step(self, step: str):
        if step in STEPS:
            self.current_step = step

    @rx.var(cache=True)
    def has_transcript(self) -> bool:
        return bool(getattr(self, "transcript", None))
