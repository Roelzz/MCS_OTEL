import json
import os
import uuid
from datetime import datetime, timezone

from loguru import logger

from models import MCSActivity, MCSEntity, MCSTranscript, parse_activity_value

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

ROLE_BOT = 0
ROLE_USER = 1


def _normalize_timestamp(ts: int | float | str | None) -> int:
    """Normalize a timestamp to epoch millis or seconds (int), preserving precision.

    Handles:
    - int/float already in epoch seconds (10 digits) — returned as-is
    - int/float in epoch millis (13 digits) — returned as-is (millis preserved)
    - ISO 8601 strings like '2026-03-07T10:03:11.8086342+00:00' — converted to millis
    """
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        ts_int = int(ts)
        # 13-digit = milliseconds, preserve as-is
        if len(str(abs(ts_int))) >= 13:
            return ts_int
        return ts_int
    if isinstance(ts, str):
        ts = ts.strip()
        if not ts:
            return 0
        # Try parsing as number first
        try:
            return _normalize_timestamp(float(ts))
        except ValueError:
            pass
        # Parse ISO 8601 string — truncate fractional seconds to 6 digits (Python max)
        try:
            cleaned = ts.rstrip("Z")
            if "." in cleaned:
                main, rest = cleaned.split(".", 1)
                # Separate fractional seconds from timezone offset
                frac = ""
                tz_part = ""
                for i, ch in enumerate(rest):
                    if ch in ("+", "-") and i > 0:
                        frac = rest[:i]
                        tz_part = rest[i:]
                        break
                else:
                    frac = rest
                frac = frac[:6]
                cleaned = f"{main}.{frac}{tz_part}"
                if ts.endswith("Z"):
                    cleaned += "+00:00"
            elif ts.endswith("Z"):
                cleaned += "+00:00"
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            logger.warning("Could not parse timestamp '{}', returning 0", ts)
            return 0
    return 0

# Event types we track for entity extraction
TRACKED_EVENT_TYPES = {
    "UniversalSearchToolTraceData",
    "DynamicPlanReceived",
    "DynamicPlanStepTriggered",
    "DynamicPlanStepFinished",
    "DynamicPlanFinished",
    "DynamicPlanReceivedDebug",
    "DynamicPlanStepBindUpdate",
    "DynamicServerInitialize",
    "DynamicServerInitializeConfirmation",
    "DynamicServerToolsList",
    "DialogTracingInfo",
    "DialogRedirect",
    "VariableAssignment",
    "ErrorTraceData",
    "ErrorCode",
    "ProtocolInfo",
    "UnknownIntent",
    "SkillInfo",
    # Evaluation and success tracking
    "CSATSurveyResponse",
    "CSATSurveyRequest",
    "PRRSurveyResponse",
    "PRRSurveyRequest",
    "ImpliedSuccess",
}


def _resolve_activities(content: str) -> list[dict]:
    """Parse raw JSON content into a list of activity dicts.

    Handles: (a) Dataverse content field, (b) {"activities": [...]}, (c) bare [...].
    """
    data = json.loads(content)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if "activities" in data:
            return data["activities"]
        # Dataverse: look for a 'content' field containing JSON
        if "content" in data and isinstance(data["content"], str):
            inner = json.loads(data["content"])
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict) and "activities" in inner:
                return inner["activities"]

    raise ValueError("Cannot find activities array in provided JSON")


