from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- MCS side (parsed from uploaded data) ---


class MCSActivity(BaseModel):
    id: str
    type: str
    timestamp: int
    from_role: int
    text: str = ""
    value_type: str = ""
    value: dict = Field(default_factory=dict)
    channel_data: dict = Field(default_factory=dict)
    channel_id: str = ""


class MCSTranscript(BaseModel):
    conversation_id: str
    bot_name: str = ""
    bot_id: str = ""
    activities: list[MCSActivity] = Field(default_factory=list)
    session_info: dict = Field(default_factory=dict)


class MCSEntity(BaseModel):
    entity_id: str
    entity_type: str
    source_type: str = "transcript"
    label: str
    value_type: str = ""
    properties: dict = Field(default_factory=dict)


# --- Typed value sub-models (nested in activity.value) ---


class SessionInfoValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    outcome: str | None = Field(default=None)
    type: str | None = Field(default=None)
    startTimeUtc: str | None = Field(default=None)
    endTimeUtc: str | None = Field(default=None)
    turnCount: int | None = Field(default=None)
    outcomeReason: str | None = Field(default=None)
    impliedSuccess: bool | None = Field(default=None)


class IntentRecognitionValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    intentName: str | None = Field(default=None)
    intentId: str | None = Field(default=None)
    score: float | None = Field(default=None)
    userMessage: str | None = Field(default=None)


class ConversationInfoValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    isDesignMode: bool | None = Field(default=None)
    locale: str | None = Field(default=None)


class DynamicPlanReceivedValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    steps: list[str] | None = Field(default=None)
    isFinalPlan: bool | None = Field(default=None)
    planIdentifier: str | None = Field(default=None)
    toolDefinitions: list[dict[str, Any]] | None = Field(default=None)


class DynamicPlanStepTriggeredValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    planIdentifier: str | None = Field(default=None)
    stepId: str | None = Field(default=None)
    taskDialogId: str | None = Field(default=None)
    thought: str | None = Field(default=None)
    type: str | None = Field(default=None)


class DynamicPlanFinishedValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    planId: str | None = Field(default=None)
    wasCancelled: bool | None = Field(default=None)


class DialogRedirectValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    targetDialogId: str | None = Field(default=None)
    targetDialogName: str | None = Field(default=None)
    sourceDialogId: str | None = Field(default=None)


class VariableAssignmentValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None)
    value: Any = Field(default=None)
    type: str | None = Field(default=None)


class ErrorTraceDataValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    isUserError: bool | None = Field(default=None)
    errorCode: str | None = Field(default=None)
    errorMessage: str | None = Field(default=None)


class UnknownIntentValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    userQuery: str | None = Field(default=None)


class KnowledgeTraceDataValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    completionState: str | None = Field(default=None)
    isKnowledgeSearched: bool | None = Field(default=None)
    citedKnowledgeSources: list[dict[str, Any]] | None = Field(default=None)


class GPTAnswerValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    gptAnswerState: str | None = Field(default=None)


class CSATSurveyResponseValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: int | None = Field(default=None)
    comment: str | None = Field(default=None)


class PRRSurveyResponseValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    response: str | bool | None = Field(default=None)


class EscalationRequestedValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    escalationRequestType: int | None = Field(default=None)


class HandOffValue(BaseModel):
    model_config = ConfigDict(extra="allow")


class ImpliedSuccessValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    dialogId: str | None = Field(default=None)


class NodeTraceDataValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodeID: str | None = Field(default=None)
    nodeType: str | None = Field(default=None)
    startTime: str | None = Field(default=None)
    endTime: str | None = Field(default=None)
    topicDisplayName: str | None = Field(default=None)


# --- Schema registry: valueType -> value model class ---

SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "SessionInfo": SessionInfoValue,
    "IntentRecognition": IntentRecognitionValue,
    "ConversationInfo": ConversationInfoValue,
    "DynamicPlanReceived": DynamicPlanReceivedValue,
    "DynamicPlanStepTriggered": DynamicPlanStepTriggeredValue,
    "DynamicPlanFinished": DynamicPlanFinishedValue,
    "DialogRedirect": DialogRedirectValue,
    "VariableAssignment": VariableAssignmentValue,
    "ErrorTraceData": ErrorTraceDataValue,
    "UnknownIntent": UnknownIntentValue,
    "KnowledgeTraceData": KnowledgeTraceDataValue,
    "GPTAnswer": GPTAnswerValue,
    "CSATSurveyResponse": CSATSurveyResponseValue,
    "PRRSurveyResponse": PRRSurveyResponseValue,
    "EscalationRequested": EscalationRequestedValue,
    "HandOff": HandOffValue,
    "ImpliedSuccess": ImpliedSuccessValue,
    "nodeTraceData": NodeTraceDataValue,
}


