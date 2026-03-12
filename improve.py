"""Self-learning mapper improvement engine.

Analyzes real MCS conversation transcripts to iteratively improve
parsers.py, converter.py, and otel_registry.py until coverage is maximized.

Loop: Analyze all transcripts -> measure coverage -> find gaps ->
      auto-fix obvious gaps -> ask human on ambiguous ones -> repeat.
"""

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer
from loguru import logger

from analyze_transcripts import (
    FileStats,
    aggregate_stats,
    analyze_file,
    build_mapping_gap_analysis,
    discover_files,
    iter_transcripts,
    suggest_attribute_mappings,
    suggest_mapping_rule,
)
from converter import apply_mapping, generate_default_mapping, to_otlp_json
from models import (
    AttributeMapping,
    MappingSpecification,
    MCSEntity,
    OTELOperationName,
    OTELSpanKind,
    SpanMappingRule,
)
from parsers import TRACKED_EVENT_TYPES, extract_entities, parse_transcript

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

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
    code_snippet: str = ""


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
        entities = extract_entities(transcript)
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
        fa.span_count = trace.total_spans

        total_attrs = 0
        filled_attrs = 0
        _count_attributes(trace.root_span, total_attrs, filled_attrs)
        counts = _count_attributes_recursive(trace.root_span)
        total_attrs, filled_attrs = counts
        fa.attribute_fill_rate = filled_attrs / total_attrs if total_attrs > 0 else 0.0

        _detect_empty_spans(trace.root_span, fa.empty_spans)

    except Exception as e:
        logger.debug("Failed to apply mapping to {}: {}", label, e)
        fa.error = f"mapping: {e}"

    return fa