def _parse_activity(raw: dict, index: int) -> MCSActivity:
    """Convert a raw activity dict into an MCSActivity model."""
    from_data = raw.get("from", {})
    role = from_data.get("role", 0)
    if isinstance(role, str):
        role = ROLE_USER if role.lower() == "user" else ROLE_BOT
    elif not isinstance(role, int):
        role = 0

    activity_id = raw.get("id", "") or f"act_{index}"

    # Determine value_type: trace activities use valueType, events use name
    value_type = raw.get("valueType", "") or raw.get("name", "") or ""

    # Parse value through typed model if available
    raw_value = raw.get("value", {}) or {}
    if value_type and isinstance(raw_value, dict):
        typed_value = parse_activity_value(value_type, raw_value)
        # Convert typed model back to dict for downstream compatibility
        if hasattr(typed_value, "model_dump"):
            value = typed_value.model_dump(exclude_none=True)
        else:
            value = typed_value
    else:
        value = raw_value

    return MCSActivity(
        id=str(activity_id),
        type=raw.get("type", ""),
        timestamp=_normalize_timestamp(raw.get("timestamp", 0)),
        from_role=role,
        text=raw.get("text", "") or "",
        value_type=value_type,
        value=value,
        channel_data=raw.get("channelData", {}) or {},
        channel_id=raw.get("channelId", "") or "",
    )


def _extract_session_info(activities: list[MCSActivity]) -> dict:
    """Extract SessionInfo, ConversationInfo, and channel context from activities."""
    info: dict = {}
    for a in activities:
        if a.type == "trace":
            val = a.value
            if a.value_type == "SessionInfo":
                info["outcome"] = val.get("outcome", "None")
                info["session_type"] = val.get("type", "Unknown")
                info["turn_count"] = val.get("turnCount", 0)
                info["implied_success"] = val.get("impliedSuccess", False)
                info["outcome_reason"] = val.get("outcomeReason", "")
                info["start_time_utc"] = val.get("startTimeUtc", "")
                info["end_time_utc"] = val.get("endTimeUtc", "")
            elif a.value_type == "ConversationInfo":
                info["locale"] = val.get("locale", "")
                info["is_design_mode"] = val.get("isDesignMode", False)

    # Extract channel context from first activity with channel info
    for a in activities:
        if a.channel_id and "channel" not in info:
            info["channel"] = a.channel_id
        if a.channel_data:
            tenant = a.channel_data.get("tenant", {})
            if isinstance(tenant, dict) and tenant.get("id") and "tenant" not in info:
                info["tenant"] = tenant["id"]

    # Derive environment from design mode
    if info.get("is_design_mode"):
        info["environment"] = "design"
    elif "is_design_mode" in info:
        info["environment"] = "production"

    return info


def _find_first_bot_activity(activities: list[MCSActivity]) -> MCSActivity | None:
    """Find the first bot message activity (role=0, type=message)."""
    for a in activities:
        if a.type == "message" and a.from_role == ROLE_BOT:
            return a
    return None


def parse_transcript(content: str) -> MCSTranscript:
    """Parse raw JSON transcript into an MCSTranscript model."""
    raw_activities = _resolve_activities(content)
    logger.info("Parsing transcript with {} raw activities", len(raw_activities))

    activities = [_parse_activity(raw, i) for i, raw in enumerate(raw_activities)]

    # Extract conversation_id from first activity's conversation.id
    conversation_id = ""
    for raw in raw_activities:
        conv = raw.get("conversation", {})
        if isinstance(conv, dict) and conv.get("id"):
            conversation_id = conv["id"]
            break
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        logger.debug("No conversation.id found, generated: {}", conversation_id)

    # Extract bot info from first bot message
    bot_name = ""
    bot_id = ""
    for raw in raw_activities:
        from_data = raw.get("from", {})
        role = from_data.get("role")
        is_bot = role == ROLE_BOT or (isinstance(role, str) and role.lower() == "bot")
        if raw.get("type") == "message" and is_bot:
            bot_name = from_data.get("name", "")
            bot_id = from_data.get("id", "")
            break

    session_info = _extract_session_info(activities)

    transcript = MCSTranscript(
        conversation_id=conversation_id,
        bot_name=bot_name,
        bot_id=bot_id,
        activities=activities,
        session_info=session_info,
    )

    logger.info(
        "Parsed transcript: {} activities, bot='{}', session_outcome='{}'",
        len(activities),
        bot_name,
        session_info.get("outcome", "N/A"),
    )
    return transcript


