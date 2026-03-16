"""Self-learning mapper improvement engine.

Analyzes real MCS conversation transcripts to iteratively improve
the mapping config (config/default_mapping.json) until coverage is maximized.

Loop: Analyze all transcripts -> measure coverage -> find gaps ->
      auto-fix obvious gaps -> ask human on ambiguous ones -> repeat.

Output: proposed_mapping.json for review. Use 'approve' command to apply.
"""

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer

from analyze_transcripts import (
    FileStats,
    _suggest_otel_op,
    aggregate_stats,
    build_mapping_gap_analysis,
    discover_files,
    iter_transcripts,
    suggest_attribute_mappings_json,
    suggest_mapping_rule_json,
)
from config_loader import load_default_mapping, DEFAULT_MAPPING_PATH
from converter import apply_mapping, to_otlp_json
from log import logger
from models import (
    AttributeMapping,
    EventMetadata,
    MappingSpecification,
    OTELSpanKind,
    SpanMappingRule,
)
from parsers import extract_entities, parse_transcript
from utils import to_snake_case

app = typer.Typer(help="Self-learning mapper improvement engine.")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileAnalysis:
    path: str
    success: bool
    error: str = ""
    activity_count: int = 0
    entity_count: int = 0
    span_count: int = 0
    value_types: dict[str, int] = field(default_factory=dict)
    unknown_types: dict[str, dict] = field(default_factory=dict)
    unmapped_props: dict[str, set[str]] = field(default_factory=dict)
    empty_spans: list[str] = field(default_factory=list)
    attribute_fill_rate: float = 0.0


@dataclass
class Finding:
    category: str  # "new_type" | "new_attribute" | "new_enrichment"
    auto_fixable: bool
    value_type: str
    property_name: str = ""
    file_count: int = 0
    sample_value: dict = field(default_factory=dict)
    suggested_config: dict = field(default_factory=dict)


@dataclass
class ImprovementRun:
    run_id: str
    timestamp: str
    input_dir: str
    file_count: int
    success_count: int
    failure_count: int
    avg_coverage: float
    avg_fill_rate: float
    findings: list[Finding] = field(default_factory=list)
    auto_applied: list[Finding] = field(default_factory=list)
    needs_review: list[Finding] = field(default_factory=list)
    delta_coverage: float = 0.0
    delta_fill_rate: float = 0.0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def analyze_corpus(
    input_dir: Path,
    spec: MappingSpecification,
    tracked_types: set[str],
) -> tuple[list[FileAnalysis], dict[str, int], dict[str, dict], dict[str, set[str]]]:
    """Process all transcripts, return per-file results + aggregated gaps.

    Returns:
        file_analyses: per-file results
        unknown_types_agg: vt -> file_count (types not in tracked_types)
        unknown_samples: vt -> sample_value dict
        unmapped_props_agg: vt -> {property_names} (props without AttributeMapping)
    """
    files = discover_files([input_dir])
    if not files:
        logger.warning("No transcript files found in {}", input_dir)
        return [], {}, {}, {}

    # Build lookup: value_type -> set of mapped mcs_property
    mapped_by_vt: dict[str, set[str]] = {}
    for rule in spec.rules:
        if rule.mcs_value_type:
            mapped_by_vt[rule.mcs_value_type] = {
                am.mcs_property for am in rule.attribute_mappings if am.mcs_property
            }

    file_analyses: list[FileAnalysis] = []
    unknown_types_count: dict[str, int] = {}
    unknown_samples: dict[str, dict] = {}
    unmapped_props_agg: dict[str, set[str]] = {}

    for label, content in iter_transcripts(files):
        fa = _analyze_single_content(label, content, spec, tracked_types, mapped_by_vt)
        file_analyses.append(fa)

        if not fa.success:
            continue

        # Aggregate unknown types
        for vt, sample in fa.unknown_types.items():
            unknown_types_count[vt] = unknown_types_count.get(vt, 0) + 1
            if vt not in unknown_samples:
                unknown_samples[vt] = sample

        # Aggregate unmapped props
        for vt, props in fa.unmapped_props.items():
            if vt not in unmapped_props_agg:
                unmapped_props_agg[vt] = set()
            unmapped_props_agg[vt].update(props)

    return file_analyses, unknown_types_count, unknown_samples, unmapped_props_agg


