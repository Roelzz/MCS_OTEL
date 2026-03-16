import json
from pathlib import Path

import pytest

from config_loader import load_default_mapping
from converter import apply_mapping, to_otlp_json
from models import MappingSpecification, OTELTrace
from parsers import extract_entities, parse_transcript

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPT_PATH = FIXTURE_DIR / "rex_teams_transcript.json"


@pytest.fixture
def entities():
    with open(TRANSCRIPT_PATH) as f:
        content = f.read()
    t = parse_transcript(content)
    return extract_entities(t)


@pytest.fixture
def default_spec():
    return load_default_mapping()


@pytest.fixture
def trace(entities, default_spec):
    return apply_mapping(entities, default_spec)


class TestGenerateDefaultMapping:
    def test_returns_spec(self, default_spec):
        assert isinstance(default_spec, MappingSpecification)

    def test_has_rules(self, default_spec):
        assert len(default_spec.rules) >= 4

    def test_has_root_rule(self, default_spec):
        root_rules = [r for r in default_spec.rules if r.is_root]
        assert len(root_rules) == 1

    def test_rule_ids_unique(self, default_spec):
        ids = [r.rule_id for r in default_spec.rules]
        assert len(ids) == len(set(ids))


class TestApplyMapping:
    def test_returns_trace(self, trace):
        assert isinstance(trace, OTELTrace)

    def test_has_root_span(self, trace):
        assert trace.root_span is not None

    def test_trace_has_spans(self, trace):
        assert trace.total_spans > 0

    def test_trace_id_deterministic(self, entities, default_spec):
        trace1 = apply_mapping(entities, default_spec)
        trace2 = apply_mapping(entities, default_spec)
        assert trace1.trace_id == trace2.trace_id

    def test_root_span_is_invoke_agent(self, trace):
        assert (
            "invoke_agent" in trace.root_span.name
            or trace.root_span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        )

    def test_root_has_children(self, trace):
        assert len(trace.root_span.children) > 0

    def test_all_spans_have_trace_id(self, trace):
        def check(span):
            assert span.trace_id == trace.trace_id
            for child in span.children:
                check(child)

        check(trace.root_span)