def _extract_turns(activities: list[MCSActivity]) -> list[dict]:
    """Group activities into turns, including turn_0 for greeting."""
    sorted_acts = sorted(activities, key=lambda a: a.timestamp)

    user_indices = [
        i
        for i, a in enumerate(sorted_acts)
        if a.type == "message" and a.from_role == ROLE_USER
    ]

    turns = []

    # Turn 0: collect bot activities before first user message (greeting)
    if user_indices:
        first_user_idx = user_indices[0]
        pre_user_acts = sorted_acts[:first_user_idx]
    else:
        pre_user_acts = sorted_acts

    bot_greetings = [a for a in pre_user_acts if a.type == "message" and a.from_role == ROLE_BOT and a.text]
    if bot_greetings:
        first_bot = bot_greetings[0]
        greeting_text = " | ".join(a.text for a in bot_greetings)
        turns.append({
            "user_msg": "",
            "bot_msg": greeting_text,
            "user_ts": 0,
            "bot_ts": first_bot.timestamp,
            "topic_name": "",
            "action_type": "",
            "turn_index": "0",
            "is_greeting": True,
        })

    # User-initiated turns
    for pos, user_idx in enumerate(user_indices):
        user_act = sorted_acts[user_idx]
        end_idx = user_indices[pos + 1] if pos + 1 < len(user_indices) else len(sorted_acts)
        turn_acts = sorted_acts[user_idx:end_idx]

        # Find first bot message in this turn
        bot_act = None
        for a in turn_acts:
            if a.type == "message" and a.from_role == ROLE_BOT and a.text:
                bot_act = a
                break

        # Extract topic name from DynamicPlanStepTriggered
        topic_name = ""
        action_type = ""
        for a in turn_acts:
            if a.value_type == "DynamicPlanStepTriggered":
                topic_name = a.value.get("taskDialogId", "")
                action_type = a.value.get("type", "")
                break

        # Turn index: offset by 1 if we have a greeting turn_0
        idx = pos + 1 if turns and turns[0].get("is_greeting") else pos

        turns.append({
            "user_msg": user_act.text,
            "bot_msg": bot_act.text if bot_act else "",
            "user_ts": user_act.timestamp,
            "bot_ts": bot_act.timestamp if bot_act else 0,
            "topic_name": topic_name,
            "action_type": action_type,
            "turn_index": str(idx),
        })

    return turns


def extract_entities(transcript: MCSTranscript) -> list[MCSEntity]:
    """Flatten parsed transcript into entity list for the mapping UI."""
    entities: list[MCSEntity] = []

    # 1. Session root — always create, synthesize from metadata if SessionInfo absent
    has_session_info = "outcome" in transcript.session_info
    if has_session_info:
        root_props = dict(transcript.session_info)
    else:
        root_props = dict(transcript.session_info)
        root_props["outcome"] = "Unknown"
        root_props["session_type"] = "Unknown"
    root_props["bot_name"] = transcript.bot_name
    root_props["conversation_id"] = transcript.conversation_id
    entities.append(
        MCSEntity(
            entity_id="session_root",
            entity_type="trace_event",
            label="SessionInfo",
            value_type="SessionInfo",
            properties=root_props,
        )
    )

    # 2. Turns (including turn_0 greeting)
    turns = _extract_turns(transcript.activities)
    for turn in turns:
        turn_idx = turn.get("turn_index", "0")
        if turn.get("is_greeting"):
            label_text = turn["bot_msg"][:50] if turn["bot_msg"] else "greeting"
            label = f"Turn 0 (greeting): {label_text}"
        else:
            label_text = turn["user_msg"][:50] if turn["user_msg"] else "empty"
            label = f"Turn {turn_idx}: {label_text}"
        entities.append(
            MCSEntity(
                entity_id=f"turn_{turn_idx}",
                entity_type="turn",
                label=label,
                properties=turn,
            )
        )

    # 3. Trace/event entities
    trace_counters: dict[str, int] = {}
    for a in transcript.activities:
        vt = a.value_type
        if not vt or vt not in TRACKED_EVENT_TYPES:
            continue

        count = trace_counters.get(vt, 0)
        trace_counters[vt] = count + 1

        label = _event_label(vt)
        props = dict(a.value)
        props["timestamp"] = a.timestamp

        # Enrich entities with flattened properties for mapping
        _enrich_entity_properties(vt, props)

        entities.append(
            MCSEntity(
                entity_id=f"trace_{vt}_{count}",
                entity_type="trace_event",
                label=label,
                value_type=vt,
                properties=props,
            )
        )

    logger.info("Extracted {} entities from transcript", len(entities))
    return entities


