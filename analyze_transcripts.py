"""Transcript analysis CLI — scans MCS transcripts and reports coverage gaps."""

import csv
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

from config_loader import load_default_mapping
from models import AttributeMapping, OTELOperationName, OTELSpanKind, SpanMappingRule
from config_loader import load_default_mapping as _load_spec
from parsers import _resolve_activities, parse_transcript

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

app = typer.Typer(help="Analyze MCS transcripts for mapping coverage gaps.")

_SPEC = _load_spec()
TRACKED_EVENT_TYPES = {em.value_type for em in _SPEC.event_metadata if em.tracked}

DEFAULT_SEARCH_DIRS = [
    "tests/fixtures/",
    "Agent_analyser/Transcripts/",
    "Agent_analyser/botContent/",
]


@dataclass
class FileStats:
    path: Path
    activity_count: int = 0
    bot_name: str = ""
    conversation_id: str = ""
    value_type_counts: dict[str, int] = field(default_factory=dict)
    value_type_props: dict[str, set[str]] = field(default_factory=dict)
    value_type_samples: dict[str, dict] = field(default_factory=dict)


@dataclass
class ValueTypeStats:
    name: str
    total_count: int = 0
    file_count: int = 0
    files: list[str] = field(default_factory=list)
    all_properties: set[str] = field(default_factory=set)
    is_tracked: bool = False
    has_mapping_rule: bool = False
    mapped_properties: set[str] = field(default_factory=set)
    sample_value: dict = field(default_factory=dict)


def discover_files(paths: list[Path]) -> list[Path]:
    """Glob *.json and *.csv in given dirs, dedupe."""
    found: dict[str, Path] = {}

    for p in paths:
        if p.is_file() and p.suffix in {".json", ".csv"}:
            found[str(p.resolve())] = p.resolve()
        elif p.is_dir():
            for ext in ("**/*.json", "**/*.csv"):
                for f in p.glob(ext):
                    found[str(f.resolve())] = f.resolve()

    return sorted(found.values())


