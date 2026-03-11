from enum import Enum

from pydantic import BaseModel, Field


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
    properties: dict = Field(default_factory=dict)


# --- OTEL side (target) ---


class OTELSpanKind(str, Enum):
    CLIENT = "CLIENT"
    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class OTELOperationName(str, Enum):
    chat = "chat"
    invoke_agent = "invoke_agent"
    execute_tool = "execute_tool"
    create_agent = "create_agent"
    text_completion = "text_completion"
    chain = "chain"


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
    status: str = "OK"
    children: list["OTELSpan"] = Field(default_factory=list)


class OTELTrace(BaseModel):
    trace_id: str
    root_span: OTELSpan
    total_spans: int
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
    mcs_entity_type: str
    mcs_value_type: str = ""
    otel_operation_name: OTELOperationName
    otel_span_kind: OTELSpanKind = OTELSpanKind.INTERNAL
    span_name_template: str = ""
    is_root: bool = False
    parent_rule_id: str | None = None
    attribute_mappings: list[AttributeMapping] = Field(default_factory=list)


class MappingSpecification(BaseModel):
    version: str = "1.0"
    name: str = "MCS-to-OTEL GenAI Mapping"
    service_name: str = "copilot-studio"
    rules: list[SpanMappingRule] = Field(default_factory=list)