def _enrich_entity_properties(vt: str, props: dict) -> None:
    """Enrich entity properties by flattening nested structures for OTEL mapping."""
    if vt == "DynamicPlanStepBindUpdate":
        args = props.get("arguments", {})
        if isinstance(args, dict):
            if "search_query" in args:
                props["search_query"] = args["search_query"]
            if "search_keywords" in args:
                props["search_keywords"] = str(args["search_keywords"])
            props["arguments_json"] = json.dumps(args)
        task_id = props.get("taskDialogId", "")
        if task_id.startswith("MCP:"):
            props["mcp_tool_name"] = task_id.split(":")[-1]

    elif vt == "DynamicPlanStepFinished":
        obs = props.get("observation", {})
        if isinstance(obs, dict):
            # MCP tool results
            if "content" in obs:
                texts = [c.get("text", "") for c in obs.get("content", []) if isinstance(c, dict)]
                props["tool_result_text"] = "\n".join(texts)
                props["tool_is_error"] = str(obs.get("isError", False))
            # Search results
            if "search_result" in obs:
                sr = obs["search_result"]
                results = sr.get("search_results", []) if isinstance(sr, dict) else []
                props["retrieval_document_count"] = str(len(results))
                props["retrieval_document_names"] = ", ".join(
                    r.get("Name", "") or "" for r in results if isinstance(r, dict)
                )
                props["retrieval_source_types"] = ", ".join(
                    sorted(set(r.get("Type", "") for r in results if isinstance(r, dict) and r.get("Type")))
                )
                errors = sr.get("search_errors", []) if isinstance(sr, dict) else []
                if errors:
                    props["retrieval_errors"] = json.dumps(errors)
            # Connector results
            if "messageLink" in obs:
                props["connector_result_url"] = obs["messageLink"]
            # HITL responder
            if "responderObjectId" in obs:
                props["hitl_responder_id"] = obs["responderObjectId"]
            props["observation_json"] = json.dumps(obs)

    elif vt == "UniversalSearchToolTraceData":
        ks = props.get("knowledgeSources", [])
        if isinstance(ks, list):
            props["knowledge_source_count"] = str(len(ks))
            props["knowledge_sources"] = ", ".join(str(s) for s in ks)
        output_ks = props.get("outputKnowledgeSources", [])
        if isinstance(output_ks, list):
            props["output_knowledge_sources"] = ", ".join(str(s) for s in output_ks)

    elif vt == "DynamicServerToolsList":
        tools = props.get("toolsList", [])
        if isinstance(tools, list):
            props["tool_count"] = str(len(tools))
            props["tool_names"] = ", ".join(
                t.get("displayName", t.get("identifier", "")) for t in tools if isinstance(t, dict)
            )

    elif vt == "DynamicPlanReceived":
        steps = props.get("steps", [])
        if isinstance(steps, list):
            props["step_count"] = str(len(steps))
        props["is_final_plan"] = str(props.get("isFinalPlan", False))
        tool_defs = props.get("toolDefinitions", [])
        if isinstance(tool_defs, list):
            props["tool_definition_count"] = str(len(tool_defs))

    elif vt == "DynamicPlanReceivedDebug":
        if props.get("ask"):
            props["user_ask"] = str(props["ask"])
        if props.get("summary"):
            props["plan_summary"] = str(props["summary"])

    elif vt == "DynamicPlanFinished":
        props["was_cancelled"] = str(props.get("wasCancelled", False))

    elif vt == "DialogTracingInfo":
        actions = props.get("actions", [])
        if isinstance(actions, list):
            props["action_count"] = str(len(actions))
            action_types = [a.get("actionType", "") for a in actions if isinstance(a, dict)]
            props["action_types"] = ", ".join(action_types)
            topic_ids = sorted(set(
                a.get("topicId", "") for a in actions if isinstance(a, dict) and a.get("topicId")
            ))
            if topic_ids:
                props["topic_ids"] = ", ".join(topic_ids)
            exceptions = [
                a.get("exception", "") for a in actions if isinstance(a, dict) and a.get("exception")
            ]
            if exceptions:
                props["dialog_exceptions"] = "; ".join(exceptions)

    elif vt == "ErrorTraceData":
        if props.get("errorCode"):
            props["errorCode"] = str(props["errorCode"])
        if props.get("errorMessage"):
            props["errorMessage"] = str(props["errorMessage"])
        if props.get("isUserError") is not None:
            props["isUserError"] = str(props["isUserError"])

    elif vt == "ErrorCode":
        if props.get("errorCode"):
            props["errorCode"] = str(props["errorCode"])
        if props.get("errorMessage"):
            props["errorMessage"] = str(props["errorMessage"])

    elif vt == "VariableAssignment":
        if props.get("name"):
            props["name"] = str(props["name"])
        if props.get("value") is not None:
            props["value"] = str(props["value"])
        if props.get("type"):
            props["type"] = str(props["type"])

    elif vt == "UnknownIntent":
        if props.get("userQuery"):
            props["userQuery"] = str(props["userQuery"])

    # CSAT/PRR/ImpliedSuccess enrichment
    elif vt == "CSATSurveyResponse":
        if props.get("score") is not None:
            props["csat_score"] = str(props["score"])
        if props.get("comment"):
            props["csat_comment"] = str(props["comment"])

    elif vt == "PRRSurveyResponse":
        if props.get("response") is not None:
            props["prr_response"] = str(props["response"])

    elif vt == "ImpliedSuccess":
        if props.get("dialogId"):
            props["implied_success_dialog_id"] = str(props["dialogId"])