class TestToOtlpJson:
    def test_returns_dict(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        assert isinstance(result, dict)

    def test_has_resource_spans(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        assert "resourceSpans" in result
        assert len(result["resourceSpans"]) == 1

    def test_has_scope_spans(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        scope_spans = result["resourceSpans"][0]["scopeSpans"]
        assert len(scope_spans) == 1

    def test_span_count_matches(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == trace.total_spans

    def test_service_name_in_resource(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        attrs = result["resourceSpans"][0]["resource"]["attributes"]
        service_attr = [a for a in attrs if a["key"] == "service.name"]
        assert len(service_attr) == 1
        assert service_attr[0]["value"]["stringValue"] == "copilot-studio"

    def test_roundtrip_json_serializable(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        assert parsed == result


# ---------------------------------------------------------------------------
# apply_mapping — edge cases
# ---------------------------------------------------------------------------


class TestApplyMappingEdgeCases:
    def test_empty_entities(self):
        """apply_mapping returns empty trace for empty entity list."""
        spec = load_default_mapping()
        trace = apply_mapping([], spec)
        assert trace.total_spans == 0
        assert trace.root_span.name == "empty"


# ---------------------------------------------------------------------------
# Event parent timing logic
# ---------------------------------------------------------------------------


class TestEventParentTiming:
    """Events should attach to the best parent span based on timing."""

    def _make_spec(self, error_event_names: list[str] | None = None) -> MappingSpecification:
        """Build a minimal spec with a root span rule, child span rule, and event rule."""
        from models import SpanMappingRule, OTELOperationName, OTELSpanKind

        rules = [
            SpanMappingRule(
                rule_id="root",
                rule_name="Root",
                mcs_entity_type="trace_event",
                mcs_value_type="SessionInfo",
                otel_operation_name=OTELOperationName.invoke_agent,
                otel_span_kind=OTELSpanKind.SERVER,
                is_root=True,
            ),
            SpanMappingRule(
                rule_id="turns",
                rule_name="Turns",
                mcs_entity_type="turn",
                otel_operation_name=OTELOperationName.chat,
                parent_rule_id="root",
                span_name_template="turn {turn_index}",
            ),
            SpanMappingRule(
                rule_id="errors",
                rule_name="Errors",
                mcs_entity_type="trace_event",
                mcs_value_type="ErrorTraceData",
                otel_operation_name=OTELOperationName.chat,
                parent_rule_id="turns",
                output_type="event",
                span_name_template="error",
            ),
        ]
        kwargs: dict = {"rules": rules}
        if error_event_names is not None:
            kwargs["error_event_names"] = error_event_names
        return MappingSpecification(**kwargs)

    def _make_entities(self) -> list:
        """Create entities: 1 session, 2 turns at different times, 1 error event."""
        from models import MCSEntity

        return [
            MCSEntity(
                entity_id="session_1",
                entity_type="trace_event",
                label="SessionInfo",
                value_type="SessionInfo",
                properties={"conversation_id": "conv1", "timestamp": 1000},
            ),
            MCSEntity(
                entity_id="turn_0",
                entity_type="turn",
                label="Turn 0",
                properties={
                    "conversation_id": "conv1",
                    "user_ts": 2000,
                    "bot_ts": 3000,
                    "turn_index": "0",
                },
            ),
            MCSEntity(
                entity_id="turn_1",
                entity_type="turn",
                label="Turn 1",
                properties={
                    "conversation_id": "conv1",
                    "user_ts": 5000,
                    "bot_ts": 6000,
                    "turn_index": "1",
                },
            ),
            MCSEntity(
                entity_id="err_1",
                entity_type="trace_event",
                label="ErrorTraceData",
                value_type="ErrorTraceData",
                properties={"conversation_id": "conv1", "timestamp": 5500},
            ),
        ]

    def test_event_attaches_to_best_timed_parent(self):
        """Error event at ts=5500 should attach to turn_1 (start=5000), not turn_0 (start=2000)."""
        spec = self._make_spec()
        entities = self._make_entities()
        trace = apply_mapping(entities, spec)

        # Find turn spans
        turn_spans = []
        for child in trace.root_span.children:
            if "turn" in child.name:
                turn_spans.append(child)
        turn_spans.sort(key=lambda s: s.start_time_ns)

        assert len(turn_spans) == 2
        # Error event should be on the second turn (later timestamp)
        turn_1 = turn_spans[1]
        assert len(turn_1.events) == 1
        assert turn_1.events[0]["name"] == "error"

        # First turn should have no events
        turn_0 = turn_spans[0]
        assert len(turn_0.events) == 0

    def test_event_error_marks_correct_parent(self):
        """ERROR status should be set on the timing-matched parent, not always the first."""
        spec = self._make_spec()
        entities = self._make_entities()
        trace = apply_mapping(entities, spec)

        turn_spans = []
        for child in trace.root_span.children:
            if "turn" in child.name:
                turn_spans.append(child)
        turn_spans.sort(key=lambda s: s.start_time_ns)

        # Second turn gets ERROR status
        assert turn_spans[1].status == "ERROR"
        # First turn stays UNSET
        assert turn_spans[0].status == "UNSET"

    def test_event_falls_back_to_root_without_parent(self):
        """Events with no parent_rule_id should attach to root span."""
        from models import SpanMappingRule, OTELOperationName, OTELSpanKind, MCSEntity

        spec = MappingSpecification(
            rules=[
                SpanMappingRule(
                    rule_id="root",
                    mcs_entity_type="trace_event",
                    mcs_value_type="SessionInfo",
                    otel_operation_name=OTELOperationName.invoke_agent,
                    is_root=True,
                ),
                SpanMappingRule(
                    rule_id="orphan_evt",
                    mcs_entity_type="trace_event",
                    mcs_value_type="ErrorTraceData",
                    otel_operation_name=OTELOperationName.chat,
                    output_type="event",
                    span_name_template="orphan_error",
                    # No parent_rule_id
                ),
            ],
        )
        entities = [
            MCSEntity(
                entity_id="s1",
                entity_type="trace_event",
                label="SessionInfo",
                value_type="SessionInfo",
                properties={"conversation_id": "c1", "timestamp": 1000},
            ),
            MCSEntity(
                entity_id="e1",
                entity_type="trace_event",
                label="ErrorTraceData",
                value_type="ErrorTraceData",
                properties={"conversation_id": "c1", "timestamp": 2000},
            ),
        ]
        trace = apply_mapping(entities, spec)
        assert len(trace.root_span.events) == 1
        assert trace.root_span.events[0]["name"] == "orphan_error"


# ---------------------------------------------------------------------------
# Configurable error event names
# ---------------------------------------------------------------------------


class TestConfigurableErrorEventNames:
    def test_custom_error_names_mark_status(self):
        """Custom error_event_names in spec should trigger ERROR status."""
        from models import SpanMappingRule, OTELOperationName, MCSEntity

        spec = MappingSpecification(
            error_event_names=["my_custom_error"],
            rules=[
                SpanMappingRule(
                    rule_id="root",
                    mcs_entity_type="trace_event",
                    mcs_value_type="SessionInfo",
                    otel_operation_name=OTELOperationName.invoke_agent,
                    is_root=True,
                ),
                SpanMappingRule(
                    rule_id="evt",
                    mcs_entity_type="trace_event",
                    mcs_value_type="ErrorTraceData",
                    otel_operation_name=OTELOperationName.chat,
                    parent_rule_id="root",
                    output_type="event",
                    span_name_template="my_custom_error",
                ),
            ],
        )
        entities = [
            MCSEntity(
                entity_id="s1",
                entity_type="trace_event",
                label="SessionInfo",
                value_type="SessionInfo",
                properties={"conversation_id": "c1", "timestamp": 1000},
            ),
            MCSEntity(
                entity_id="e1",
                entity_type="trace_event",
                label="ErrorTraceData",
                value_type="ErrorTraceData",
                properties={"conversation_id": "c1", "timestamp": 2000},
            ),
        ]
        trace = apply_mapping(entities, spec)
        assert trace.root_span.status == "ERROR"

    def test_default_error_names_not_triggered_when_overridden(self):
        """When error_event_names is overridden, default names should NOT trigger ERROR."""
        from models import SpanMappingRule, OTELOperationName, MCSEntity

        spec = MappingSpecification(
            error_event_names=["something_else"],
            rules=[
                SpanMappingRule(
                    rule_id="root",
                    mcs_entity_type="trace_event",
                    mcs_value_type="SessionInfo",
                    otel_operation_name=OTELOperationName.invoke_agent,
                    is_root=True,
                ),
                SpanMappingRule(
                    rule_id="evt",
                    mcs_entity_type="trace_event",
                    mcs_value_type="ErrorTraceData",
                    otel_operation_name=OTELOperationName.chat,
                    parent_rule_id="root",
                    output_type="event",
                    # This would normally trigger ERROR with default names
                    span_name_template="error",
                ),
            ],
        )
        entities = [
            MCSEntity(
                entity_id="s1",
                entity_type="trace_event",
                label="SessionInfo",
                value_type="SessionInfo",
                properties={"conversation_id": "c1", "timestamp": 1000},
            ),
            MCSEntity(
                entity_id="e1",
                entity_type="trace_event",
                label="ErrorTraceData",
                value_type="ErrorTraceData",
                properties={"conversation_id": "c1", "timestamp": 2000},
            ),
        ]
        trace = apply_mapping(entities, spec)
        # "error" is NOT in error_event_names=["something_else"], so no ERROR
        assert trace.root_span.status == "UNSET"
