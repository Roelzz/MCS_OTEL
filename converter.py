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
        # Match against label or entity properties
        if entity.label == rule.mcs_value_type:
            return True
        # Also check if the entity_id or label contains the value_type hint
        if rule.mcs_value_type in entity.entity_id:
            return True
        return False
    return True


def apply_mapping(
    entities: list[MCSEntity], spec: MappingSpecification
) -> OTELTrace:
    """Apply mapping rules to entities to produce an OTEL trace tree."""
    # Generate deterministic trace_id
    first = entities[0] if entities else None
    conv_id = ""
    if first:
        conv_id = first.properties.get("conversation_id", "") or first.entity_id
    trace_id = _md5_hex(conv_id)

    # Phase 1: create spans per rule, track which rule produced which spans
    rule_spans: dict[str, list[OTELSpan]] = defaultdict(list)
    all_spans: list[OTELSpan] = []

    for rule in spec.rules:
        matched = [e for e in entities if _matches_rule(e, rule)]
        logger.debug(
            "Rule '{}' matched {} entities", rule.rule_id, len(matched)
        )

        for entity in matched:
            span_id = _md5_hex(
                f"{trace_id}:{rule.rule_id}:{entity.entity_id}", 16
            )

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

            start_ns, end_ns = _extract_timestamps(entity)

            # Apply attribute mappings
            attributes: dict[str, str] = {}
            attributes["gen_ai.operation.name"] = rule.otel_operation_name.value
            attributes["gen_ai.system"] = "copilot_studio"

            for am in rule.attribute_mappings:
                raw = _resolve_property(entity.properties, am.mcs_property)
                value = _apply_transform(raw, am)
                if value is not None:
                    attributes[am.otel_attribute] = value

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
        if not rule.parent_rule_id:
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

    # Adjust root span timing to cover all children
    if root_span.children:
        all_starts = [s.start_time_ns for s in all_spans if s.start_time_ns > 0]
        all_ends = [s.end_time_ns for s in all_spans if s.end_time_ns > 0]
        if all_starts:
            root_span.start_time_ns = min(all_starts)
        if all_ends:
            root_span.end_time_ns = max(all_ends)

    total = len(all_spans)
    duration_ns = root_span.end_time_ns - root_span.start_time_ns
    duration_ms = duration_ns / 1_000_000

    logger.info(
        "Built trace {}: {} spans, {:.1f}ms duration",
        trace_id[:8],
        total,
        duration_ms,
    )

    return OTELTrace(
        trace_id=trace_id,
        root_span=root_span,
        total_spans=total,
        duration_ms=duration_ms,
    )


