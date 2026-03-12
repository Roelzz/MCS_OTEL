"""Improvement dashboard state mixin."""

import asyncio
from pathlib import Path

import reflex as rx

from improve import (
    Finding,
    apply_to_source_files,
    finding_to_dict,
    generate_code_changes,
    improvement_run_to_dict,
    run_improvement_loop,
)


class ImproveMixin(rx.State, mixin=True):
    improve_input_dir: str = ""
    improve_max_iterations: int = 5
    improve_min_files: int = 3
    improve_running: bool = False
    improve_progress: str = ""
    iterations: list[dict] = []
    pending_review: list[dict] = []
    code_export: dict[str, str] = {}

    def set_improve_input_dir(self, value: str):
        self.improve_input_dir = value

    def set_improve_max_iterations(self, value: str):
        try:
            self.improve_max_iterations = int(value)
        except (ValueError, TypeError):
            pass

    def set_improve_min_files(self, value: str):
        try:
            self.improve_min_files = int(value)
        except (ValueError, TypeError):
            pass

    @rx.var
    def coverage_trend(self) -> list[dict]:
        """Chart data: [{iteration, coverage, fill_rate}]."""
        return [
            {
                "iteration": i + 1,
                "coverage": it.get("avg_coverage", 0),
                "fill_rate": round(it.get("avg_fill_rate", 0) * 100, 1),
            }
            for i, it in enumerate(self.iterations)
        ]

    @rx.var
    def code_export_list(self) -> list[dict]:
        """Convert code_export dict to list for rx.foreach."""
        return [{"file": k, "code": v} for k, v in self.code_export.items()]

    @rx.var
    def has_pending(self) -> bool:
        return len(self.pending_review) > 0

    @rx.var
    def total_improvements(self) -> int:
        return sum(it.get("auto_applied_count", 0) for it in self.iterations)

    async def start_improvement(self):
        """Run improvement loop in background."""
        if not self.improve_input_dir:
            self.improve_progress = "Please set input directory"
            return

        input_path = Path(self.improve_input_dir)
        if not input_path.exists():
            self.improve_progress = f"Directory not found: {self.improve_input_dir}"
            return

        self.improve_running = True
        self.improve_progress = "Starting improvement loop..."
        self.iterations = []
        self.pending_review = []
        self.code_export = {}
        yield

        try:
            runs = await asyncio.to_thread(
                run_improvement_loop,
                input_dir=input_path,
                max_iterations=self.improve_max_iterations,
                min_file_count=self.improve_min_files,
                output_dir=Path("improve_runs"),
            )

            self.iterations = [improvement_run_to_dict(r) for r in runs]

            # Collect all needs-review findings
            all_review: list[dict] = []
            all_applied: list[Finding] = []
            for run in runs:
                for f in run.needs_review:
                    all_review.append(finding_to_dict(f))
                all_applied.extend(run.auto_applied)

            self.pending_review = all_review

            # Generate code export
            review_findings = []
            for run in runs:
                review_findings.extend(run.needs_review)

            code_changes = generate_code_changes(all_applied, review_findings)
            self.code_export = {k: "\n".join(v) for k, v in code_changes.items()}

            if runs:
                final = runs[-1]
                self.improve_progress = (
                    f"Done — {len(runs)} iterations, "
                    f"{final.avg_coverage:.1f}% coverage, "
                    f"{final.avg_fill_rate:.1%} fill rate"
                )
            else:
                self.improve_progress = "No iterations completed"

        except Exception as e:
            self.improve_progress = f"Error: {e}"
        finally:
            self.improve_running = False

    def accept_finding(self, index: int):
        """Accept a needs-review finding (move to code export)."""
        if 0 <= index < len(self.pending_review):
            finding = self.pending_review.pop(index)
            # Add to code export
            snippet = finding.get("code_snippet", "")
            if snippet:
                vt = finding.get("value_type", "unknown")
                cat = finding.get("category", "")
                if cat == "new_type" or cat == "new_enrichment":
                    key = "parsers.py"
                elif cat == "new_attribute":
                    key = "converter.py"
                else:
                    key = "converter.py"

                existing = self.code_export.get(key, "")
                self.code_export = {
                    **self.code_export,
                    key: (existing + "\n" + snippet).strip(),
                }

    def reject_finding(self, index: int):
        """Reject a needs-review finding."""
        if 0 <= index < len(self.pending_review):
            self.pending_review.pop(index)

    def apply_to_source(self):
        """Write accepted code changes to actual source files."""
        if not self.code_export:
            self.improve_progress = "No code changes to apply"
            return

        code_changes = {k: v.split("\n") for k, v in self.code_export.items()}
        results = apply_to_source_files(code_changes)

        success = sum(1 for v in results.values() if v)
        total = len(results)
        self.improve_progress = f"Applied to {success}/{total} files"
