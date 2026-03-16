import hashlib
import os
from collections import defaultdict

from loguru import logger

from models import (
    AttributeMapping,
    MappingSpecification,
    MCSEntity,
    OTELOperationName,
    OTELSpan,
    OTELSpanKind,
    OTELTrace,
    SpanMappingRule,
    TransformType,
)

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

_SPAN_KIND_MAP: dict[OTELSpanKind, int] = {
    OTELSpanKind.INTERNAL: 1,
    OTELSpanKind.SERVER: 2,
    OTELSpanKind.CLIENT: 3,
    OTELSpanKind.PRODUCER: 4,
    OTELSpanKind.CONSUMER: 5,
}


class _DefaultDict(dict):
    """Dict that returns empty string for missing keys, used in format_map."""

    def __missing__(self, key: str) -> str:
        return ""


def _md5_hex(data: str, length: int = 32) -> str:
    """Generate deterministic hex string from input via MD5."""
    return hashlib.md5(data.encode()).hexdigest()[:length]


def _resolve_property(properties: dict, path: str) -> str | None:
    """Resolve a dotted property path like 'value.outcome' from nested dicts."""
    if not path:
        return None
    parts = path.split(".")
    current: object = properties
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return str(current) if current is not None else None


def _apply_transform(
    raw_value: str | None, mapping: AttributeMapping
) -> str | None:
    """Apply transform logic to a raw property value."""
    match mapping.transform:
        case TransformType.direct | TransformType.lookup:
            return raw_value
        case TransformType.template:
            if raw_value is None:
                return None
            return mapping.transform_value.replace("{value}", raw_value)
        case TransformType.constant:
            return mapping.transform_value
    return raw_value


def _extract_timestamps(entity: MCSEntity) -> tuple[int, int]:
    """Extract start/end nanosecond timestamps from entity properties."""
    props = entity.properties

    if entity.entity_type == "turn":
        user_ts = props.get("user_ts", 0)
        bot_ts = props.get("bot_ts", 0)
        start = user_ts if user_ts else bot_ts
        end = bot_ts if bot_ts else user_ts
    else:
        ts = props.get("timestamp", 0)
        start = ts
        end = ts

    # Convert to nanoseconds — timestamps from MCS are in milliseconds (13-digit)
    start_ns = _to_nanoseconds(start)
    end_ns = _to_nanoseconds(end)

    # Ensure end >= start
    if end_ns < start_ns:
        end_ns = start_ns

    return start_ns, end_ns


def _to_nanoseconds(ts: int | float) -> int:
    """Convert a timestamp to nanoseconds. Handles seconds, millis, micros, nanos."""
    if ts == 0:
        return 0
    ts_int = int(ts)
    digits = len(str(abs(ts_int)))
    if digits <= 10:
        return ts_int * 1_000_000_000
    elif digits <= 13:
        return ts_int * 1_000_000
    elif digits <= 16:
        return ts_int * 1_000
    return ts_int


def _matches_rule(entity: MCSEntity, rule: SpanMappingRule) -> bool:
    """Check if an entity matches a span mapping rule."""
    if entity.entity_type != rule.mcs_entity_type:
        return False
    if rule.mcs_value_type:
        return entity.value_type == rule.mcs_value_type or entity.label == rule.mcs_value_type
    return True


