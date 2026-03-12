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
    # Generate deterministic trace_id
    first = entities[0] if entities else None
    conv_id = ""
    if first:
        conv_id = first.properties.get("conversation_id", "") or first.entity_id
    trace_id = _md5_hex(conv_id)

    # Phase 1: create spans/events per rule
    rule_spans: dict[str, list[OTELSpan]] = defaultdict(list)
    all_spans: list[OTELSpan] = []
    # Events to attach to parent spans (rule_id -> list of event dicts with parent info)
    pending_events: list[dict] = []

    for rule in spec.rules:
        matched = [e for e in entities if _matches_rule(e, rule)]
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
            attributes["gen_ai.system"] = "copilot_studio"

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
                otel_operation_name=OTELOperationName.invoke_agent,
                otel_span_kind=OTELSpanKind.SERVER,
                span_name_template="invoke_agent {bot_name}",
                is_root=True,
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="outcome",
                        otel_attribute="mcs.session.outcome",
                    ),
                    AttributeMapping(
                        mcs_property="session_type",
                        otel_attribute="mcs.session.type",
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
                        mcs_property="",
                        otel_attribute="gen_ai.provider.name",
                        transform=TransformType.constant,
                        transform_value="copilot_studio",
                    ),
                    AttributeMapping(
                        mcs_property="channel",
                        otel_attribute="mcs.channel",
                    ),
                    AttributeMapping(
                        mcs_property="environment",
                        otel_attribute="mcs.environment",
                    ),
                    AttributeMapping(
                        mcs_property="tenant",
                        otel_attribute="mcs.tenant",
                    ),
                    AttributeMapping(
                        mcs_property="user_timezone",
                        otel_attribute="enduser.timezone",
                    ),
                    AttributeMapping(
                        mcs_property="user_locale",
                        otel_attribute="enduser.locale",
                    ),
                    AttributeMapping(
                        mcs_property="user_id",
                        otel_attribute="enduser.id",
                    ),
                    AttributeMapping(
                        mcs_property="ai_model",
                        otel_attribute="gen_ai.request.model",
                    ),
                    AttributeMapping(
                        mcs_property="knowledge_sources",
                        otel_attribute="mcs.knowledge.configured_sources",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_connector_name",
                        otel_attribute="mcs.mcp.connector_name",
                    ),
                    AttributeMapping(
                        mcs_property="auth_mode",
                        otel_attribute="mcs.auth.mode",
                    ),
                ],
            ),
            # --- Conversation turns ---
            SpanMappingRule(
                rule_id="user_turn",
                rule_name="User-Bot Turn",
                mcs_entity_type="turn",
                otel_operation_name=OTELOperationName.chat,
                otel_span_kind=OTELSpanKind.CLIENT,
                span_name_template="chat turn:{turn_index}",
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
                        otel_attribute="mcs.topic.name",
                    ),
                    AttributeMapping(
                        mcs_property="turn_index",
                        otel_attribute="mcs.turn.index",
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
                        otel_attribute="mcs.knowledge.sources",
                    ),
                    AttributeMapping(
                        mcs_property="knowledge_source_count",
                        otel_attribute="mcs.knowledge.source_count",
                    ),
                    AttributeMapping(
                        mcs_property="output_knowledge_sources",
                        otel_attribute="mcs.knowledge.output_sources",
                    ),
                    AttributeMapping(
                        mcs_property="full_result_count",
                        otel_attribute="mcs.knowledge.full_result_count",
                    ),
                    AttributeMapping(
                        mcs_property="filtered_result_count",
                        otel_attribute="mcs.knowledge.filtered_result_count",
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
                        otel_attribute="mcs.plan.id",
                    ),
                    AttributeMapping(
                        mcs_property="step_count",
                        otel_attribute="mcs.plan.step_count",
                    ),
                    AttributeMapping(
                        mcs_property="is_final_plan",
                        otel_attribute="mcs.plan.is_final",
                    ),
                    AttributeMapping(
                        mcs_property="think_time_ms",
                        otel_attribute="mcs.orchestrator.think_time_ms",
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
                        otel_attribute="mcs.search.keywords",
                    ),
                    AttributeMapping(
                        mcs_property="arguments_json",
                        otel_attribute="gen_ai.tool.call.arguments",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_tool_name",
                        otel_attribute="mcs.mcp.tool_name",
                    ),
                ],
            ),
            # --- Plan step finished (tool outputs, results) ---
            SpanMappingRule(
                rule_id="plan_step_finished",
                rule_name="Plan Step Finished (Tool Output)",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanStepFinished",
                otel_operation_name=OTELOperationName.execute_tool,
                otel_span_kind=OTELSpanKind.CLIENT,
                span_name_template="execute_tool {taskDialogId}",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="taskDialogId",
                        otel_attribute="gen_ai.tool.name",
                    ),
                    AttributeMapping(
                        mcs_property="executionTime",
                        otel_attribute="mcs.tool.execution_time",
                    ),
                    AttributeMapping(
                        mcs_property="state",
                        otel_attribute="mcs.tool.step_state",
                    ),
                    AttributeMapping(
                        mcs_property="tool_result_text",
                        otel_attribute="gen_ai.tool.call.result",
                    ),
                    AttributeMapping(
                        mcs_property="tool_is_error",
                        otel_attribute="mcs.tool.is_error",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_document_count",
                        otel_attribute="mcs.retrieval.document_count",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_document_names",
                        otel_attribute="mcs.retrieval.documents",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_source_types",
                        otel_attribute="mcs.retrieval.source_type",
                    ),
                    AttributeMapping(
                        mcs_property="retrieval_errors",
                        otel_attribute="mcs.retrieval.errors",
                    ),
                    AttributeMapping(
                        mcs_property="connector_result_url",
                        otel_attribute="mcs.connector.result_url",
                    ),
                    AttributeMapping(
                        mcs_property="hitl_responder_id",
                        otel_attribute="mcs.hitl.responder_id",
                    ),
                    AttributeMapping(
                        mcs_property="plan_used_outputs",
                        otel_attribute="mcs.plan.used_outputs",
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
                        otel_attribute="mcs.plan.id",
                    ),
                    AttributeMapping(
                        mcs_property="was_cancelled",
                        otel_attribute="mcs.plan.was_cancelled",
                    ),
                ],
            ),
            # --- Topic classification (dialog redirect) ---
            SpanMappingRule(
                rule_id="topic_classification",
                rule_name="Topic Classification",
                mcs_entity_type="trace_event",
                mcs_value_type="DialogRedirect",
                otel_operation_name=OTELOperationName.dialog_redirect,
                span_name_template="dialog_redirect",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="targetDialogId",
                        otel_attribute="mcs.topic.name",
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
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="mcp_server_name",
                        otel_attribute="mcs.mcp.server_name",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_server_version",
                        otel_attribute="mcs.mcp.server_version",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_protocol_version",
                        otel_attribute="mcs.mcp.protocol_version",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_session_id",
                        otel_attribute="mcs.mcp.session_id",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_capabilities",
                        otel_attribute="mcs.mcp.capabilities",
                    ),
                    AttributeMapping(
                        mcs_property="mcp_dialog_schema",
                        otel_attribute="mcs.mcp.dialog_schema",
                    ),
                ],
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
                        otel_attribute="mcs.mcp.tool_count",
                    ),
                    AttributeMapping(
                        mcs_property="tool_names",
                        otel_attribute="mcs.mcp.tool_names",
                    ),
                ],
            ),
            # --- Plan step triggered (orchestrator reasoning) ---
            SpanMappingRule(
                rule_id="plan_step_triggered",
                rule_name="Plan Step Triggered",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanStepTriggered",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain step:{taskDialogId}",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="thought",
                        otel_attribute="mcs.orchestrator.thought",
                    ),
                    AttributeMapping(
                        mcs_property="taskDialogId",
                        otel_attribute="gen_ai.tool.name",
                    ),
                    AttributeMapping(
                        mcs_property="type",
                        otel_attribute="mcs.step.type",
                    ),
                ],
            ),
            # --- Plan received debug (user ask) ---
            SpanMappingRule(
                rule_id="plan_received_debug",
                rule_name="Plan Received Debug",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicPlanReceivedDebug",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain plan_debug",
                parent_rule_id="dynamic_plan",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="user_ask",
                        otel_attribute="mcs.orchestrator.user_ask",
                    ),
                    AttributeMapping(
                        mcs_property="plan_summary",
                        otel_attribute="mcs.orchestrator.plan_summary",
                    ),
                ],
            ),
            # --- Dialog tracing ---
            SpanMappingRule(
                rule_id="dialog_tracing",
                rule_name="Dialog Tracing",
                mcs_entity_type="trace_event",
                mcs_value_type="DialogTracingInfo",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain dialog_trace",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="action_types",
                        otel_attribute="mcs.dialog.action_types",
                    ),
                    AttributeMapping(
                        mcs_property="topic_ids",
                        otel_attribute="mcs.dialog.topic_ids",
                    ),
                    AttributeMapping(
                        mcs_property="dialog_exceptions",
                        otel_attribute="mcs.dialog.exceptions",
                    ),
                    AttributeMapping(
                        mcs_property="action_count",
                        otel_attribute="mcs.dialog.action_count",
                    ),
                ],
            ),
            # --- Error trace (as event on turn) ---
            SpanMappingRule(
                rule_id="error_trace",
                rule_name="Error Trace",
                mcs_entity_type="trace_event",
                mcs_value_type="ErrorTraceData",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="error",
                output_type="event",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(mcs_property="errorCode", otel_attribute="error.type"),
                    AttributeMapping(mcs_property="errorMessage", otel_attribute="error.message"),
                    AttributeMapping(mcs_property="isUserError", otel_attribute="mcs.error.is_user_error"),
                ],
            ),
            # --- Error code (as event on turn) ---
            SpanMappingRule(
                rule_id="error_code",
                rule_name="Error Code",
                mcs_entity_type="trace_event",
                mcs_value_type="ErrorCode",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="error_code",
                output_type="event",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(mcs_property="errorCode", otel_attribute="error.type"),
                    AttributeMapping(mcs_property="errorMessage", otel_attribute="error.message"),
                ],
            ),
            # --- Variable assignment (as event on turn) ---
            SpanMappingRule(
                rule_id="variable_assignment",
                rule_name="Variable Assignment",
                mcs_entity_type="trace_event",
                mcs_value_type="VariableAssignment",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="variable_assignment",
                output_type="event",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(mcs_property="name", otel_attribute="mcs.variable.name"),
                    AttributeMapping(mcs_property="value", otel_attribute="mcs.variable.value"),
                    AttributeMapping(mcs_property="type", otel_attribute="mcs.variable.type"),
                ],
            ),
            # --- Unknown intent (as event on turn) ---
            SpanMappingRule(
                rule_id="unknown_intent",
                rule_name="Unknown Intent",
                mcs_entity_type="trace_event",
                mcs_value_type="UnknownIntent",
                otel_operation_name=OTELOperationName.intent_recognition,
                span_name_template="unknown_intent",
                output_type="event",
                parent_rule_id="user_turn",
                attribute_mappings=[
                    AttributeMapping(mcs_property="userQuery", otel_attribute="gen_ai.input.messages"),
                ],
            ),
            # --- MCP server init confirmation ---
            SpanMappingRule(
                rule_id="mcp_server_init_confirmation",
                rule_name="MCP Server Init Confirmation",
                mcs_entity_type="trace_event",
                mcs_value_type="DynamicServerInitializeConfirmation",
                otel_operation_name=OTELOperationName.create_agent,
                span_name_template="create_agent mcp_init_confirm",
                parent_rule_id="mcp_server_init",
                attribute_mappings=[],
            ),
            # --- Protocol info ---
            SpanMappingRule(
                rule_id="protocol_info",
                rule_name="Protocol Info",
                mcs_entity_type="trace_event",
                mcs_value_type="ProtocolInfo",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="chain protocol_info",
                parent_rule_id="user_turn",
                attribute_mappings=[],
            ),
            # --- Skill info ---
            SpanMappingRule(
                rule_id="skill_info",
                rule_name="Skill Info",
                mcs_entity_type="trace_event",
                mcs_value_type="SkillInfo",
                otel_operation_name=OTELOperationName.create_agent,
                span_name_template="create_agent skill_info",
                parent_rule_id="user_turn",
                attribute_mappings=[],
            ),
            # --- CSAT response (as event on root) ---
            SpanMappingRule(
                rule_id="csat_response",
                rule_name="CSAT Response",
                mcs_entity_type="trace_event",
                mcs_value_type="CSATSurveyResponse",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="csat_response",
                output_type="event",
                parent_rule_id="session_root",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="",
                        otel_attribute="gen_ai.evaluation.name",
                        transform=TransformType.constant,
                        transform_value="csat",
                    ),
                    AttributeMapping(
                        mcs_property="csat_score",
                        otel_attribute="gen_ai.evaluation.score.value",
                    ),
                    AttributeMapping(
                        mcs_property="csat_comment",
                        otel_attribute="gen_ai.evaluation.score.label",
                    ),
                ],
            ),
            # --- PRR response (as event on root) ---
            SpanMappingRule(
                rule_id="prr_response",
                rule_name="PRR Response",
                mcs_entity_type="trace_event",
                mcs_value_type="PRRSurveyResponse",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="prr_response",
                output_type="event",
                parent_rule_id="session_root",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="",
                        otel_attribute="gen_ai.evaluation.name",
                        transform=TransformType.constant,
                        transform_value="prr",
                    ),
                    AttributeMapping(
                        mcs_property="prr_response",
                        otel_attribute="gen_ai.evaluation.score.value",
                    ),
                ],
            ),
            # --- Implied success (as event on root) ---
            SpanMappingRule(
                rule_id="implied_success",
                rule_name="Implied Success",
                mcs_entity_type="trace_event",
                mcs_value_type="ImpliedSuccess",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="implied_success",
                output_type="event",
                parent_rule_id="session_root",
                attribute_mappings=[
                    AttributeMapping(
                        mcs_property="implied_success_dialog_id",
                        otel_attribute="mcs.dialog.id",
                    ),
                ],
            ),
            # --- Escalation (as event on root) ---
            SpanMappingRule(
                rule_id="escalation",
                rule_name="Escalation Requested",
                mcs_entity_type="trace_event",
                mcs_value_type="EscalationRequested",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="escalation",
                output_type="event",
                parent_rule_id="session_root",
                attribute_mappings=[],
            ),
            # --- HandOff (as event on root) ---
            SpanMappingRule(
                rule_id="handoff",
                rule_name="HandOff",
                mcs_entity_type="trace_event",
                mcs_value_type="HandOff",
                otel_operation_name=OTELOperationName.chain,
                span_name_template="handoff",
                output_type="event",
                parent_rule_id="session_root",
                attribute_mappings=[],
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
    otlp: dict = {
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

    # Serialize events if present
    if span.events:
        otlp["events"] = [
            {
                "name": evt["name"],
                "timeUnixNano": str(evt["timeUnixNano"]),
                "attributes": [
                    {"key": k, "value": {"stringValue": str(v)}}
                    for k, v in evt.get("attributes", {}).items()
                ],
            }
            for evt in span.events
        ]

    return otlp


def to_otlp_json(
    trace: OTELTrace, service_name: str, bot_name: str | None = None
) -> dict:
    """Serialize trace to OTLP-compatible JSON structure."""
    effective_service_name = bot_name if bot_name else service_name
    flat_spans = _flatten_spans(trace.root_span)

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": effective_service_name},
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