def _analyze_single_file(
    fpath: Path,
    spec: MappingSpecification,
    tracked_types: set[str],
    mapped_by_vt: dict[str, set[str]],
) -> FileAnalysis:
    """Analyze a single transcript file through the full pipeline."""
    fa = FileAnalysis(path=str(fpath), success=False)

    try:
        content = fpath.read_text(encoding="utf-8")
        transcript = parse_transcript(content)
        entities = extract_entities(transcript)
    except Exception as e:
        fa.error = str(e)
        logger.debug("Failed to parse {}: {}", fpath, e)
        return fa

    fa.success = True
    fa.activity_count = len(transcript.activities)
    fa.entity_count = len(entities)

    # Collect value types from entities
    for ent in entities:
        vt = ent.value_type
        if not vt:
            continue
        fa.value_types[vt] = fa.value_types.get(vt, 0) + 1

        # Check if unknown
        if vt not in tracked_types and ent.entity_type == "trace_event":
            if vt not in fa.unknown_types:
                fa.unknown_types[vt] = ent.properties

        # Check for unmapped properties on tracked types
        if vt in tracked_types and vt in mapped_by_vt:
            mapped_props = mapped_by_vt[vt]
            skip_props = {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"}
            available = set(ent.properties.keys()) - skip_props - {"timestamp"}
            unmapped = available - mapped_props
            if unmapped:
                if vt not in fa.unmapped_props:
                    fa.unmapped_props[vt] = set()
                fa.unmapped_props[vt].update(unmapped)

    # Try applying the mapping to measure coverage
    try:
        trace = apply_mapping(entities, spec)
        fa.span_count = trace.total_spans

        # Compute attribute fill rate
        total_attrs = 0
        filled_attrs = 0
        _count_attributes(trace.root_span, total_attrs, filled_attrs)
        counts = _count_attributes_recursive(trace.root_span)
        total_attrs, filled_attrs = counts
        fa.attribute_fill_rate = filled_attrs / total_attrs if total_attrs > 0 else 0.0

        # Detect empty spans (only gen_ai.operation.name + gen_ai.system)
        _detect_empty_spans(trace.root_span, fa.empty_spans)

    except Exception as e:
        logger.debug("Failed to apply mapping to {}: {}", fpath, e)
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


def _count_attributes(span, total: int, filled: int) -> None:
    """Deprecated — use _count_attributes_recursive instead."""
    pass


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
    - new_type: unknown type -> TRACKED_EVENT_TYPES + SpanMappingRule
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
        code = suggest_mapping_rule(vt, sample_props)

        findings.append(Finding(
            category=category,
            auto_fixable=auto,
            value_type=vt,
            file_count=file_count,
            sample_value=_safe_sample(sample),
            code_snippet=code,
        ))

    # Unmapped properties on tracked types
    for vt, props in unmapped_props.items():
        for prop in sorted(props):
            # Count how many unique unmapped props — we consider all as auto-fixable
            # if the type itself is tracked (mapped props just need extending)
            findings.append(Finding(
                category="new_attribute",
                auto_fixable=True,
                value_type=vt,
                property_name=prop,
                file_count=0,  # Not tracked per-file for attributes
                code_snippet=f'AttributeMapping(\n    mcs_property="{prop}",\n    otel_attribute="copilot_studio.{prop}",\n),',
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

            # Generate a new rule
            rule_id = _to_snake_case(finding.value_type)
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


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


def _suggest_otel_op(value_type: str) -> OTELOperationName:
    """Heuristic OTEL operation for a value type."""
    vt = value_type.lower()
    if "search" in vt or "retrieval" in vt or "knowledge" in vt:
        return OTELOperationName.knowledge_retrieval
    if "plan" in vt or "chain" in vt or "dialog" in vt or "tracing" in vt:
        return OTELOperationName.chain
    if "tool" in vt or "step" in vt or "execute" in vt:
        return OTELOperationName.tool_execute
    if "error" in vt:
        return OTELOperationName.chain
    if "topic" in vt or "redirect" in vt or "intent" in vt:
        return OTELOperationName.topic_classification
    if "server" in vt or "agent" in vt or "skill" in vt or "mcp" in vt:
        return OTELOperationName.create_agent
    return OTELOperationName.chain


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


def generate_code_changes(
    applied: list[Finding],
    needs_review: list[Finding],
) -> dict[str, list[str]]:
    """Generate Python code snippets for all changes.

    Returns: {filename: [code_snippet, ...]}
    """
    changes: dict[str, list[str]] = {
        "parsers.py": [],
        "converter.py": [],
        "otel_registry.py": [],
    }

    for finding in applied + needs_review:
        if finding.category == "new_type":
            # Add to TRACKED_EVENT_TYPES
            changes["parsers.py"].append(f'    "{finding.value_type}",')
            # Add SpanMappingRule to converter
            changes["converter.py"].append(finding.code_snippet)
            # Add OTELAttribute entries to registry
            for prop in sorted(finding.sample_value.keys()):
                if prop in {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"}:
                    continue
                changes["otel_registry.py"].append(
                    f'    OTELAttribute(\n'
                    f'        key="copilot_studio.{prop}",\n'
                    f'        value_type="string",\n'
                    f'        description="Auto-discovered from {finding.value_type}",\n'
                    f'        requirement_level="recommended",\n'
                    f'        example_value="",\n'
                    f'    ),'
                )
        elif finding.category == "new_attribute":
            changes["converter.py"].append(
                f'# Add to {finding.value_type} rule:\n{finding.code_snippet}'
            )
            changes["otel_registry.py"].append(
                f'    OTELAttribute(\n'
                f'        key="copilot_studio.{finding.property_name}",\n'
                f'        value_type="string",\n'
                f'        description="Auto-discovered on {finding.value_type}",\n'
                f'        requirement_level="recommended",\n'
                f'        example_value="",\n'
                f'    ),'
            )
        elif finding.category == "new_enrichment":
            changes["parsers.py"].append(
                f'# NEEDS REVIEW: {finding.value_type} has nested structures\n'
                f'# Add enrichment block in _enrich_entity_properties()\n'
                f'{finding.code_snippet}'
            )

    # Filter out empty
    return {k: v for k, v in changes.items() if v}


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

    spec = generate_default_mapping()
    tracked_types = set(TRACKED_EVENT_TYPES)
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

    # Generate code export
    all_applied = []
    all_review = []
    for run in runs:
        all_applied.extend(run.auto_applied)
        all_review.extend(run.needs_review)

    code_changes = generate_code_changes(all_applied, all_review)
    _save_code_export(output_dir, code_changes)

    # Save final spec
    spec_path = output_dir / "improved_mapping.json"
    spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Improved mapping saved to {}", spec_path)

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
                "code_snippet": f.code_snippet,
                "sample_value": f.sample_value,
            }
            for f in run.needs_review
        ],
    }
    path = output_dir / f"{run.run_id}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.debug("Saved iteration to {}", path)


def _save_code_export(output_dir: Path, code_changes: dict[str, list[str]]) -> None:
    """Save code export as a Python file with all changes."""
    lines = [
        '"""Auto-generated code changes from improvement loop.',
        "",
        "Copy these snippets into the appropriate files.",
        '"""',
        "",
    ]

    for filename, snippets in sorted(code_changes.items()):
        lines.append(f"# {'='*60}")
        lines.append(f"# {filename}")
        lines.append(f"# {'='*60}")
        lines.append("")
        for snippet in snippets:
            lines.append(snippet)
            lines.append("")

    path = output_dir / "code_export.py"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Code export saved to {}", path)


# ---------------------------------------------------------------------------
# Source file modification
# ---------------------------------------------------------------------------


def apply_to_source_files(code_changes: dict[str, list[str]]) -> dict[str, bool]:
    """Write approved code changes to actual source files.

    For parsers.py:
    - Insert new types into TRACKED_EVENT_TYPES set

    For converter.py:
    - Insert new SpanMappingRule into generate_default_mapping().rules list

    For otel_registry.py:
    - Insert new OTELAttribute into MCS_CUSTOM_ATTRIBUTES list

    Uses pattern-based insertion points (find the closing bracket/brace, insert before it).
    Returns: {filename: success}
    """
    results: dict[str, bool] = {}

    if "parsers.py" in code_changes:
        results["parsers.py"] = _insert_into_parsers(code_changes["parsers.py"])

    if "converter.py" in code_changes:
        results["converter.py"] = _insert_into_converter(code_changes["converter.py"])

    if "otel_registry.py" in code_changes:
        results["otel_registry.py"] = _insert_into_registry(code_changes["otel_registry.py"])

    return results


def _insert_into_parsers(snippets: list[str]) -> bool:
    """Insert new types into TRACKED_EVENT_TYPES in parsers.py."""
    path = Path("parsers.py")
    try:
        content = path.read_text(encoding="utf-8")

        # Find TRACKED_EVENT_TYPES closing brace
        # Pattern: find the } that closes the set
        marker = "TRACKED_EVENT_TYPES = {"
        start_idx = content.find(marker)
        if start_idx == -1:
            logger.error("Could not find TRACKED_EVENT_TYPES in parsers.py")
            return False

        # Find the closing }
        close_idx = content.find("}", start_idx)
        if close_idx == -1:
            logger.error("Could not find closing brace for TRACKED_EVENT_TYPES")
            return False

        # Filter to only type name lines (skip enrichment snippets)
        type_lines = [s for s in snippets if s.strip().startswith('"') and s.strip().endswith('",')]

        if not type_lines:
            return True

        # Check which types are already present
        new_lines = []
        for line in type_lines:
            type_name = line.strip().strip('",')
            if f'"{type_name}"' not in content:
                new_lines.append(line)

        if not new_lines:
            return True

        insert_text = "\n".join(f"    {line.strip()}" for line in new_lines) + "\n"
        content = content[:close_idx] + insert_text + content[close_idx:]

        path.write_text(content, encoding="utf-8")
        logger.info("Inserted {} types into parsers.py", len(new_lines))
        return True
    except Exception as e:
        logger.error("Failed to update parsers.py: {}", e)
        return False


def _insert_into_converter(snippets: list[str]) -> bool:
    """Insert new SpanMappingRule entries into converter.py generate_default_mapping()."""
    path = Path("converter.py")
    try:
        content = path.read_text(encoding="utf-8")

        # Find the end of generate_default_mapping's rules list
        # Look for the last "]," before the closing ")" of the function
        marker = "def generate_default_mapping()"
        func_start = content.find(marker)
        if func_start == -1:
            logger.error("Could not find generate_default_mapping in converter.py")
            return False

        # Find rules=[ and its closing ]
        rules_start = content.find("rules=[", func_start)
        if rules_start == -1:
            logger.error("Could not find rules=[ in generate_default_mapping")
            return False

        # Find matching ] — track bracket depth
        bracket_depth = 0
        idx = rules_start + len("rules=[")
        while idx < len(content):
            if content[idx] == "[":
                bracket_depth += 1
            elif content[idx] == "]":
                if bracket_depth == 0:
                    break
                bracket_depth -= 1
            idx += 1

        if idx >= len(content):
            logger.error("Could not find closing ] for rules list")
            return False

        # Filter to only SpanMappingRule snippets
        rule_snippets = [s for s in snippets if "SpanMappingRule(" in s]

        if not rule_snippets:
            return True

        insert_text = "\n" + "\n".join(f"            {line}" for snippet in rule_snippets for line in snippet.split("\n")) + "\n"
        content = content[:idx] + insert_text + content[idx:]

        path.write_text(content, encoding="utf-8")
        logger.info("Inserted {} rules into converter.py", len(rule_snippets))
        return True
    except Exception as e:
        logger.error("Failed to update converter.py: {}", e)
        return False


def _insert_into_registry(snippets: list[str]) -> bool:
    """Insert new OTELAttribute entries into otel_registry.py."""
    path = Path("otel_registry.py")
    try:
        content = path.read_text(encoding="utf-8")

        # Find MCS_CUSTOM_ATTRIBUTES closing bracket
        marker = "MCS_CUSTOM_ATTRIBUTES"
        start_idx = content.find(marker)
        if start_idx == -1:
            logger.error("Could not find MCS_CUSTOM_ATTRIBUTES in otel_registry.py")
            return False

        # Find the list start [
        list_start = content.find("[", start_idx)
        if list_start == -1:
            return False

        # Find matching ]
        bracket_depth = 0
        idx = list_start + 1
        while idx < len(content):
            if content[idx] == "[":
                bracket_depth += 1
            elif content[idx] == "]":
                if bracket_depth == 0:
                    break
                bracket_depth -= 1
            idx += 1

        if idx >= len(content):
            return False

        # Filter to OTELAttribute snippets
        attr_snippets = [s for s in snippets if "OTELAttribute(" in s]
        if not attr_snippets:
            return True

        # Check for duplicates by key
        new_snippets = []
        for snippet in attr_snippets:
            key_match = re.search(r'key="([^"]+)"', snippet)
            if key_match and f'key="{key_match.group(1)}"' in content:
                continue
            new_snippets.append(snippet)

        if not new_snippets:
            return True

        insert_text = "\n" + "\n".join(f"    {line}" for snippet in new_snippets for line in snippet.split("\n")) + "\n"
        content = content[:idx] + insert_text + content[idx:]

        path.write_text(content, encoding="utf-8")
        logger.info("Inserted {} attributes into otel_registry.py", len(new_snippets))
        return True
    except Exception as e:
        logger.error("Failed to update otel_registry.py: {}", e)
        return False


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
        "code_snippet": finding.code_snippet,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def main(
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

    for i, run in enumerate(runs, 1):
        delta_cov = f"+{run.delta_coverage:.1f}%" if run.delta_coverage > 0 else f"{run.delta_coverage:.1f}%"
        typer.echo(
            f"  Iteration {i}: coverage={run.avg_coverage:.1f}% ({delta_cov}) | "
            f"fill_rate={run.avg_fill_rate:.1%} | "
            f"auto-fixed={len(run.auto_applied)} | "
            f"needs-review={len(run.needs_review)}"
        )

    if runs:
        final = runs[-1]
        typer.echo(f"\nFinal: {final.avg_coverage:.1f}% coverage, {final.avg_fill_rate:.1%} fill rate")
        typer.echo(f"Results: {output}/")

        if final.needs_review:
            typer.echo(f"\n{len(final.needs_review)} findings need human review — see {output}/code_export.py")


if __name__ == "__main__":
    app()