def apply_mapping(
    entities: list[MCSEntity], spec: MappingSpecification
) -> OTELTrace:
    """Apply mapping rules to entities to produce an OTEL trace tree."""
    if not entities:
        trace_id = _md5_hex("empty")
        root = OTELSpan(
            trace_id=trace_id,
            span_id=_md5_hex(f"{trace_id}:empty", 16),
            name="empty",
            start_time_ns=0,
            end_time_ns=0,
        )
        return OTELTrace(trace_id=trace_id, root_span=root, total_spans=0, duration_ms=0.0)

    # Generate deterministic trace_id
    first = entities[0]
    conv_id = first.properties.get("conversation_id", "") or first.entity_id
    trace_id = _md5_hex(conv_id)

    # Phase 1: create spans/events per rule
    rule_spans: dict[str, list[OTELSpan]] = defaultdict(list)
    all_spans: list[OTELSpan] = []
    # Events to attach to parent spans (rule_id -> list of event dicts with parent info)
    pending_events: list[dict] = []

    # Build entity index for fast rule matching
    _entity_by_type: dict[str, list[MCSEntity]] = defaultdict(list)
    _entity_by_type_value: dict[tuple[str, str], list[MCSEntity]] = defaultdict(list)
    for _e in entities:
        _entity_by_type[_e.entity_type].append(_e)
        if _e.value_type:
            _entity_by_type_value[(_e.entity_type, _e.value_type)].append(_e)
        if _e.label and _e.label != _e.value_type:
            _entity_by_type_value[(_e.entity_type, _e.label)].append(_e)

    for rule in spec.rules:
        if rule.mcs_value_type:
            candidates = _entity_by_type_value.get(
                (rule.mcs_entity_type, rule.mcs_value_type), []
            )
        else:
            candidates = _entity_by_type.get(rule.mcs_entity_type, [])
        matched = [e for e in candidates if _matches_rule(e, rule)]
        logger.debug(
            "Rule '{}' matched {} entities", rule.rule_id, len(matched)
        )

        for entity in matched:
            start_ns, end_ns = _extract_timestamps(entity)

            # Build name from template
            name_ctx = _DefaultDict(entity.properties)
            name_ctx["bot_name"] = entity.properties.get("bot_name", "")
            name_ctx["turn_index"] = entity.properties.get("turn_index", "")
            # For turns, derive turn_index from entity_id
            if entity.entity_type == "turn" and not name_ctx.get("turn_index"):
                parts = entity.entity_id.split("_")
                if len(parts) > 1:
                    name_ctx["turn_index"] = parts[-1]

            name = (
                rule.span_name_template.format_map(name_ctx)
                if rule.span_name_template
                else rule.otel_operation_name.value
            )

            # Apply attribute mappings
            attributes: dict[str, str] = {}
            attributes["gen_ai.operation.name"] = rule.otel_operation_name.value

            for am in rule.attribute_mappings:
                raw = _resolve_property(entity.properties, am.mcs_property)
                value = _apply_transform(raw, am)
                if value is not None:
                    attributes[am.otel_attribute] = value

            if rule.output_type == "event":
                # Queue as event to attach to parent span
                pending_events.append({
                    "name": name,
                    "timestamp_ns": start_ns,
                    "attributes": attributes,
                    "parent_rule_id": rule.parent_rule_id,
                    "rule_id": rule.rule_id,
                })
            else:
                span_id = _md5_hex(
                    f"{trace_id}:{rule.rule_id}:{entity.entity_id}", 16
                )

                span = OTELSpan(
                    trace_id=trace_id,
                    span_id=span_id,
                    name=name,
                    kind=rule.otel_span_kind,
                    start_time_ns=start_ns,
                    end_time_ns=end_ns,
                    attributes=attributes,
                )

                rule_spans[rule.rule_id].append(span)
                all_spans.append(span)

    # Phase 2: build parent-child tree
    for rule in spec.rules:
        if not rule.parent_rule_id or rule.output_type == "event":
            continue
        parent_candidates = rule_spans.get(rule.parent_rule_id, [])
        if not parent_candidates:
            logger.warning(
                "Rule '{}' references parent '{}' but no parent spans exist",
                rule.rule_id,
                rule.parent_rule_id,
            )
            continue

        for child_span in rule_spans[rule.rule_id]:
            # Find best parent: closest parent span whose start_time <= child start_time
            best_parent: OTELSpan | None = None
            for p in parent_candidates:
                if p.start_time_ns <= child_span.start_time_ns or best_parent is None:
                    best_parent = p
            if not best_parent:
                best_parent = parent_candidates[0]

            child_span.parent_span_id = best_parent.span_id
            best_parent.children.append(child_span)

    # Phase 3: find root span
    root_span: OTELSpan | None = None
    for rule in spec.rules:
        if rule.is_root and rule_spans.get(rule.rule_id):
            root_span = rule_spans[rule.rule_id][0]
            break

    if not root_span:
        root_span = all_spans[0] if all_spans else OTELSpan(
            trace_id=trace_id,
            span_id=_md5_hex(f"{trace_id}:fallback", 16),
            name="unknown",
            start_time_ns=0,
            end_time_ns=0,
        )

    # Attach orphan top-level spans as children of root
    for span in all_spans:
        if span is not root_span and span.parent_span_id is None:
            span.parent_span_id = root_span.span_id
            root_span.children.append(span)

    # Attach pending events to their parent spans (or root)
    for evt in pending_events:
        parent_rule_id = evt["parent_rule_id"]
        parent_candidates = rule_spans.get(parent_rule_id, []) if parent_rule_id else []
        target_span = parent_candidates[0] if parent_candidates else root_span
        target_span.events.append({
            "name": evt["name"],
            "timeUnixNano": evt["timestamp_ns"],
            "attributes": evt["attributes"],
        })

    # Mark parent spans as ERROR when they contain error events
    for evt in pending_events:
        if evt["name"] in ("error", "error_code"):
            parent_rule_id = evt["parent_rule_id"]
            parent_candidates = rule_spans.get(parent_rule_id, []) if parent_rule_id else []
            target_span = parent_candidates[0] if parent_candidates else root_span
            target_span.status = "ERROR"

    # Adjust root span timing to cover all children
    if root_span.children:
        all_starts = [s.start_time_ns for s in all_spans if s.start_time_ns > 0]
        all_ends = [s.end_time_ns for s in all_spans if s.end_time_ns > 0]
        if all_starts:
            root_span.start_time_ns = min(all_starts)
        if all_ends:
            root_span.end_time_ns = max(all_ends)

    total = len(all_spans)
    total_events = len(pending_events)
    duration_ns = root_span.end_time_ns - root_span.start_time_ns
    duration_ms = duration_ns / 1_000_000

    logger.info(
        "Built trace {}: {} spans, {} events, {:.1f}ms duration",
        trace_id[:8],
        total,
        total_events,
        duration_ms,
    )

    return OTELTrace(
        trace_id=trace_id,
        root_span=root_span,
        total_spans=total,
        total_events=total_events,
        duration_ms=duration_ms,
    )


