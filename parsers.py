import json
import os
import uuid

from loguru import logger

from models import MCSActivity, MCSEntity, MCSTranscript

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

ROLE_BOT = 0
ROLE_USER = 1

# Event types we track for entity extraction
TRACKED_EVENT_TYPES = {
    "UniversalSearchToolTraceData",
    "DynamicPlanReceived",
    "DynamicPlanStepTriggered",
    "DynamicPlanStepFinished",
    "DynamicPlanFinished",
    "DynamicPlanReceivedDebug",
    "DynamicPlanStepBindUpdate",
    "DialogTracing",
    "DialogRedirect",
    "VariableAssignment",
    "ErrorTraceData",
    "ErrorCode",
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
    if not isinstance(role, int):
        role = 0

    activity_id = raw.get("id", "") or f"act_{index}"

    # Determine value_type: trace activities use valueType, events use name
    value_type = raw.get("valueType", "") or raw.get("name", "") or ""

    return MCSActivity(
        id=str(activity_id),
        type=raw.get("type", ""),
        timestamp=raw.get("timestamp", 0),
        from_role=role,
        text=raw.get("text", "") or "",
        value_type=value_type,
        value=raw.get("value", {}) or {},
        channel_data=raw.get("channelData", {}) or {},
    )


def _extract_session_info(activities: list[MCSActivity]) -> dict:
    """Extract SessionInfo and ConversationInfo from trace activities."""
    info: dict = {}
    for a in activities:
        if a.type != "trace":
            continue
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
        if raw.get("type") == "message" and role == ROLE_BOT:
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
    """Group activities into user-initiated turns (user msg + bot response)."""
    sorted_acts = sorted(activities, key=lambda a: a.timestamp)

    user_indices = [
        i
        for i, a in enumerate(sorted_acts)
        if a.type == "message" and a.from_role == ROLE_USER
    ]

    turns = []
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

        turns.append({
            "user_msg": user_act.text,
            "bot_msg": bot_act.text if bot_act else "",
            "user_ts": user_act.timestamp,
            "bot_ts": bot_act.timestamp if bot_act else 0,
            "topic_name": topic_name,
            "action_type": action_type,
        })

    return turns


def extract_entities(transcript: MCSTranscript) -> list[MCSEntity]:
    """Flatten parsed transcript into entity list for the mapping UI."""
    entities: list[MCSEntity] = []

    # 1. Session root
    if transcript.session_info:
        entities.append(
            MCSEntity(
                entity_id="session_root",
                entity_type="trace_event",
                label="SessionInfo",
                properties=transcript.session_info,
            )
        )

    # 2. Turns
    turns = _extract_turns(transcript.activities)
    for i, turn in enumerate(turns):
        label_text = turn["user_msg"][:50] if turn["user_msg"] else "empty"
        entities.append(
            MCSEntity(
                entity_id=f"turn_{i}",
                entity_type="turn",
                label=f"Turn {i + 1}: {label_text}",
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
        entities.append(
            MCSEntity(
                entity_id=f"trace_{vt}_{count}",
                entity_type="trace_event",
                label=label,
                properties=a.value,
            )
        )

    logger.info("Extracted {} entities from transcript", len(entities))
    return entities


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
        "DialogTracing": "Dialog Tracing",
        "DialogRedirect": "Dialog Redirect",
        "VariableAssignment": "Variable Assignment",
        "ErrorTraceData": "Error",
        "ErrorCode": "Error",
    }
    return labels.get(value_type, value_type)
