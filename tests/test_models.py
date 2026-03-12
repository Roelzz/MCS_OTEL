import json

from models import (
    AttributeMapping,
    MappingSpecification,
    MCSActivity,
    MCSEntity,
    MCSTranscript,
    OTELOperationName,
    OTELSpan,
    OTELSpanKind,
    SpanMappingRule,
    TransformType,
)


class TestMCSModels:
    def test_activity_defaults(self):
        a = MCSActivity(id="1", type="message", timestamp=1000, from_role=1)
        assert a.text == ""
        assert a.value_type == ""
        assert a.value == {}

    def test_transcript_roundtrip(self):
        t = MCSTranscript(
            conversation_id="abc",
            bot_name="TestBot",
            activities=[MCSActivity(id="1", type="message", timestamp=1000, from_role=1, text="hi")],
            session_info={"outcome": "resolved"},
        )
        data = t.model_dump()
        t2 = MCSTranscript(**data)
        assert t2.conversation_id == "abc"
        assert t2.bot_name == "TestBot"
        assert len(t2.activities) == 1

    def test_entity_properties(self):
        e = MCSEntity(entity_id="e1", entity_type="turn", label="Turn 1", properties={"user_msg": "hello"})
        assert e.properties["user_msg"] == "hello"


class TestOTELModels:
    def test_span_children(self):
        child = OTELSpan(trace_id="t", span_id="c", name="child", start_time_ns=0, end_time_ns=100)
        parent = OTELSpan(
            trace_id="t", span_id="p", name="parent", start_time_ns=0, end_time_ns=200, children=[child]
        )
        assert len(parent.children) == 1
        assert parent.children[0].name == "child"

    def test_span_kind_enum(self):
        assert OTELSpanKind.INTERNAL == "INTERNAL"
        assert OTELSpanKind.CLIENT == "CLIENT"

    def test_operation_name_enum(self):
        assert OTELOperationName.invoke_agent == "invoke_agent"
        assert OTELOperationName.chat == "chat"
        assert OTELOperationName.execute_tool == "execute_tool"
        assert OTELOperationName.knowledge_retrieval == "knowledge.retrieval"
        assert OTELOperationName.dialog_redirect == "dialog_redirect"
        assert OTELOperationName.intent_recognition == "intent_recognition"
        assert OTELOperationName.execute_node == "execute_node"
        # Backward compat aliases
        assert OTELOperationName.agent_turn == "agent.turn"
        assert OTELOperationName.gen_ai_chat == "gen_ai.chat"
        assert OTELOperationName.tool_execute == "tool.execute"


class TestMappingModels:
    def test_attribute_mapping(self):
        am = AttributeMapping(mcs_property="outcome", otel_attribute="gen_ai.status")
        assert am.transform == TransformType.direct
        assert am.transform_value == ""

    def test_rule_defaults(self):
        r = SpanMappingRule(
            rule_id="test",
            mcs_entity_type="trace_event",
            otel_operation_name=OTELOperationName.chat,
        )
        assert r.is_root is False
        assert r.parent_rule_id is None
        assert r.otel_span_kind == OTELSpanKind.INTERNAL
        assert r.output_type == "span"

    def test_mapping_spec_roundtrip(self):
        spec = MappingSpecification(
            name="Test Mapping",
            service_name="test-service",
            rules=[
                SpanMappingRule(
                    rule_id="r1",
                    rule_name="Root",
                    mcs_entity_type="trace_event",
                    mcs_value_type="SessionInfo",
                    otel_operation_name=OTELOperationName.agent_turn,
                    is_root=True,
                    attribute_mappings=[
                        AttributeMapping(mcs_property="outcome", otel_attribute="session.outcome"),
                    ],
                ),
            ],
        )
        json_str = spec.model_dump_json()
        spec2 = MappingSpecification.model_validate_json(json_str)
        assert spec2.name == "Test Mapping"
        assert len(spec2.rules) == 1
        assert spec2.rules[0].rule_id == "r1"
        assert len(spec2.rules[0].attribute_mappings) == 1

    def test_mapping_spec_json_matches_format(self):
        spec = MappingSpecification(
            rules=[
                SpanMappingRule(
                    rule_id="session_root",
                    rule_name="Session Root Span",
                    mcs_entity_type="trace_event",
                    mcs_value_type="SessionInfo",
                    otel_operation_name=OTELOperationName.agent_turn,
                    otel_span_kind=OTELSpanKind.SERVER,
                    span_name_template="agent.turn {bot_name}",
                    is_root=True,
                ),
            ],
        )
        data = json.loads(spec.model_dump_json())
        assert data["version"] == "1.0"
        rule = data["rules"][0]
        assert rule["rule_id"] == "session_root"
        assert rule["otel_operation_name"] == "agent.turn"
        assert rule["otel_span_kind"] == "SERVER"
        assert rule["is_root"] is True