def generate_default_mapping() -> MappingSpecification:
    """Create sensible default mapping rules for MCS transcript entities."""
    return MappingSpecification(
        version="1.0",
        name="MCS-to-OTEL GenAI Mapping",
        service_name="copilot-studio",
        rules=[
            # --- Root span ---
            SpanMappingRule(
                rule_id="session_root",
                rule_name="Session Root Span",
                mcs_entity_type="trace_event",
                mcs_value_type="SessionInfo",
                otel_operation_name=OTELOperationName.agent_turn,
                otel_span_kind=OTELSpanKind.SERVER,
                span_name_template="agent.turn {bot_name}",
                is_root=True,
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="outcome",
                        otel_attribute="copilot_studio.session_outcome",
                    ),
                    AttributeMapping(
                        mcs_property="bot_name",
                        otel_attribute="gen_ai.agent.name",
                    ),
                    AttributeMapping(
                        mcs_property="conversation_id",
                        otel_attribute="gen_ai.conversation.id",
                    ),
                    AttributeMapping(
                        mcs_property="channel",
                        otel_attribute="channel",
                    ),
                    AttributeMapping(
                        mcs_property="environment",
                        otel_attribute="environment",
                    ),
                    AttributeMapping(
                        mcs_property="tenant",
                        otel_attribute="tenant",
                    ),
                ],
            ),
            # --- Conversation turns ---
            SpanMappingRule(
                rule_id="user_turn",
                rule_name="User-Bot Turn",
                mcs_entity_type="turn",
                otel_operation_name=OTELOperationName.gen_ai_chat,
                otel_span_kind=OTELSpanKind.CLIENT,
                span_name_template="gen_ai.chat turn:{turn_index}",
                parent_rule_id="session_root",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="user_msg",
                        otel_attribute="gen_ai.input.messages",
                        transform=TransformType.template,
                        transform_value='[{{"role":"user","content":"{value}"}}]',
                    ),
                    AttributeMapping(
                        mcs_property="bot_msg",
                        otel_attribute="gen_ai.output.messages",
                        transform=TransformType.template,
                        transform_value='[{{"role":"assistant","content":"{value}"}}]',
                    ),
                    AttributeMapping(
                        mcs_property="user_msg",
                        otel_attribute="user.message_preview",
                    ),
                    AttributeMapping(
                        mcs_property="bot_msg",
                        otel_attribute="assistant.message_preview",
                    ),
                    AttributeMapping(
                        mcs_property="topic_name",
                        otel_attribute="topic.name",
                    ),
                    AttributeMapping(
                        mcs_property="turn_index",
                        otel_attribute="conversation.turn",
                    ),
                ],
            ),
            # --- Knowledge search ---
            SpanMappingRule(
                rule_id="knowledge_search",
                rule_name="Knowledge Search",
                mcs_entity_type="trace_event",
                mcs_value_type="UniversalSearchToolTraceData",
                otel_operation_name=OTELOperationName.knowledge_retrieval,
                otel_span_kind=OTELSpanKind.CLIENT,
                span_name_template="knowledge.retrieval",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="toolId",
                        otel_attribute="gen_ai.tool.name",
                    ),
                    AttributeMapping(
                        mcs_property="",
                        otel_attribute="gen_ai.tool.type",
                        transform=TransformType.constant,
                        transform_value="datastore",
                    ),
                    AttributeMapping(
                        mcs_property="knowledge_sources",
                        otel_attribute="knowledge_source",
                    ),
                    AttributeMapping(
                        mcs_property="knowledge_source_count",
                        otel_attribute="retrieval.document_count",
                    ),
                    AttributeMapping(
                        mcs_property="output_knowledge_sources",
                        otel_attribute="copilot_studio.output_knowledge_sources",
                    ),
                ],
            ),
            # --- Dynamic plan ---
            SpanMappingRule(
                rule_id="dynamic_plan",
                rule_name="Dynamic Plan",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanReceived",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain plan",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="planIdentifier",
                        otel_attribute="copilot_studio.plan_identifier",
                    ),
                ],
            ),
            # --- Plan step bind (tool inputs, search queries) ---
            SpanMappingRule(
                rule_id="plan_step_bind",
                rule_name="Plan Step Bind (Tool Input)",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanStepBindUpdate",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain bind:{taskDialogId}",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="taskDialogId",
                        otel_attribute="gen_ai.tool.name",
                    ),
                    AttributeMapping(
                        mcs_property="search_query",
                        otel_attribute="gen_ai.retrieval.query.text",
                    ),
                    AttributeMapping(
                        mcs_property="search_keywords",
                        otel_attribute="copilot_studio.search_keywords",
                    ),
                    AttributeMapping(
                        mcs_property="arguments_json",
                        otel_attribute="gen_ai.tool.call.arguments",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_tool_name",
                        otel_attribute="copilot_studio.mcp_tool_name",
                    ),
                ],
            ),
            # --- Plan step finished (tool outputs, results) ---
            SpanMappingRule(
                rule_id="plan_step_finished",
                rule_name="Plan Step Finished (Tool Output)",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanStepFinished",
                otel_operation_name=OTELOperationName.tool_execute,
                otel_span_kind=OTELSpanKind.CLIENT,
                span_name_template="tool.execute {taskDialogId}",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="taskDialogId",
                        otel_attribute="gen_ai.tool.name",
                    ),
                    AttributeMapping(
                        mcs_property="executionTime",
                        otel_attribute="copilot_studio.execution_time",
                    ),
                    AttributeMapping(
                        mcs_property="state",
                        otel_attribute="copilot_studio.step_state",
                    ),
                    AttributeMapping(
                        mcs_property="tool_result_text",
                        otel_attribute="gen_ai.tool.call.result",
                    ),
                    AttributeMapping(
                        mcs_property="tool_is_error",
                        otel_attribute="copilot_studio.tool_is_error",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_document_count",
                        otel_attribute="retrieval.document_count",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_document_names",
                        otel_attribute="copilot_studio.retrieval_documents",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_source_types",
                        otel_attribute="copilot_studio.retrieval_source_type",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_errors",
                        otel_attribute="copilot_studio.retrieval_errors",
                    ),
                    AttributeMapping(
                        mcs_property="connector_result_url",
                        otel_attribute="copilot_studio.connector_result_url",
                    ),
                    AttributeMapping(
                        mcs_property="hitl_responder_id",
                        otel_attribute="copilot_studio.hitl_responder_id",
                    ),
                ],
            ),
            # --- Plan finished ---
            SpanMappingRule(
                rule_id="plan_finished",
                rule_name="Plan Finished",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanFinished",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain plan_finished",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="planId",
                        otel_attribute="copilot_studio.plan_identifier",
                    ),
                    AttributeMapping(
                        mcs_property="was_cancelled",
                        otel_attribute="copilot_studio.plan_was_cancelled",
                    ),
                ],
            ),
            # --- Topic classification (dialog redirect) ---
            SpanMappingRule(
                rule_id="topic_classification",
                rule_name="Topic Classification",
                mcs_entity_type="trace_event",
                mcs_value_type="DialogRedirect",
                otel_operation_name=OTELOperationName.topic_classification,
                span_name_template="topic_classification",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="targetDialogId",
                        otel_attribute="topic.name",
                    ),
                ],
            ),
            # --- MCP server init ---
            SpanMappingRule(
                rule_id="mcp_server_init",
                rule_name="MCP Server Initialize",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicServerInitialize",
                otel_operation_name=OTELOperationName.create_agent,
                span_name_template="create_agent mcp_init",
                parent_rule_id="user_turn",
                attribute_mappings=[],
            ),
            # --- MCP tools list ---
            SpanMappingRule(
                rule_id="mcp_tools_list",
                rule_name="MCP Tools List",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicServerToolsList",
                otel_operation_name=OTELOperationName.create_agent,
                span_name_template="create_agent mcp_tools",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="tool_count",
                        otel_attribute="copilot_studio.mcp_tool_count",
                    ),
                    AttributeMapping(
                        mcs_property="tool_names",
                        otel_attribute="copilot_studio.mcp_tool_names",
                    ),
                ],
            ),
        ],
    )


def _flatten_spans(span: OTELSpan) -> list[OTELSpan]:
    """Recursively flatten span tree depth-first."""
    result = [span]
    for child in span.children:
        result.extend(_flatten_spans(child))
    return result


def _span_to_otlp(span: OTELSpan) -> dict:
    """Convert a single OTELSpan to OTLP JSON format."""
    return {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "parentSpanId": span.parent_span_id or "",
        "name": span.name,
        "kind": _SPAN_KIND_MAP.get(span.kind, 1),
        "startTimeUnixNano": str(span.start_time_ns),
        "endTimeUnixNano": str(span.end_time_ns),
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in span.attributes.items()
        ],
        "status": {"code": 1 if span.status == "OK" else 2},
    }


def to_otlp_json(trace: OTELTrace, service_name: str) -> dict:
    """Serialize trace to OTLP-compatible JSON structure."""
    flat_spans = _flatten_spans(trace.root_span)

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": service_name},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "mcs-otel-mapper",
                            "version": "1.0",
                        },
                        "spans": [
                            _span_to_otlp(span) for span in flat_spans
                        ],
                    }
                ],
            }
        ]
    }