def _event_label(value_type: str) -> str:
    """Map a value_type to a human-readable label."""
    labels = {
        "UniversalSearchToolTraceData": "Knowledge Search",
        "DynamicPlanReceived": "Plan Received",
        "DynamicPlanReceivedDebug": "Plan Received (Debug)",
        "DynamicPlanStepTriggered": "Plan Step Triggered",
        "DynamicPlanStepFinished": "Plan Step Finished",
        "DynamicPlanStepBindUpdate": "Plan Step Bind Update",
        "DynamicPlanFinished": "Plan Finished",
        "DynamicServerInitialize": "MCP Server Init",
        "DynamicServerToolsList": "MCP Tools List",
        "DialogTracingInfo": "Dialog Tracing",
        "DialogRedirect": "Dialog Redirect",
        "VariableAssignment": "Variable Assignment",
        "ErrorTraceData": "Error",
        "ErrorCode": "Error Code",
        "DynamicServerInitializeConfirmation": "MCP Server Init Confirmation",
        "ProtocolInfo": "Protocol Info",
        "UnknownIntent": "Unknown Intent",
        "SkillInfo": "Skill Info",
        # Evaluation types
        "CSATSurveyResponse": "CSAT Response",
        "CSATSurveyRequest": "CSAT Request",
        "PRRSurveyResponse": "PRR Response",
        "PRRSurveyRequest": "PRR Request",
        "ImpliedSuccess": "Implied Success",
    }
    return labels.get(value_type, value_type)