def iter_transcripts(paths: list[Path]) -> Iterator[tuple[str, str]]:
    """Yield (source_label, content_string) from JSON files and CSV rows.

    JSON files: yield (filename, file_content) — one transcript per file.
    CSV files: yield (filename:row_N, content_column) — one transcript per row.

    CSV detection: looks for 'content' column (Dataverse export format).
    """
    for path in paths:
        if path.suffix == ".csv":
            try:
                csv.field_size_limit(10 * 1024 * 1024)  # 10 MB — Dataverse transcripts can be large
                with path.open(encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames and "content" not in reader.fieldnames:
                        logger.warning("CSV {} has no 'content' column, skipping", path.name)
                        continue
                    for row_num, row in enumerate(reader, start=1):
                        content = row.get("content", "").strip()
                        if content:
                            yield f"{path.name}:row_{row_num}", content
            except Exception as e:
                logger.warning("Skipping CSV {} — {}", path.name, e)
        else:
            try:
                content = path.read_text(encoding="utf-8")
                yield path.name, content
            except Exception as e:
                logger.warning("Skipping {} — {}", path.name, e)


def analyze_content(source_label: str, content: str) -> FileStats | None:
    """Analyze a transcript content string for valueType coverage."""
    stats = FileStats(path=Path(source_label))

    try:
        raw_activities = _resolve_activities(content)
    except Exception as e:
        logger.warning("Skipping {} — {}", source_label, e)
        return None

    stats.activity_count = len(raw_activities)

    try:
        transcript = parse_transcript(content)
        stats.bot_name = transcript.bot_name
        stats.conversation_id = transcript.conversation_id
    except Exception as e:
        logger.debug("Could not parse transcript metadata for {}: {}", source_label, e)

    for raw in raw_activities:
        vt = raw.get("valueType", "") or raw.get("name", "") or ""
        if not vt:
            continue

        stats.value_type_counts[vt] = stats.value_type_counts.get(vt, 0) + 1

        value = raw.get("value", {})
        if isinstance(value, dict) and value:
            props = set(value.keys())
            if vt not in stats.value_type_props:
                stats.value_type_props[vt] = set()
            stats.value_type_props[vt].update(props)

            if vt not in stats.value_type_samples:
                stats.value_type_samples[vt] = value

    return stats


def analyze_file(path: Path) -> FileStats | None:
    """Analyze a single transcript file for valueType coverage."""
    stats = FileStats(path=path)

    try:
        content = path.read_text(encoding="utf-8")
        raw_activities = _resolve_activities(content)
    except Exception as e:
        logger.warning("Skipping {} — {}", path, e)
        return None

    stats.activity_count = len(raw_activities)

    # Parse for metadata
    try:
        transcript = parse_transcript(content)
        stats.bot_name = transcript.bot_name
        stats.conversation_id = transcript.conversation_id
    except Exception as e:
        logger.debug("Could not parse transcript metadata for {}: {}", path, e)

    # Collect valueType info from raw activities
    for raw in raw_activities:
        vt = raw.get("valueType", "") or raw.get("name", "") or ""
        if not vt:
            continue

        stats.value_type_counts[vt] = stats.value_type_counts.get(vt, 0) + 1

        value = raw.get("value", {})
        if isinstance(value, dict) and value:
            props = set(value.keys())
            if vt not in stats.value_type_props:
                stats.value_type_props[vt] = set()
            stats.value_type_props[vt].update(props)

            if vt not in stats.value_type_samples:
                stats.value_type_samples[vt] = value

    return stats


def aggregate_stats(file_stats_list: list[FileStats]) -> dict[str, ValueTypeStats]:
    """Aggregate per-valueType stats across all files."""
    agg: dict[str, ValueTypeStats] = {}

    for fs in file_stats_list:
        for vt, count in fs.value_type_counts.items():
            if vt not in agg:
                agg[vt] = ValueTypeStats(name=vt)
            s = agg[vt]
            s.total_count += count
            s.file_count += 1
            s.files.append(str(fs.path.name))
            s.is_tracked = vt in TRACKED_EVENT_TYPES

            if vt in fs.value_type_props:
                s.all_properties.update(fs.value_type_props[vt])

            if not s.sample_value and vt in fs.value_type_samples:
                s.sample_value = fs.value_type_samples[vt]

    return agg


def build_mapping_gap_analysis(
    stats: dict[str, ValueTypeStats],
    mapping_rules: list[SpanMappingRule],
) -> dict[str, ValueTypeStats]:
    """Cross-reference valueType stats against mapping rules."""
    # Build lookup: mcs_value_type -> rule
    rule_by_vt: dict[str, SpanMappingRule] = {}
    for rule in mapping_rules:
        if rule.mcs_value_type:
            rule_by_vt[rule.mcs_value_type] = rule

    for vt, s in stats.items():
        rule = rule_by_vt.get(vt)
        if rule:
            s.has_mapping_rule = True
            s.mapped_properties = {am.mcs_property for am in rule.attribute_mappings if am.mcs_property}
        else:
            s.has_mapping_rule = False

    return stats


def _suggest_rule_id(value_type: str) -> str:
    """Convert CamelCase valueType to snake_case rule_id."""
    result = []
    for i, ch in enumerate(value_type):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


def _suggest_otel_op(value_type: str) -> str:
    """Heuristic OTEL operation name for a valueType."""
    vt = value_type.lower()
    if "search" in vt or "retrieval" in vt or "knowledge" in vt:
        return "OTELOperationName.knowledge_retrieval"
    if "plan" in vt or "chain" in vt or "dialog" in vt or "tracing" in vt:
        return "OTELOperationName.chain"
    if "tool" in vt or "step" in vt or "execute" in vt:
        return "OTELOperationName.tool_execute"
    if "error" in vt:
        return "OTELOperationName.chain"
    if "topic" in vt or "redirect" in vt or "intent" in vt:
        return "OTELOperationName.topic_classification"
    if "server" in vt or "agent" in vt or "skill" in vt or "mcp" in vt:
        return "OTELOperationName.create_agent"
    return "OTELOperationName.chain"


def suggest_mapping_rule(value_type: str, sample_props: set[str]) -> str:
    """Generate a copy-pasteable SpanMappingRule Python snippet."""
    rule_id = _suggest_rule_id(value_type)
    otel_op = _suggest_otel_op(value_type)
    span_name = f'{rule_id.replace("_", ".")}'

    # Build attribute mappings for each property
    attr_lines = []
    skip_props = {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"}
    for prop in sorted(sample_props):
        if prop in skip_props:
            continue
        otel_attr = f"copilot_studio.{prop}"
        attr_lines.append(
            f'                    AttributeMapping(\n'
            f'                        mcs_property="{prop}",\n'
            f'                        otel_attribute="{otel_attr}",\n'
            f'                    ),'
        )

    attrs_block = "\n".join(attr_lines) if attr_lines else ""
    mappings_section = (
        f"                attribute_mappings=[\n{attrs_block}\n                ],"
        if attrs_block
        else "                attribute_mappings=[],"
    )

    return (
        f'            SpanMappingRule(\n'
        f'                rule_id="{rule_id}",\n'
        f'                rule_name="{value_type}",\n'
        f'                mcs_entity_type="trace_event",\n'
        f'                mcs_value_type="{value_type}",\n'
        f'                otel_operation_name={otel_op},\n'
        f'                otel_span_kind=OTELSpanKind.INTERNAL,\n'
        f'                span_name_template="{span_name}",\n'
        f'                parent_rule_id="user_turn",\n'
        f'{mappings_section}\n'
        f'            ),'
    )


def suggest_attribute_mappings(props: set[str], mapped: set[str]) -> str:
    """Generate AttributeMapping snippets for unmapped properties."""
    unmapped = sorted(props - mapped - {"timestamp", "actions", "steps", "toolDefinitions", "observation", "content"})
    if not unmapped:
        return ""

    lines = []
    for prop in unmapped:
        lines.append(
            f'                    AttributeMapping(\n'
            f'                        mcs_property="{prop}",\n'
            f'                        otel_attribute="copilot_studio.{prop}",\n'
            f'                    ),'
        )
    return "\n".join(lines)


def render_markdown(
    file_stats_list: list[FileStats],
    stats: dict[str, ValueTypeStats],
) -> str:
    """Build the full markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_activities = sum(fs.activity_count for fs in file_stats_list)
    total_vts = len(stats)
    tracked_count = sum(1 for s in stats.values() if s.is_tracked)
    untracked_count = total_vts - tracked_count
    has_rule_count = sum(1 for s in stats.values() if s.has_mapping_rule)
    tracked_no_rule = sum(1 for s in stats.values() if s.is_tracked and not s.has_mapping_rule)

    lines = [
        "# MCS Transcript Analysis Report",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        f"- **Files analyzed:** {len(file_stats_list)}",
        f"- **Total activities:** {total_activities}",
        f"- **Unique valueTypes:** {total_vts}",
        f"- **Tracked (in TRACKED_EVENT_TYPES):** {tracked_count}",
        f"- **Untracked:** {untracked_count}",
        f"- **Have mapping rules:** {has_rule_count}",
        f"- **Tracked but missing rules:** {tracked_no_rule}",
        "",
        "### Files",
        "",
        "| File | Activities | Bot | Conversation ID |",
        "|------|-----------|-----|-----------------|",
    ]

    for fs in file_stats_list:
        lines.append(f"| `{fs.path.name}` | {fs.activity_count} | {fs.bot_name} | `{fs.conversation_id[:20]}…` |")

    lines.extend([
        "",
        "> **Note:** `ConversationInfo` and `SessionInfo` are handled specially in `_extract_session_info()`,",
        "> not via `TRACKED_EVENT_TYPES`. They appear in the table below but are not \"untracked\" — they are",
        "> extracted into `MCSTranscript.session_info` and mapped via the `session_root` rule.",
        "",
        "## All ValueTypes",
        "",
        "| valueType | Count | Files | Tracked | Has Rule | Properties |",
        "|-----------|-------|-------|---------|----------|------------|",
    ])

    session_types = {"ConversationInfo", "SessionInfo"}
    for vt in sorted(stats.keys()):
        s = stats[vt]
        tracked_mark = "yes" if s.is_tracked else ("session" if vt in session_types else "no")
        rule_mark = "yes" if s.has_mapping_rule else ("session_root" if vt in session_types else "no")
        prop_count = len(s.all_properties)
        mapped_count = len(s.mapped_properties)
        prop_str = f"{mapped_count}/{prop_count} mapped" if s.has_mapping_rule else f"{prop_count} available"
        lines.append(
            f"| `{vt}` | {s.total_count} | {s.file_count} | {tracked_mark} | {rule_mark} | {prop_str} |"
        )

    # Untracked valueTypes
    untracked = {vt: s for vt, s in stats.items() if not s.is_tracked and vt not in session_types}
    if untracked:
        lines.extend([
            "",
            "## Untracked ValueTypes",
            "",
            "These valueTypes appear in transcripts but are not in `TRACKED_EVENT_TYPES`.",
            "Consider adding them if they carry useful observability data.",
            "",
        ])

        for vt in sorted(untracked.keys()):
            s = untracked[vt]
            lines.extend([
                f"### `{vt}`",
                "",
                f"- **Occurrences:** {s.total_count} across {s.file_count} file(s)",
                f"- **Files:** {', '.join(s.files)}",
                f"- **Properties:** {', '.join(sorted(s.all_properties)) if s.all_properties else 'none'}",
                "",
            ])

            if s.sample_value:
                sample_json = json.dumps(s.sample_value, indent=2, default=str)
                # Truncate large samples
                sample_lines = sample_json.split("\n")
                if len(sample_lines) > 30:
                    sample_json = "\n".join(sample_lines[:30]) + "\n  // ... truncated"
                lines.extend([
                    "**Sample payload:**",
                    "```json",
                    sample_json,
                    "```",
                    "",
                ])

            suggested = suggest_mapping_rule(vt, s.all_properties)
            lines.extend([
                "**Suggested mapping rule:**",
                "```python",
                suggested,
                "```",
                "",
            ])

    # Attribute mapping gaps for tracked types with rules
    types_with_gaps = {}
    for vt, s in stats.items():
        if s.has_mapping_rule and s.all_properties:
            unmapped = s.all_properties - s.mapped_properties - {
                "timestamp", "actions", "steps", "toolDefinitions", "observation", "content",
            }
            if unmapped:
                types_with_gaps[vt] = (s, unmapped)

    if types_with_gaps:
        lines.extend([
            "",
            "## Attribute Mapping Gaps",
            "",
            "Tracked types that have mapping rules but unmapped properties.",
            "",
        ])

        for vt in sorted(types_with_gaps.keys()):
            s, unmapped = types_with_gaps[vt]
            lines.extend([
                f"### `{vt}`",
                "",
                f"- **Available properties:** {', '.join(sorted(s.all_properties))}",
                f"- **Currently mapped:** {', '.join(sorted(s.mapped_properties)) if s.mapped_properties else 'none'}",
                f"- **Unmapped:** {', '.join(sorted(unmapped))}",
                "",
            ])

            suggested = suggest_attribute_mappings(s.all_properties, s.mapped_properties)
            if suggested:
                lines.extend([
                    "**Suggested attribute mappings:**",
                    "```python",
                    suggested,
                    "```",
                    "",
                ])

    # Tracked types missing rules
    missing_rules = [
        vt for vt, s in stats.items()
        if s.is_tracked and not s.has_mapping_rule and vt not in session_types
    ]
    if missing_rules:
        lines.extend([
            "",
            "## Tracked Types Missing Rules",
            "",
            "These types are in `TRACKED_EVENT_TYPES` but have no `SpanMappingRule` in `generate_default_mapping()`.",
            "",
        ])
        for vt in sorted(missing_rules):
            s = stats[vt]
            lines.extend([
                f"### `{vt}`",
                "",
                f"- **Occurrences:** {s.total_count} across {s.file_count} file(s)",
                f"- **Properties:** {', '.join(sorted(s.all_properties)) if s.all_properties else 'none'}",
                "",
            ])
            suggested = suggest_mapping_rule(vt, s.all_properties)
            lines.extend([
                "**Suggested mapping rule:**",
                "```python",
                suggested,
                "```",
                "",
            ])

    return "\n".join(lines) + "\n"


@app.command()
def main(
    paths: list[Path] = typer.Argument(None, help="Files or directories to scan (default: tests/fixtures/ + Agent_analyser/)"),
    output: Path = typer.Option(Path("docs/transcript_analysis.md"), "--output", "-o", help="Output markdown path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Analyze MCS transcripts and report mapping coverage gaps."""
    if verbose:
        logger.remove()
        logger.add(
            sink=lambda msg: print(msg, end=""),
            level="DEBUG",
            format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
        )

    # Default search paths
    if not paths:
        paths = [Path(d) for d in DEFAULT_SEARCH_DIRS if Path(d).exists()]
        if not paths:
            logger.error("No default directories found. Provide paths explicitly.")
            raise typer.Exit(1)

    logger.info("Searching for transcripts in: {}", [str(p) for p in paths])

    files = discover_files(paths)
    if not files:
        logger.error("No transcript files found.")
        raise typer.Exit(1)

    logger.info("Found {} files (JSON + CSV)", len(files))

    # Analyze each transcript (JSON files yield 1, CSV files yield N rows)
    file_stats_list: list[FileStats] = []
    for label, content in iter_transcripts(files):
        logger.debug("Analyzing {}", label)
        result = analyze_content(label, content)
        if result:
            file_stats_list.append(result)

    if not file_stats_list:
        logger.error("No transcripts could be analyzed.")
        raise typer.Exit(1)

    logger.info("Successfully analyzed {} transcripts", len(file_stats_list))

    # Aggregate and analyze
    stats = aggregate_stats(file_stats_list)
    mapping_spec = load_default_mapping()
    stats = build_mapping_gap_analysis(stats, mapping_spec.rules)

    # Render report
    report = render_markdown(file_stats_list, stats)

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    logger.info("Report written to {}", output)

    # Print summary
    tracked = sum(1 for s in stats.values() if s.is_tracked)
    untracked = len(stats) - tracked
    has_rules = sum(1 for s in stats.values() if s.has_mapping_rule)
    typer.echo(f"\nAnalysis complete: {len(file_stats_list)} files, {len(stats)} valueTypes "
               f"({tracked} tracked, {untracked} untracked, {has_rules} with rules)")
    typer.echo(f"Report: {output}")


if __name__ == "__main__":
    app()