def parse_activity_value(value_type: str, raw_value: dict) -> BaseModel | dict:
    """Parse a raw value dict into the appropriate typed model.

    Falls back to raw dict for unknown valueTypes.
    """
    model_cls = SCHEMA_REGISTRY.get(value_type)
    if not model_cls:
        return raw_value
    try:
        return model_cls.model_validate(raw_value)
    except Exception:
        return raw_value


# --- OTEL side (target) ---


class OTELSpanKind(str, Enum):
    CLIENT = "CLIENT"
    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class OTELOperationName(str, Enum):
    invoke_agent = "invoke_agent"
    chat = "chat"
    execute_tool = "execute_tool"
    knowledge_retrieval = "knowledge.retrieval"
    create_agent = "create_agent"
    text_completion = "text_completion"
    chain = "chain"
    dialog_redirect = "dialog_redirect"
    intent_recognition = "intent_recognition"
    execute_node = "execute_node"


class OTELSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: OTELSpanKind = OTELSpanKind.INTERNAL
    start_time_ns: int
    end_time_ns: int
    attributes: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    status: str = "UNSET"
    children: list["OTELSpan"] = Field(default_factory=list)


class OTELTrace(BaseModel):
    trace_id: str
    root_span: OTELSpan
    total_spans: int
    total_events: int = 0
    duration_ms: float


# --- Mapping (the core value) ---


class TransformType(str, Enum):
    direct = "direct"
    template = "template"
    constant = "constant"
    lookup = "lookup"


class AttributeMapping(BaseModel):
    mcs_property: str
    otel_attribute: str
    transform: TransformType = TransformType.direct
    transform_value: str = ""


class SpanMappingRule(BaseModel):
    rule_id: str
    rule_name: str = ""
    description: str = ""
    mcs_entity_type: str
    mcs_value_type: str = ""
    otel_operation_name: OTELOperationName
    otel_span_kind: OTELSpanKind = OTELSpanKind.INTERNAL
    span_name_template: str = ""
    is_root: bool = False
    parent_rule_id: str | None = None
    output_type: str = "span"
    attribute_mappings: list[AttributeMapping] = Field(default_factory=list)


class EventMetadata(BaseModel):
    value_type: str
    tracked: bool = True
    label: str = ""
    description: str = ""
    entity_type: str = ""
    default_output_type: str = ""


class EnrichmentOp(BaseModel):
    target: str
    op: str  # extract_path, len, join, join_unique_sorted, json_dump, str_coerce, rename, template, conditional
    source: str = ""
    separator: str = ""
    template: str = ""
    condition: dict = Field(default_factory=dict)


class EnrichmentRule(BaseModel):
    value_type: str
    derived_fields: list[EnrichmentOp] = Field(default_factory=list)


class SessionInfoFieldMapping(BaseModel):
    source_key: str
    target_key: str
    default: Any = ""


class SessionInfoExtraction(BaseModel):
    source_value_type: str
    field_mappings: list[SessionInfoFieldMapping] = Field(default_factory=list)


class DerivedSessionField(BaseModel):
    target_key: str
    condition: dict = Field(default_factory=dict)
    true_value: str = ""
    false_value: str = ""


class ChangelogEntry(BaseModel):
    version: str
    date: str
    changes: list[str] = Field(default_factory=list)


class MappingSpecification(BaseModel):
    version: str = "1.0"
    name: str = "MCS-to-OTEL GenAI Mapping"
    description: str = ""
    service_name: str = "copilot-studio"
    event_metadata: list[EventMetadata] = Field(default_factory=list)
    enrichment_rules: list[EnrichmentRule] = Field(default_factory=list)
    rules: list[SpanMappingRule] = Field(default_factory=list)
    session_info_extraction: list[SessionInfoExtraction] = Field(default_factory=list)
    derived_session_fields: list[DerivedSessionField] = Field(default_factory=list)
    error_event_names: list[str] = Field(
        default_factory=lambda: ["error", "error_code"]
    )
    changelog: list[ChangelogEntry] = Field(default_factory=list)