def _flatten_spans(span: OTELSpan) -> list[OTELSpan]:
    """Recursively flatten span tree depth-first."""
    result = [span]
    for child in span.children:
        result.extend(_flatten_spans(child))
    return result


def _typed_attribute_value(v: object) -> dict:
    """Convert a Python value to the appropriate OTLP attribute value type."""
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _span_to_otlp(span: OTELSpan) -> dict:
    """Convert a single OTELSpan to OTLP JSON format."""
    status_code = 0  # UNSET
    if span.status == "OK":
        status_code = 1
    elif span.status == "ERROR":
        status_code = 2

    otlp: dict = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "parentSpanId": span.parent_span_id or "",
        "name": span.name,
        "kind": _SPAN_KIND_MAP.get(span.kind, 1),
        "startTimeUnixNano": str(span.start_time_ns),
        "endTimeUnixNano": str(span.end_time_ns),
        "attributes": [
            {"key": k, "value": _typed_attribute_value(v)}
            for k, v in span.attributes.items()
        ],
        "status": {"code": status_code},
    }

    # Serialize events if present
    if span.events:
        otlp["events"] = [
            {
                "name": evt["name"],
                "timeUnixNano": str(evt["timeUnixNano"]),
                "attributes": [
                    {"key": k, "value": _typed_attribute_value(v)}
                    for k, v in evt.get("attributes", {}).items()
                ],
            }
            for evt in span.events
        ]

    return otlp


def to_otlp_json(
    trace: OTELTrace, service_name: str, bot_name: str | None = None, version: str = "1.0"
) -> dict:
    """Serialize trace to OTLP-compatible JSON structure."""
    effective_service_name = bot_name if bot_name else service_name
    flat_spans = _flatten_spans(trace.root_span)

    # Resolve SDK version from trace attributes or fall back to spec version
    sdk_version = version
    root_attrs = trace.root_span.attributes if trace.root_span else {}
    if root_attrs.get("telemetry.sdk.version"):
        sdk_version = root_attrs["telemetry.sdk.version"]

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": effective_service_name},
                        },
                        {
                            "key": "telemetry.sdk.name",
                            "value": {"stringValue": "mcs-otel-mapper"},
                        },
                        {
                            "key": "telemetry.sdk.version",
                            "value": {"stringValue": sdk_version},
                        },
                        {
                            "key": "telemetry.sdk.language",
                            "value": {"stringValue": "python"},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "mcs-otel-mapper",
                            "version": version,
                        },
                        "spans": [
                            _span_to_otlp(span) for span in flat_spans
                        ],
                    }
                ],
            }
        ]
    }
