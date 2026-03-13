"""Improvement dashboard state mixin."""

import asyncio
import importlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import reflex as rx
from loguru import logger

import improve as improve_mod


class ImproveMixin(rx.State, mixin=True):
    improve_input_dir: str = ""
    improve_max_iterations: int = 5
    improve_min_files: int = 3
    improve_running: bool = False
    improve_progress: str = ""
    iterations: list[dict] = []
    pending_review: list[dict] = []
    code_export: dict[str, str] = {}
    # Original snippet lists for apply — preserves multi-line snippet boundaries
    _code_snippets: dict[str, list[str]] = {}

    # Workflow step tracking
    improve_step: str = "configure"
    apply_results: dict[str, bool] = {}
    apply_diff: str = ""
    pre_verify_coverage: float = 0.0
    pre_verify_fill_rate: float = 0.0

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
    def step_index(self) -> int:
        return {
            "configure": 0,
            "running": 1,
            "review": 2,
            "previewing": 2,
            "applied": 3,
            "verified": 4,
        }.get(self.improve_step, 0)

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

    @rx.var
    def auto_applied_total(self) -> int:
        return sum(it.get("auto_applied_count", 0) for it in self.iterations)

    @rx.var
    def review_total(self) -> int:
        return sum(it.get("needs_review_count", 0) for it in self.iterations)

    @rx.var
    def final_coverage(self) -> float:
        if not self.iterations:
            return 0.0
        return self.iterations[-1].get("avg_coverage", 0.0)

    @rx.var
    def final_fill_rate(self) -> float:
        if not self.iterations:
            return 0.0
        return round(self.iterations[-1].get("avg_fill_rate", 0.0) * 100, 1)

    @rx.var
    def iteration_count(self) -> int:
        return len(self.iterations)

    @rx.var
    def files_analyzed(self) -> int:
        if not self.iterations:
            return 0
        return self.iterations[-1].get("file_count", 0)

    @rx.var
    def apply_results_list(self) -> list[dict]:
        return [
            {"file": k, "success": v} for k, v in self.apply_results.items()
        ]

    @rx.var
    def coverage_delta(self) -> float:
        if self.improve_step != "verified":
            return 0.0
        return round(self.final_coverage - self.pre_verify_coverage, 1)

    @rx.var
    def fill_rate_delta(self) -> float:
        if self.improve_step != "verified":
            return 0.0
        return round(self.final_fill_rate - self.pre_verify_fill_rate, 1)

    def _reload_improve(self):
        """Reload parsers, converter, and improve modules to pick up source file changes."""
        import parsers
        import converter

        importlib.reload(parsers)
        importlib.reload(converter)

        global improve_mod
        improve_mod = importlib.reload(improve_mod)

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
        self.improve_step = "running"
        self.improve_progress = "Starting improvement loop..."
        self.iterations = []
        self.pending_review = []
        self.code_export = {}
        self._code_snippets = {}
        yield

        try:
            runs = await asyncio.to_thread(
                improve_mod.run_improvement_loop,
                input_dir=input_path,
                max_iterations=self.improve_max_iterations,
                min_file_count=self.improve_min_files,
                output_dir=Path("improve_runs"),
            )

            self.iterations = [improve_mod.improvement_run_to_dict(r) for r in runs]

            # Collect all needs-review findings with unique IDs
            all_review: list[dict] = []
            all_applied: list[improve_mod.Finding] = []
            finding_id = 0
            for run in runs:
                for f in run.needs_review:
                    d = improve_mod.finding_to_dict(f)
                    d["id"] = finding_id
                    finding_id += 1
                    all_review.append(d)
                all_applied.extend(run.auto_applied)

            self.pending_review = all_review

            # Generate code export — keep snippet list for apply, flat string for display
            review_findings = []
            for run in runs:
                review_findings.extend(run.needs_review)

            code_changes = improve_mod.generate_code_changes(all_applied, review_findings)
            self._code_snippets = code_changes
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

            self.improve_step = "review"

        except Exception as e:
            self.improve_progress = f"Error: {e}"
            self.improve_step = "configure"
        finally:
            self.improve_running = False

    def accept_finding(self, finding_id: int):
        """Accept a needs-review finding (move to code export)."""
        idx = next(
            (i for i, f in enumerate(self.pending_review) if f.get("id") == finding_id),
            -1,
        )
        if idx < 0:
            return
        finding = self.pending_review.pop(idx)
        snippet = finding.get("code_snippet", "")
        if snippet:
            cat = finding.get("category", "")
            if cat in ("new_type", "new_enrichment"):
                key = "parsers.py"
            else:
                key = "converter.py"

            # Update display string
            existing = self.code_export.get(key, "")
            self.code_export = {
                **self.code_export,
                key: (existing + "\n" + snippet).strip(),
            }
            # Update snippet list for apply
            snippets = self._code_snippets.get(key, [])
            snippets.append(snippet)
            self._code_snippets = {**self._code_snippets, key: snippets}

    def reject_finding(self, finding_id: int):
        """Reject a needs-review finding."""
        idx = next(
            (i for i, f in enumerate(self.pending_review) if f.get("id") == finding_id),
            -1,
        )
        if idx >= 0:
            self.pending_review.pop(idx)

    def preview_apply(self):
        """Dry-run: apply changes to temp copies and generate a diff preview."""
        if not self._code_snippets:
            self.improve_progress = "No code changes to preview"
            return

        source_files = ["parsers.py", "converter.py", "otel_registry.py"]
        tmpdir = None
        try:
            tmpdir = tempfile.mkdtemp(prefix="improve_preview_")
            tmp = Path(tmpdir)

            # Copy source files to temp dir
            for fname in source_files:
                src = Path(fname)
                if src.exists():
                    shutil.copy2(src, tmp / fname)

            # Apply changes to the temp copies
            improve_mod.apply_to_source_files(self._code_snippets, base_dir=tmp)

            # Generate unified diff between originals and modified copies
            diff_parts: list[str] = []
            for fname in source_files:
                original = Path(fname)
                modified = tmp / fname
                if not original.exists() or not modified.exists():
                    continue
                result = subprocess.run(
                    ["diff", "-u", "--label", f"a/{fname}", "--label", f"b/{fname}",
                     str(original), str(modified)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.stdout:
                    diff_parts.append(result.stdout)

            self.apply_diff = "\n".join(diff_parts) if diff_parts else "No changes detected."
            self.improve_step = "previewing"

        except Exception as e:
            logger.error("Failed to generate preview diff: {}", e)
            self.apply_diff = f"Error generating preview: {e}"
            self.improve_step = "previewing"
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def cancel_preview(self):
        """Go back to review step from preview."""
        self.apply_diff = ""
        self.improve_step = "review"

    def confirm_apply(self):
        """Actually apply changes to source files after previewing."""
        if not self._code_snippets:
            self.improve_progress = "No code changes to apply"
            return

        results = improve_mod.apply_to_source_files(self._code_snippets)

        self.apply_results = {k: v for k, v in results.items()}

        success = sum(1 for v in results.values() if v)
        total = len(results)
        self.improve_progress = f"Applied to {success}/{total} files"
        self.improve_step = "applied"

        # Reload so next run_improvement_loop picks up the updated source files
        if success > 0:
            self._reload_improve()

    async def rerun_verification(self):
        """Store current metrics and re-run to verify improvements."""
        self.pre_verify_coverage = self.final_coverage
        self.pre_verify_fill_rate = self.final_fill_rate
        yield
        async for update in self.start_improvement():
            yield update
        self.improve_step = "verified"

    def reset_improvement(self):
        """Reset back to configure step for a new run."""
        self.improve_step = "configure"
        self.improve_running = False
        self.improve_progress = ""
        self.iterations = []
        self.pending_review = []
        self.code_export = {}
        self._code_snippets = {}
        self.apply_results = {}
        self.apply_diff = ""
        self.pre_verify_coverage = 0.0
        self.pre_verify_fill_rate = 0.0