def _analyze_single_content(
    label: str,
    content: str,
    spec: MappingSpecification,
    tracked_types: set[str],
    mapped_by_vt: dict[str, set[str]],
) -> FileAnalysis:
    """Analyze a single transcript content string through the full pipeline."""
    fa = FileAnalysis(path=label, success=False)

    try:
        transcript = parse_transcript(content)
        entities = extract_entities(transcript, spec=spec)
    except Exception as e:
        fa.error = str(e)
        logger.debug("Failed to parse {}: {}", label, e)
        return fa

    fa.success = True
    fa.activity_count = len(transcript.activities)
    fa.entity_count = len(entities)

    for ent in entities:
        vt = ent.value_type
        if not vt:
            continue
        fa.value_types[vt] = fa.value_types.get(vt, 0) + 1

        if vt not in tracked_types and ent.entity_type == "trace_event":
            if vt not in fa.unknown_types:
                fa.unknown_types[vt] = ent.properties

        if vt in tracked_types and vt in mapped_by_vt:
            mapped_props = mapped_by_vt[vt]
            skip_props = {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"}
            available = set(ent.properties.keys()) - skip_props - {"timestamp"}
            unmapped = available - mapped_props
            if unmapped:
                if vt not in fa.unmapped_props:
                    fa.unmapped_props[vt] = set()
                fa.unmapped_props[vt].update(unmapped)

    try:
        trace = apply_mapping(entities, spec)
        fa.span_count = trace.total_spans + trace.total_events

        total_attrs, filled_attrs = _count_attributes_recursive(trace.root_span)
        fa.attribute_fill_rate = filled_attrs / total_attrs if total_attrs > 0 else 0.0

        _detect_empty_spans(trace.root_span, fa.empty_spans)

    except Exception as e:
        logger.debug("Failed to apply mapping to {}: {}", label, e)
        fa.error = f"mapping: {e}"

    return fa


def _count_attributes_recursive(span) -> tuple[int, int]:
    """Count total and filled attributes across all spans recursively."""
    default_keys = {"gen_ai.operation.name", "gen_ai.system"}
    total = len(span.attributes)
    filled = sum(1 for k, v in span.attributes.items() if k not in default_keys and v)

    for child in span.children:
        ct, cf = _count_attributes_recursive(child)
        total += ct
        filled += cf

    return total, filled



def _detect_empty_spans(span, empty_list: list[str]) -> None:
    """Find spans with only default attributes (gen_ai.operation.name, gen_ai.system)."""
    default_keys = {"gen_ai.operation.name", "gen_ai.system"}
    non_default = {k for k in span.attributes if k not in default_keys}
    if not non_default and span.name != "unknown":
        empty_list.append(span.name)

    for child in span.children:
        _detect_empty_spans(child, empty_list)


def classify_findings(
    unknown_types: dict[str, int],
    unknown_samples: dict[str, dict],
    unmapped_props: dict[str, set[str]],
    min_file_count: int = 3,
) -> list[Finding]:
    """Classify gaps into auto-fixable vs needs-review.

    Auto-fixable (>= min_file_count files):
    - new_type: unknown type -> EventMetadata + SpanMappingRule
    - new_attribute: unmapped property -> AttributeMapping on existing rule

    Needs review:
    - new_enrichment: types with nested structures
    - Any finding in < min_file_count files
    """
    findings: list[Finding] = []

    # New types
    for vt, file_count in unknown_types.items():
        sample = unknown_samples.get(vt, {})
        auto = file_count >= min_file_count

        # Check if sample has nested structures that need enrichment
        has_nested = any(isinstance(v, (dict, list)) for v in sample.values()) if sample else False

        if has_nested:
            category = "new_enrichment"
            auto = False
        else:
            category = "new_type"

        sample_props = set(sample.keys()) if sample else set()
        config = suggest_mapping_rule_json(vt, sample_props)

        findings.append(Finding(
            category=category,
            auto_fixable=auto,
            value_type=vt,
            file_count=file_count,
            sample_value=_safe_sample(sample),
            suggested_config=config,
        ))

    # Unmapped properties on tracked types
    for vt, props in unmapped_props.items():
        for prop in sorted(props):
            findings.append(Finding(
                category="new_attribute",
                auto_fixable=True,
                value_type=vt,
                property_name=prop,
                file_count=0,
                suggested_config={"mcs_property": prop, "otel_attribute": f"copilot_studio.{prop}"},
            ))

    return findings


def _safe_sample(sample: dict) -> dict:
    """Make a sample JSON-safe (truncate large values)."""
    safe: dict = {}
    for k, v in sample.items():
        if isinstance(v, str) and len(v) > 200:
            safe[k] = v[:200] + "..."
        elif isinstance(v, (dict, list)):
            try:
                s = json.dumps(v, default=str)
                if len(s) > 200:
                    safe[k] = f"<{type(v).__name__} len={len(v)}>"
                else:
                    safe[k] = v
            except Exception:
                safe[k] = f"<{type(v).__name__}>"
        else:
            safe[k] = v
    return safe


def apply_auto_fixes(
    findings: list[Finding],
    spec: MappingSpecification,
    tracked_types: set[str],
) -> tuple[MappingSpecification, set[str], list[Finding]]:
    """Apply auto-fixable findings to in-memory mapping spec.

    For new_type: add to tracked_types set, create SpanMappingRule, add to spec.rules
    For new_attribute: find matching rule, add AttributeMapping

    Returns: updated spec, updated tracked_types, list of applied findings
    """
    spec = deepcopy(spec)
    tracked_types = set(tracked_types)
    applied: list[Finding] = []

    # Build rule lookup
    rule_by_vt: dict[str, int] = {}
    for idx, rule in enumerate(spec.rules):
        if rule.mcs_value_type:
            rule_by_vt[rule.mcs_value_type] = idx

    for finding in findings:
        if not finding.auto_fixable:
            continue

        if finding.category == "new_type":
            # Skip if already tracked or already has a rule
            if finding.value_type in tracked_types:
                continue
            if finding.value_type in rule_by_vt:
                continue

            tracked_types.add(finding.value_type)

            # Add EventMetadata so extract_entities picks it up
            spec.event_metadata.append(EventMetadata(
                value_type=finding.value_type,
                tracked=True,
                label=finding.value_type,
                entity_type="trace_event",
            ))

            # Generate a new rule
            rule_id = to_snake_case(finding.value_type)
            new_rule = SpanMappingRule(
                rule_id=rule_id,
                rule_name=finding.value_type,
                mcs_entity_type="trace_event",
                mcs_value_type=finding.value_type,
                otel_operation_name=_suggest_otel_op(finding.value_type),
                otel_span_kind=OTELSpanKind.INTERNAL,
                span_name_template=rule_id.replace("_", "."),
                parent_rule_id="user_turn",
                attribute_mappings=_build_attribute_mappings(finding.sample_value),
            )
            spec.rules.append(new_rule)
            rule_by_vt[finding.value_type] = len(spec.rules) - 1
            applied.append(finding)

        elif finding.category == "new_attribute":
            idx = rule_by_vt.get(finding.value_type)
            if idx is None:
                continue

            rule = spec.rules[idx]
            # Check idempotency — don't add duplicate
            existing = {am.mcs_property for am in rule.attribute_mappings}
            if finding.property_name in existing:
                continue

            rule.attribute_mappings.append(
                AttributeMapping(
                    mcs_property=finding.property_name,
                    otel_attribute=f"copilot_studio.{finding.property_name}",
                )
            )
            applied.append(finding)

    return spec, tracked_types, applied


def _build_attribute_mappings(sample: dict) -> list[AttributeMapping]:
    """Build AttributeMapping list from sample properties."""
    skip = {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"}
    mappings = []
    for prop in sorted(sample.keys()):
        if prop in skip:
            continue
        mappings.append(
            AttributeMapping(
                mcs_property=prop,
                otel_attribute=f"copilot_studio.{prop}",
            )
        )
    return mappings


def compute_coverage(
    file_analyses: list[FileAnalysis],
) -> tuple[float, float]:
    """Compute average coverage % and average attribute fill rate across files."""
    if not file_analyses:
        return 0.0, 0.0

    successful = [fa for fa in file_analyses if fa.success]
    if not successful:
        return 0.0, 0.0

    # Coverage: ratio of entities that produced spans
    total_entities = sum(fa.entity_count for fa in successful)
    total_spans = sum(fa.span_count for fa in successful)
    coverage = (total_spans / total_entities * 100) if total_entities > 0 else 0.0

    # Average fill rate
    fill_rates = [fa.attribute_fill_rate for fa in successful if fa.attribute_fill_rate > 0]
    avg_fill = sum(fill_rates) / len(fill_rates) if fill_rates else 0.0

    return coverage, avg_fill



def generate_spec_changes(
    applied: list[Finding],
    needs_review: list[Finding],
    current_spec: MappingSpecification,
) -> MappingSpecification:
    """Generate an updated MappingSpecification from findings.

    For new_type: add EventMetadata + SpanMappingRule.
    For new_attribute: add AttributeMapping to existing rule.
    Returns: complete updated MappingSpecification.
    """
    spec = deepcopy(current_spec)

    # Build rule lookup
    rule_by_vt: dict[str, int] = {}
    for idx, rule in enumerate(spec.rules):
        if rule.mcs_value_type:
            rule_by_vt[rule.mcs_value_type] = idx

    # Build existing event metadata value_types
    existing_meta_vts = {em.value_type for em in spec.event_metadata}

    for finding in applied + needs_review:
        if finding.category == "new_type":
            vt = finding.value_type
            if vt in rule_by_vt:
                continue

            # Add EventMetadata
            if vt not in existing_meta_vts:
                spec.event_metadata.append(EventMetadata(
                    value_type=vt,
                    tracked=True,
                    label=vt,
                    entity_type="trace_event",
                ))
                existing_meta_vts.add(vt)

            # Add SpanMappingRule
            rule_id = to_snake_case(vt)
            new_rule = SpanMappingRule(
                rule_id=rule_id,
                rule_name=vt,
                mcs_entity_type="trace_event",
                mcs_value_type=vt,
                otel_operation_name=_suggest_otel_op(vt),
                otel_span_kind=OTELSpanKind.INTERNAL,
                span_name_template=rule_id.replace("_", "."),
                parent_rule_id="user_turn",
                attribute_mappings=_build_attribute_mappings(finding.sample_value),
            )
            spec.rules.append(new_rule)
            rule_by_vt[vt] = len(spec.rules) - 1

        elif finding.category == "new_attribute":
            idx = rule_by_vt.get(finding.value_type)
            if idx is None:
                continue
            rule = spec.rules[idx]
            existing = {am.mcs_property for am in rule.attribute_mappings}
            if finding.property_name in existing:
                continue
            rule.attribute_mappings.append(
                AttributeMapping(
                    mcs_property=finding.property_name,
                    otel_attribute=f"copilot_studio.{finding.property_name}",
                )
            )

    return spec


def run_improvement_loop(
    input_dir: Path,
    max_iterations: int = 5,
    min_file_count: int = 3,
    output_dir: Path = Path("improve_runs"),
) -> list[ImprovementRun]:
    """Main loop: analyze -> classify -> auto-fix -> re-analyze -> repeat.

    Stops when:
    - No more auto-fixable findings (converged)
    - Max iterations reached
    - Coverage improvement < 0.1% (diminishing returns)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = load_default_mapping()
    tracked_types = {em.value_type for em in spec.event_metadata if em.tracked}
    runs: list[ImprovementRun] = []
    prev_coverage = 0.0
    prev_fill = 0.0

    for iteration in range(1, max_iterations + 1):
        run_id = f"iter_{iteration}_{uuid4().hex[:8]}"
        logger.info("=== Iteration {} ===", iteration)

        # 1. Analyze
        file_analyses, unknown_types, unknown_samples, unmapped_props = analyze_corpus(
            input_dir, spec, tracked_types
        )

        success_count = sum(1 for fa in file_analyses if fa.success)
        failure_count = sum(1 for fa in file_analyses if not fa.success)
        coverage, fill_rate = compute_coverage(file_analyses)

        logger.info(
            "Files: {} success, {} failed | Coverage: {:.1f}% | Fill rate: {:.1%}",
            success_count, failure_count, coverage, fill_rate,
        )

        # 2. Classify
        findings = classify_findings(unknown_types, unknown_samples, unmapped_props, min_file_count)
        auto_fixable = [f for f in findings if f.auto_fixable]
        needs_review = [f for f in findings if not f.auto_fixable]

        logger.info(
            "Findings: {} auto-fixable, {} need review",
            len(auto_fixable), len(needs_review),
        )

        # 3. Auto-fix
        spec, tracked_types, applied = apply_auto_fixes(findings, spec, tracked_types)

        logger.info("Applied {} auto-fixes", len(applied))

        # Build run record
        run = ImprovementRun(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_dir=str(input_dir),
            file_count=len(file_analyses),
            success_count=success_count,
            failure_count=failure_count,
            avg_coverage=coverage,
            avg_fill_rate=fill_rate,
            findings=findings,
            auto_applied=applied,
            needs_review=needs_review,
            delta_coverage=coverage - prev_coverage,
            delta_fill_rate=fill_rate - prev_fill,
        )
        runs.append(run)

        # Save iteration results
        _save_iteration(output_dir, run)

        # 4. Check convergence
        if not applied:
            logger.info("Converged — no more auto-fixable findings")
            break

        if iteration > 1 and abs(coverage - prev_coverage) < 0.1:
            logger.info("Converged — coverage improvement < 0.1%")
            break

        prev_coverage = coverage
        prev_fill = fill_rate

    # Save proposed spec for review
    spec_path = output_dir / "proposed_mapping.json"
    spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Proposed mapping saved to {} — use 'approve' command to apply", spec_path)

    return runs


def _save_iteration(output_dir: Path, run: ImprovementRun) -> None:
    """Save iteration results to JSON."""
    data = {
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "input_dir": run.input_dir,
        "file_count": run.file_count,
        "success_count": run.success_count,
        "failure_count": run.failure_count,
        "avg_coverage": run.avg_coverage,
        "avg_fill_rate": run.avg_fill_rate,
        "delta_coverage": run.delta_coverage,
        "delta_fill_rate": run.delta_fill_rate,
        "findings_count": len(run.findings),
        "auto_applied_count": len(run.auto_applied),
        "needs_review_count": len(run.needs_review),
        "auto_applied": [
            {"category": f.category, "value_type": f.value_type, "property_name": f.property_name}
            for f in run.auto_applied
        ],
        "needs_review": [
            {
                "category": f.category,
                "value_type": f.value_type,
                "property_name": f.property_name,
                "suggested_config": f.suggested_config,
                "sample_value": f.sample_value,
            }
            for f in run.needs_review
        ],
    }
    path = output_dir / f"{run.run_id}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.debug("Saved iteration to {}", path)

# ---------------------------------------------------------------------------
# Serialization helpers (for web dashboard)
# ---------------------------------------------------------------------------


def improvement_run_to_dict(run: ImprovementRun) -> dict:
    """Convert ImprovementRun to JSON-serializable dict."""
    return {
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "input_dir": run.input_dir,
        "file_count": run.file_count,
        "success_count": run.success_count,
        "failure_count": run.failure_count,
        "avg_coverage": round(run.avg_coverage, 2),
        "avg_fill_rate": round(run.avg_fill_rate, 4),
        "delta_coverage": round(run.delta_coverage, 2),
        "delta_fill_rate": round(run.delta_fill_rate, 4),
        "findings_count": len(run.findings),
        "auto_applied_count": len(run.auto_applied),
        "needs_review_count": len(run.needs_review),
    }


def finding_to_dict(finding: Finding) -> dict:
    """Convert Finding to JSON-serializable dict."""
    return {
        "category": finding.category,
        "auto_fixable": finding.auto_fixable,
        "value_type": finding.value_type,
        "property_name": finding.property_name,
        "file_count": finding.file_count,
        "sample_value": finding.sample_value,
        "suggested_config": finding.suggested_config,
        "suggested_config_display": json.dumps(finding.suggested_config, indent=2, default=str),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def run(
    input_dir: Path = typer.Argument(..., help="Directory containing transcript JSON files"),
    max_iterations: int = typer.Option(5, "--max-iterations", "-n", help="Max improvement iterations"),
    min_files: int = typer.Option(3, "--min-files", help="Min file count for auto-fix threshold"),
    output: Path = typer.Option(Path("improve_runs"), "--output", "-o", help="Output directory for results"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Run the self-learning mapper improvement loop."""
    if verbose:
        logger.remove()
        logger.add(
            sink=lambda msg: print(msg, end=""),
            level="DEBUG",
            format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
        )

    if not input_dir.exists():
        logger.error("Input directory does not exist: {}", input_dir)
        raise typer.Exit(1)

    runs = run_improvement_loop(
        input_dir=input_dir,
        max_iterations=max_iterations,
        min_file_count=min_files,
        output_dir=output,
    )

    # Print summary
    typer.echo(f"\n{'='*60}")
    typer.echo("Improvement Loop Summary")
    typer.echo(f"{'='*60}")

    for i, run_result in enumerate(runs, 1):
        delta_cov = f"+{run_result.delta_coverage:.1f}%" if run_result.delta_coverage > 0 else f"{run_result.delta_coverage:.1f}%"
        typer.echo(
            f"  Iteration {i}: coverage={run_result.avg_coverage:.1f}% ({delta_cov}) | "
            f"fill_rate={run_result.avg_fill_rate:.1%} | "
            f"auto-fixed={len(run_result.auto_applied)} | "
            f"needs-review={len(run_result.needs_review)}"
        )

    if runs:
        final = runs[-1]
        typer.echo(f"\nFinal: {final.avg_coverage:.1f}% coverage, {final.avg_fill_rate:.1%} fill rate")
        typer.echo(f"Results: {output}/")

        if final.needs_review:
            typer.echo(f"\n{len(final.needs_review)} findings need human review — see {output}/proposed_mapping.json")

    typer.echo(f"\nNext: review with 'uv run python improve.py diff' then 'uv run python improve.py approve'")


def _bump_version(version: str) -> str:
    """Bump minor version: 1.1 -> 1.2, 2.0 -> 2.1."""
    parts = version.split(".")
    if len(parts) >= 2:
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError:
            parts.append("1")
        return ".".join(parts)
    return f"{version}.1"


@app.command()
def diff(
    source: Path = typer.Option(Path("improve_runs"), "--source", "-s", help="Directory containing proposed_mapping.json"),
) -> None:
    """Show diff between proposed mapping and current config."""
    proposed_path = source / "proposed_mapping.json"
    if not proposed_path.exists():
        typer.echo(f"No proposed mapping found at {proposed_path}")
        typer.echo("Run the improvement loop first: uv run python improve.py run <input_dir>")
        raise typer.Exit(1)

    current = json.loads(DEFAULT_MAPPING_PATH.read_text(encoding="utf-8"))
    proposed = json.loads(proposed_path.read_text(encoding="utf-8"))

    # Compare key sections
    typer.echo(f"{'='*60}")
    typer.echo(f"Config Diff: {DEFAULT_MAPPING_PATH.name} vs proposed_mapping.json")
    typer.echo(f"{'='*60}")

    current_rules = {r["rule_id"]: r for r in current.get("rules", [])}
    proposed_rules = {r["rule_id"]: r for r in proposed.get("rules", [])}

    new_rules = set(proposed_rules.keys()) - set(current_rules.keys())
    removed_rules = set(current_rules.keys()) - set(proposed_rules.keys())

    current_meta = {em["value_type"]: em for em in current.get("event_metadata", [])}
    proposed_meta = {em["value_type"]: em for em in proposed.get("event_metadata", [])}
    new_meta = set(proposed_meta.keys()) - set(current_meta.keys())

    typer.echo(f"\nVersion: {current.get('version', '?')} → {proposed.get('version', '?')}")
    typer.echo(f"Rules: {len(current_rules)} → {len(proposed_rules)} ({len(new_rules)} new, {len(removed_rules)} removed)")
    typer.echo(f"Event metadata: {len(current_meta)} → {len(proposed_meta)} ({len(new_meta)} new)")

    if new_rules:
        typer.echo(f"\n--- New rules ---")
        for rid in sorted(new_rules):
            rule = proposed_rules[rid]
            typer.echo(f"  + {rid}: {rule.get('mcs_value_type', '')} → {rule.get('otel_operation_name', '')}")
            attrs = rule.get("attribute_mappings", [])
            if attrs:
                typer.echo(f"    attributes: {len(attrs)} mappings")

    if new_meta:
        typer.echo(f"\n--- New event metadata ---")
        for vt in sorted(new_meta):
            typer.echo(f"  + {vt}")

    # Check for modified rules (attribute count changes)
    modified = []
    for rid in current_rules.keys() & proposed_rules.keys():
        c_attrs = len(current_rules[rid].get("attribute_mappings", []))
        p_attrs = len(proposed_rules[rid].get("attribute_mappings", []))
        if c_attrs != p_attrs:
            modified.append((rid, c_attrs, p_attrs))

    if modified:
        typer.echo(f"\n--- Modified rules ---")
        for rid, c, p in modified:
            typer.echo(f"  ~ {rid}: {c} → {p} attribute mappings")

    if not new_rules and not new_meta and not modified and not removed_rules:
        typer.echo("\nNo differences found.")


@app.command()
def approve(
    source: Path = typer.Option(Path("improve_runs"), "--source", "-s", help="Directory containing proposed_mapping.json"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Apply proposed mapping to config/default_mapping.json with version bump."""
    proposed_path = source / "proposed_mapping.json"
    if not proposed_path.exists():
        typer.echo(f"No proposed mapping found at {proposed_path}")
        typer.echo("Run the improvement loop first: uv run python improve.py run <input_dir>")
        raise typer.Exit(1)

    proposed_data = json.loads(proposed_path.read_text(encoding="utf-8"))
    current_data = json.loads(DEFAULT_MAPPING_PATH.read_text(encoding="utf-8"))

    current_version = current_data.get("version", "1.0")
    new_version = _bump_version(current_version)

    # Version bump
    proposed_data["version"] = new_version

    # Add changelog entry
    changelog = proposed_data.get("changelog", [])
    current_rules = {r["rule_id"] for r in current_data.get("rules", [])}
    proposed_rules = {r["rule_id"] for r in proposed_data.get("rules", [])}
    new_rule_count = len(proposed_rules - current_rules)

    changes = []
    if new_rule_count:
        changes.append(f"Added {new_rule_count} new mapping rules")
    current_meta_count = len(current_data.get("event_metadata", []))
    proposed_meta_count = len(proposed_data.get("event_metadata", []))
    if proposed_meta_count > current_meta_count:
        changes.append(f"Added {proposed_meta_count - current_meta_count} new event metadata entries")
    if not changes:
        changes.append("Updated mapping configuration")

    changelog.insert(0, {
        "version": new_version,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "changes": changes,
    })
    proposed_data["changelog"] = changelog

    typer.echo(f"Apply proposed mapping to {DEFAULT_MAPPING_PATH}?")
    typer.echo(f"  Version: {current_version} → {new_version}")
    for change in changes:
        typer.echo(f"  - {change}")

    if not yes:
        confirmed = typer.confirm("Proceed?")
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit(0)

    # Write updated config
    DEFAULT_MAPPING_PATH.write_text(
        json.dumps(proposed_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Applied v{new_version} to {DEFAULT_MAPPING_PATH}")


if __name__ == "__main__":
    app()
